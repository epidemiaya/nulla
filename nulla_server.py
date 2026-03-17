#!/usr/bin/env python3
"""
Nulla Light Client — Local Server

Serves the React UI at http://localhost:7421
and provides a JSON API for wallet operations.

Run: python nulla_server.py [--port 7421] [--node https://lac-beta.uk]
"""

import os
import sys
import json
import time
import secrets
import threading
import webbrowser
import argparse
from pathlib import Path
from functools import wraps
from typing import Optional

from flask import Flask, jsonify, request, send_from_directory, session

from nulla_core import (
    NullaWallet, NullaError, KeystoreError, WalletError,
    validate_key_id, format_lac
)
from nulla_node import LACNodeClient, NodeError, NodeConnectionError

# ── App setup ──────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="ui/dist", static_url_path="")
app.secret_key = secrets.token_hex(32)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Allow CORS only from localhost (dev mode)
try:
    from flask_cors import CORS
    CORS(app, origins=["http://localhost:5173", "http://localhost:7421"],
         supports_credentials=True)
except ImportError:
    pass

DEFAULT_KEYSTORE = str(Path.home() / ".nulla" / "wallet.nulla")
DEFAULT_NODE = "https://lac-beta.uk"

# ── Global state ───────────────────────────────────────────────────────────────
_wallet: Optional[NullaWallet] = None
_node: LACNodeClient = LACNodeClient(DEFAULT_NODE)


# ── Helpers ────────────────────────────────────────────────────────────────────

def err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": str(msg)}), code

def ok_json(**data):
    return jsonify({"ok": True, **data})

def require_unlocked(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if _wallet is None or not _wallet._unlocked:
            return err("Wallet is locked", 401)
        return f(*args, **kwargs)
    return wrapper

def keystore_path() -> str:
    return session.get("keystore_path", DEFAULT_KEYSTORE)


# ── API — system ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    return ok_json(
        wallet_exists=Path(keystore_path()).exists(),
        wallet_unlocked=bool(_wallet and _wallet._unlocked),
        node_url=_node.node_url,
        version="1.0.0",
    )


# ── API — wallet lifecycle ─────────────────────────────────────────────────────

@app.route("/api/wallet/create", methods=["POST"])
def api_create():
    global _wallet
    d = request.json or {}
    password = d.get("password", "")
    if len(password) < 8:
        return err("Password must be at least 8 characters")

    ks_path = d.get("keystore", DEFAULT_KEYSTORE)
    try:
        wallet = NullaWallet.generate(password)
        Path(ks_path).parent.mkdir(parents=True, exist_ok=True)
        wallet.save(ks_path, password)
        _wallet = wallet
        session["keystore_path"] = ks_path
        return ok_json(
            key_id=wallet.key_id,
            mnemonic=wallet.mnemonic,
            accounts=wallet.all_accounts(),
        )
    except Exception as e:
        return err(str(e))


@app.route("/api/wallet/import", methods=["POST"])
def api_import():
    global _wallet
    d = request.json or {}
    mnemonic = d.get("mnemonic", "").strip()
    password = d.get("password", "")
    if not mnemonic:
        return err("Mnemonic required")
    if not password:
        return err("Password required")

    ks_path = d.get("keystore", DEFAULT_KEYSTORE)
    try:
        wallet = NullaWallet.from_mnemonic(mnemonic, password)
        Path(ks_path).parent.mkdir(parents=True, exist_ok=True)
        wallet.save(ks_path, password)
        _wallet = wallet
        session["keystore_path"] = ks_path
        return ok_json(key_id=wallet.key_id, accounts=wallet.all_accounts())
    except WalletError as e:
        return err(str(e))


@app.route("/api/wallet/unlock", methods=["POST"])
def api_unlock():
    global _wallet
    d = request.json or {}
    password = d.get("password", "")
    ks_path = d.get("keystore", DEFAULT_KEYSTORE)
    try:
        wallet = NullaWallet.load(ks_path, password)
        _wallet = wallet
        session["keystore_path"] = ks_path
        return ok_json(key_id=wallet.key_id)
    except KeystoreError as e:
        return err(str(e), 401)
    except FileNotFoundError:
        return err("Keystore not found", 404)


@app.route("/api/wallet/lock", methods=["POST"])
def api_lock():
    global _wallet
    if _wallet:
        _wallet.lock()
        _wallet = None
    return ok_json()


@app.route("/api/wallet/info")
@require_unlocked
def api_wallet_info():
    return ok_json(
        key_id=_wallet.key_id,
        accounts=_wallet.all_accounts(),
        metadata=_wallet.metadata,
    )


# ── API — balance & transactions ───────────────────────────────────────────────

