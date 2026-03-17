#!/usr/bin/env python3
"""
Nulla — Local Server
Flask JSON API + React SPA
Binds to 127.0.0.1 only (localhost-only, never exposed to network).
Run: python nulla_server.py [--port 7421] [--testnet]
"""

import os
import json
import time
import secrets
import threading
import webbrowser
import argparse
from pathlib import Path
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory, session

from nulla_core import (
    NullaWallet, NullaError, KeystoreError, WalletError,
    validate_address, format_btc
)
from nulla_electrum import ElectrumClient, ElectrumError
from nulla_tx import build_send_tx, UTXO, estimate_fee

try:
    from flask_cors import CORS
    _HAS_CORS = True
except ImportError:
    _HAS_CORS = False

# ── App config ────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder="ui/dist", static_url_path="")
app.secret_key = secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,
    SESSION_COOKIE_SAMESITE  = "Lax",
    SESSION_COOKIE_SECURE    = False,  # localhost only
    PERMANENT_SESSION_LIFETIME = 3600,
)

if _HAS_CORS:
    CORS(app, origins=["http://localhost:5173", "http://localhost:7421"],
         supports_credentials=True)

DEFAULT_KEYSTORE = str(Path.home() / ".nulla" / "wallet.nulla")

# Global state
_wallet: NullaWallet = None
_electrum: ElectrumClient = None
_network: str = "mainnet"


# ── Helpers ───────────────────────────────────────────────────────────────────

def err(msg: str, code: int = 400):
    return jsonify({"ok": False, "error": str(msg)}), code

def ok(**kw):
    return jsonify({"ok": True, **kw})