@app.route("/api/balance")
@require_unlocked
def api_balance():
    try:
        result = _node.get_balance(_wallet.key_id)
        username = _node.get_username(_wallet.key_id)
        return ok_json(
            key_id=_wallet.key_id,
            balance=result["balance"],
            pending=result.get("pending", 0),
            stash=result.get("stash", 0),
            level=result.get("level", 0),
            username=username,
        )
    except NodeError as e:
        return err(str(e))


@app.route("/api/transactions")
@require_unlocked
def api_transactions():
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))
    try:
        txs = _node.get_transactions(_wallet.key_id, limit=limit, offset=offset)
        my_key = _wallet.key_id
        for tx in txs:
            tx_to = tx.get("to", tx.get("recipient", ""))
            tx["direction"] = "in" if my_key[:16] in (tx_to or "") else "out"
        return ok_json(transactions=txs)
    except NodeError as e:
        return err(str(e))


@app.route("/api/send", methods=["POST"])
@require_unlocked
def api_send():
    d = request.json or {}
    to = d.get("to", "").strip()
    try:
        amount = float(d.get("amount", 0))
        fee = float(d.get("fee", 0.001))
    except (TypeError, ValueError):
        return err("Invalid amount or fee")

    memo = d.get("memo", "")

    if not to:
        return err("Recipient required")
    if amount <= 0:
        return err("Amount must be positive")

    # Resolve username if needed
    if not validate_key_id(to):
        resolved = _node.resolve_username(to.lstrip("@"))
        if not resolved:
            return err(f"Unknown address or username: {to}")
        to_key_id = resolved
    else:
        to_key_id = to

    kp = _wallet.default_keypair()
    tx_data = {
        "from": kp.key_id,
        "to": to_key_id,
        "amount": amount,
        "fee": fee,
        "timestamp": int(time.time()),
    }
    if memo:
        tx_data["memo"] = memo

    signature = _wallet.sign_transaction(tx_data)

    try:
        result = _node.send_transaction(
            from_key_id=kp.key_id,
            to_key_id=to_key_id,
            amount=amount,
            signature=signature,
            fee=fee,
            memo=memo,
        )
        return ok_json(result=result)
    except NodeError as e:
        return err(str(e))


# ── API — node ─────────────────────────────────────────────────────────────────

@app.route("/api/node/status")
def api_node_status():
    result = _node.test_connection()
    return ok_json(**result)


@app.route("/api/node/connect", methods=["POST"])
def api_node_connect():
    global _node
    d = request.json or {}
    url = d.get("url", "").strip()
    if not url:
        return err("URL required")
    candidate = LACNodeClient(url)
    result = candidate.test_connection()
    if result["is_connected"]:
        _node = candidate
        return ok_json(**result)
    return err(result.get("error", "Cannot connect"))


# ── API — resolve & faucet ─────────────────────────────────────────────────────

@app.route("/api/resolve/<username>")
def api_resolve(username: str):
    result = _node.resolve_username(username)
    if result:
        return ok_json(key_id=result)
    return err(f"Username not found: {username}", 404)


@app.route("/api/faucet", methods=["POST"])
@require_unlocked
def api_faucet():
    try:
        result = _node.faucet(_wallet.key_id)
        return ok_json(result=result)
    except NodeError as e:
        return err(str(e))


# ── Static / SPA ───────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path: str):
    dist = app.static_folder
    if path and Path(dist, path).is_file():
        return send_from_directory(dist, path)
    index = Path(dist, "index.html")
    if index.exists():
        return send_from_directory(dist, "index.html")
    # Dev fallback: show helpful message
    return (
        "<pre style='font-family:monospace;padding:2em'>"
        "Nulla UI not built yet.\n\n"
        "Run:\n"
        "  cd ui && npm install && npm run build\n\n"
        "Or for dev mode:\n"
        "  cd ui && npm run dev\n"
        "  (then open http://localhost:5173)\n"
        "</pre>"
    ), 200


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    global _node

    parser = argparse.ArgumentParser(description="Nulla local server")
    parser.add_argument("--port",       type=int, default=7421)
    parser.add_argument("--node",       default=DEFAULT_NODE)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--host",       default="127.0.0.1",
                        help="Bind host (127.0.0.1 = localhost only)")
    args = parser.parse_args()

    _node = LACNodeClient(args.node)

    print(f"""
  ╔╗╔╦ ╦╦  ╦  ╔═╗
  ║║║║ ║║  ║  ╠═╣
  ╝╚╝╚═╝╩═╝╩═╝╩ ╩  LAC Light Wallet v1.0.0
  ─────────────────────────────────────────
  Server:   http://localhost:{args.port}
  Node:     {args.node}
  Wallet:   {DEFAULT_KEYSTORE}
  Ctrl+C to stop
""")

    if not args.no_browser:
        def _open():
            time.sleep(1.2)
            webbrowser.open(f"http://localhost:{args.port}")
        threading.Thread(target=_open, daemon=True).start()

    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