def require_unlocked(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if _wallet is None or not _wallet._unlocked:
            return err("Wallet locked", 401)
        return f(*args, **kwargs)
    return wrapper

def _get_electrum() -> ElectrumClient:
    global _electrum
    if _electrum is None:
        _electrum = ElectrumClient(network=_network)
    return _electrum

def _all_utxos_for_wallet() -> list:
    """Fetch and assemble UTXOs for all wallet addresses."""
    el   = _get_electrum()
    utxo_list = []
    for addr in _wallet.all_addresses():
        try:
            raw_utxos = el.get_utxos(addr.electrum_scripthash)
            for u in raw_utxos:
                utxo_list.append(UTXO(
                    txid    = u["tx_hash"],
                    vout    = u["tx_pos"],
                    value   = u["value"],
                    address = addr,
                    height  = u.get("height", 0),
                ))
        except ElectrumError:
            pass
    return utxo_list


# ── API: system ───────────────────────────────────────────────────────────────

@app.route("/api/status")
def api_status():
    ks = session.get("keystore_path", DEFAULT_KEYSTORE)
    return ok(
        wallet_exists   = Path(ks).exists(),
        wallet_unlocked = bool(_wallet and _wallet._unlocked),
        network         = _network,
        version         = "1.0.0",
    )


# ── API: wallet lifecycle ──────────────────────────────────────────────────────

@app.route("/api/wallet/create", methods=["POST"])
def api_create():
    global _wallet
    d  = request.json or {}
    pw = d.get("password", "")
    if len(pw) < 8:
        return err("Password must be at least 8 characters")
    ks_path = d.get("keystore", DEFAULT_KEYSTORE)
    try:
        w = NullaWallet.generate(pw, network=_network)
        Path(ks_path).parent.mkdir(parents=True, exist_ok=True)
        w.save(ks_path, pw)
        _wallet = w
        session["keystore_path"] = ks_path
        return ok(
            address  = w.address,
            mnemonic = w.mnemonic,
            accounts = w.all_accounts_summary(),
        )
    except Exception as e:
        return err(str(e))


@app.route("/api/wallet/import", methods=["POST"])
def api_import():
    global _wallet
    d        = request.json or {}
    mnemonic = d.get("mnemonic", "").strip()
    pw       = d.get("password", "")
    if not mnemonic: return err("Mnemonic required")
    if len(pw) < 8:  return err("Min 8 characters")
    ks_path = d.get("keystore", DEFAULT_KEYSTORE)
    try:
        w = NullaWallet.from_mnemonic(mnemonic, pw, network=_network)
        Path(ks_path).parent.mkdir(parents=True, exist_ok=True)
        w.save(ks_path, pw)
        _wallet = w
        session["keystore_path"] = ks_path
        return ok(address=w.address, accounts=w.all_accounts_summary())
    except WalletError as e:
        return err(str(e))


@app.route("/api/wallet/unlock", methods=["POST"])
def api_unlock():
    global _wallet
    d  = request.json or {}
    pw = d.get("password", "")
    ks = d.get("keystore", session.get("keystore_path", DEFAULT_KEYSTORE))
    try:
        w = NullaWallet.load(ks, pw)
        _wallet = w
        session["keystore_path"] = ks
        return ok(address=w.address, network=w.network)
    except KeystoreError as e:
        return err(str(e), 401)


@app.route("/api/wallet/lock", methods=["POST"])
def api_lock():
    global _wallet
    if _wallet:
        _wallet.lock()
        _wallet = None
    return ok()


@app.route("/api/wallet/info")
@require_unlocked
def api_info():
    return ok(
        address  = _wallet.address,
        network  = _wallet.network,
        accounts = _wallet.all_accounts_summary(),
        metadata = _wallet.metadata,
    )


# ── API: balance ──────────────────────────────────────────────────────────────

@app.route("/api/balance")
@require_unlocked
def api_balance():
    try:
        el = _get_electrum()
        confirmed = 0
        unconfirmed = 0
        for addr in _wallet.all_addresses():
            try:
                b = el.get_balance(addr.electrum_scripthash)
                confirmed   += b["confirmed"]
                unconfirmed += b["unconfirmed"]
            except ElectrumError:
                pass
        return ok(
            confirmed   = confirmed,
            unconfirmed = unconfirmed,
            total       = confirmed + unconfirmed,
            formatted   = format_btc(confirmed + unconfirmed),
            address     = _wallet.address,
        )
    except ElectrumError as e:
        return err(str(e))


# ── API: UTXOs ────────────────────────────────────────────────────────────────

@app.route("/api/utxos")
@require_unlocked
def api_utxos():
    try:
        utxos = _all_utxos_for_wallet()
        return ok(utxos=[{
            "txid":    u.txid,
            "vout":    u.vout,
            "value":   u.value,
            "address": u.address.address,
            "height":  u.height,
            "type":    u.address.addr_type,
        } for u in utxos])
    except ElectrumError as e:
        return err(str(e))


# ── API: transactions ─────────────────────────────────────────────────────────

@app.route("/api/transactions")
@require_unlocked
def api_transactions():
    limit  = int(request.args.get("limit", 25))
    try:
        el          = _get_electrum()
        my_addrs    = {a.address for a in _wallet.all_addresses()}
        scripthashes= [a.electrum_scripthash for a in _wallet.all_addresses()]
        history     = el.get_history_multi(scripthashes)[:limit]

        result = []
        for item in history:
            txid = item["tx_hash"]
            # Try to get tx details for amount
            try:
                raw = el.get_transaction(txid, verbose=True)
                # Parse outputs
                total_out_to_us = 0
                total_in_from_us = 0
                if isinstance(raw, dict):
                    for vout in raw.get("vout", []):
                        spk  = vout.get("scriptPubKey", {})
                        addr = spk.get("address") or (spk.get("addresses") or [None])[0]
                        if addr and addr in my_addrs:
                            val = int(vout.get("value", 0) * 1e8)
                            total_out_to_us += val
                direction = "in" if total_out_to_us > 0 else "out"
                result.append({
                    "txid":      txid,
                    "height":    item.get("height", 0),
                    "confirmed": item.get("height", 0) > 0,
                    "amount":    total_out_to_us,
                    "direction": direction,
                })
            except Exception:
                result.append({
                    "txid":      txid,
                    "height":    item.get("height", 0),
                    "confirmed": item.get("height", 0) > 0,
                    "amount":    0,
                    "direction": "unknown",
                })

        return ok(transactions=result)
    except ElectrumError as e:
        return err(str(e))


# ── API: fee estimate ─────────────────────────────────────────────────────────

@app.route("/api/fee")
def api_fee():
    blocks = int(request.args.get("blocks", 3))
    try:
        el       = _get_electrum()
        fee_rate = el.estimate_fee(blocks)
        return ok(fee_rate=fee_rate, blocks=blocks, unit="sat/vbyte")
    except ElectrumError as e:
        return err(str(e))


# ── API: send ─────────────────────────────────────────────────────────────────

@app.route("/api/send", methods=["POST"])
@require_unlocked
def api_send():
    d          = request.json or {}
    to         = d.get("to", "").strip()
    amount_btc = d.get("amount")
    fee_rate   = int(d.get("fee_rate", 5))

    if not to:
        return err("Recipient address required")
    if not validate_address(to, _wallet.network):
        return err(f"Invalid Bitcoin address: {to}")

    try:
        amount_sats = int(float(amount_btc) * 1e8)
    except (TypeError, ValueError):
        return err("Invalid amount")

    if amount_sats <= 0:
        return err("Amount must be positive")

    try:
        # Get UTXOs
        utxos = _all_utxos_for_wallet()
        if not utxos:
            return err("No spendable UTXOs")

        change_addr = _wallet.change_address("p2wpkh")

        raw_hex, fee_sats, change_sats = build_send_tx(
            all_utxos      = utxos,
            to_address     = to,
            amount_sats    = amount_sats,
            change_address = change_addr,
            fee_rate       = fee_rate,
        )

        # Broadcast
        el   = _get_electrum()
        txid = el.broadcast(raw_hex)

        return ok(
            txid       = txid,
            amount     = amount_sats,
            fee        = fee_sats,
            change     = change_sats,
            formatted  = format_btc(amount_sats),
        )
    except Exception as e:
        return err(str(e))


# ── API: preview transaction (without broadcast) ──────────────────────────────

@app.route("/api/send/preview", methods=["POST"])
@require_unlocked
def api_send_preview():
    """Returns fee estimate before confirming send."""
    d          = request.json or {}
    to         = d.get("to", "").strip()
    amount_btc = d.get("amount")
    fee_rate   = int(d.get("fee_rate", 5))

    if not to or not amount_btc:
        return err("Address and amount required")

    try:
        amount_sats = int(float(amount_btc) * 1e8)
        utxos       = _all_utxos_for_wallet()
        total_sats  = sum(u.value for u in utxos)

        from nulla_tx import select_utxos
        selected, fee = select_utxos(utxos, amount_sats, fee_rate)

        return ok(
            amount      = amount_sats,
            fee         = fee,
            total       = amount_sats + fee,
            change      = sum(u.value for u in selected) - amount_sats - fee,
            balance     = total_sats,
            fee_rate    = fee_rate,
            inputs_used = len(selected),
        )
    except Exception as e:
        return err(str(e))


# ── API: node ─────────────────────────────────────────────────────────────────

@app.route("/api/node/status")
def api_node_status():
    try:
        el     = _get_electrum()
        result = el.test_connection()
        return ok(**result)
    except Exception as e:
        return ok(connected=False, error=str(e))


# ── Static SPA ────────────────────────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path):
    dist = app.static_folder
    if path and Path(dist, path).is_file():
        return send_from_directory(dist, path)
    index = Path(dist, "index.html")
    if index.exists():
        return send_from_directory(dist, "index.html")
    return (
        "<pre style='font:13px monospace;padding:2em;background:#080808;color:#d4d4d4'>"
        "Nulla UI not built.\n\n"
        "Run:\n  cd ui && npm install && npm run build\n\n"
        "Dev mode:\n  cd ui && npm run dev  (port 5173)\n"
        "</pre>"
    ), 200


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    global _network

    parser = argparse.ArgumentParser(description="Nulla Bitcoin Wallet")
    parser.add_argument("--port",       type=int, default=7421)
    parser.add_argument("--host",       default="127.0.0.1")
    parser.add_argument("--testnet",    action="store_true")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _network = "testnet" if args.testnet else "mainnet"

    print(f"""
  ╔╗╔╦ ╦╦  ╦  ╔═╗
  ║║║║ ║║  ║  ╠═╣
  ╝╚╝╚═╝╩═╝╩═╝╩ ╩  Bitcoin Light Wallet v1.0.0
  ─────────────────────────────────────────────
  UI:       http://localhost:{args.port}
  Network:  {_network.upper()}
  Keystore: {DEFAULT_KEYSTORE}
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
