#!/usr/bin/env python3
"""
Nulla Light Client — CLI

Usage:
  nulla create               Create new wallet
  nulla import [words...]    Import from mnemonic
  nulla balance              Show balance
  nulla send <to> <amount>   Send LAC
  nulla receive              Show your address
  nulla history              Transaction history
  nulla node                 Node status
  nulla faucet               Request testnet tokens
  nulla lock                 Lock wallet (clear session)

Options:
  --node URL        LAC node URL  [default: https://lac-beta.uk]
  --keystore PATH   Keystore file [default: ~/.nulla/wallet.nulla]
"""

import sys
import os
import json
import getpass
import argparse
import time
from pathlib import Path
from typing import Optional

from nulla_core import (
    NullaWallet, NullaError, KeystoreError, WalletError,
    validate_key_id, format_lac
)
from nulla_node import LACNodeClient, NodeError, NodeConnectionError

DEFAULT_KEYSTORE = Path.home() / ".nulla" / "wallet.nulla"
DEFAULT_NODE = "https://lac-beta.uk"

# ── Terminal colors ────────────────────────────────────────────────────────────
_NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")

def _c(code: str) -> str:
    return "" if _NO_COLOR else code

R  = _c("\033[0m")
B  = _c("\033[1m")
DIM= _c("\033[2m")
GR = _c("\033[92m")   # green
YL = _c("\033[93m")   # yellow
CY = _c("\033[96m")   # cyan
RD = _c("\033[91m")   # red

BANNER = f"""{CY}
  ╔╗╔╦ ╦╦  ╦  ╔═╗
  ║║║║ ║║  ║  ╠═╣
  ╝╚╝╚═╝╩═╝╩═╝╩ ╩  {DIM}LAC Light Wallet v1.0.0{R}
"""

def die(msg: str):
    print(f"{RD}✗ {msg}{R}", file=sys.stderr)
    sys.exit(1)

def ok(msg: str):
    print(f"{GR}✓{R} {msg}")

def info(msg: str):
    print(f"{CY}→{R} {msg}")

def warn(msg: str):
    print(f"{YL}⚠{R} {msg}")

def hr(width: int = 50):
    print(f"{DIM}{'─' * width}{R}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def prompt_password(confirm: bool = False, prompt: str = "Password") -> str:
    pw = getpass.getpass(f"  {prompt}: ")
    if not pw:
        die("Password cannot be empty")
    if confirm:
        pw2 = getpass.getpass("  Confirm password: ")
        if pw != pw2:
            die("Passwords do not match")
    return pw


def load_wallet(path: Path, password: Optional[str] = None) -> NullaWallet:
    if not path.exists():
        die(f"No keystore at {path}\n  Run: nulla create")
    if password is None:
        password = prompt_password()
    try:
        return NullaWallet.load(str(path), password)
    except KeystoreError as e:
        die(str(e))


def trunc(key_id: str, lead: int = 12, tail: int = 8) -> str:
    return f"{key_id[:lead]}...{key_id[-tail:]}"


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_create(args, node: LACNodeClient):
    path = Path(args.keystore)
    if path.exists():
        ans = input(f"{YL}  ⚠ Keystore exists at {path}. Overwrite? [yes/no]: {R}")
        if ans.strip().lower() != "yes":
            info("Aborted")
            return

    path.parent.mkdir(parents=True, exist_ok=True)
    password = prompt_password(confirm=True)
    info("Generating wallet...")
    wallet = NullaWallet.generate(password)
    wallet.save(str(path), password)

    print()
    hr(56)
    print(f"  {B}NEW WALLET CREATED{R}")
    hr(56)
    print(f"\n  {CY}Key ID (address):{R}")
    print(f"  {wallet.key_id}")
    print(f"\n  {B}{YL}RECOVERY PHRASE — WRITE THIS DOWN:{R}")
    print()
    words = (wallet.mnemonic or "").split()
    for row in range(0, len(words), 6):
        chunk = words[row:row+6]
        cols = "  ".join(f"{i+row+1:2}. {w:<12}" for i, w in enumerate(chunk))
        print(f"  {B}{cols}{R}")
    print(f"\n  {RD}Never share this phrase. Store it offline.{R}")
    print(f"\n  Keystore: {path}")
    hr(56)
    print()


def cmd_import(args, node: LACNodeClient):
    path = Path(args.keystore)
    path.parent.mkdir(parents=True, exist_ok=True)

    if args.words:
        mnemonic = " ".join(args.words)
    else:
        mnemonic = input("  Mnemonic phrase: ").strip()

    if not mnemonic:
        die("Mnemonic required")

    password = prompt_password(confirm=True)
    try:
        wallet = NullaWallet.from_mnemonic(mnemonic, password)
        wallet.save(str(path), password)
        ok(f"Wallet restored")
        info(f"Key ID: {wallet.key_id}")
        info(f"Keystore: {path}")
    except WalletError as e:
        die(str(e))


def cmd_balance(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    info(f"Fetching balance from {node.node_url} ...")
    try:
        result = node.get_balance(wallet.key_id)
        username = node.get_username(wallet.key_id)
    except NodeConnectionError as e:
        die(str(e))

    print()
    hr(50)
    print(f"  {B}BALANCE{R}")
    hr(50)
    if username:
        print(f"  Username:  {CY}@{username}{R}")
    print(f"  Address:   {DIM}{trunc(wallet.key_id)}{R}")
    print(f"  {B}{GR}{format_lac(result['balance'])}{R}")
    if result.get("stash"):
        print(f"  Stash:     {format_lac(result['stash'])}")
    if result.get("level"):
        print(f"  Level:     {result['level']}")
    hr(50)
    print()


def cmd_send(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    kp = wallet.default_keypair()

    to = args.to
    amount = float(args.amount)
    fee = float(args.fee)
    memo = args.memo or ""

    if amount <= 0:
        die("Amount must be positive")

    # Resolve username → key_id
    if not validate_key_id(to):
        info(f"Resolving {to!r}...")
        resolved = node.resolve_username(to)
        if not resolved:
            die(f"Unknown address or username: {to}")
        to_key_id = resolved
        info(f"Resolved to: {trunc(to_key_id)}")
    else:
        to_key_id = to

    print()
    hr(50)
    print(f"  {B}{YL}CONFIRM TRANSACTION{R}")
    hr(50)
    print(f"  From:   {trunc(wallet.key_id)}")
    print(f"  To:     {trunc(to_key_id)}")
    print(f"  Amount: {B}{format_lac(amount)}{R}")
    print(f"  Fee:    {format_lac(fee)}")
    print(f"  Total:  {B}{format_lac(amount + fee)}{R}")
    if memo:
        print(f"  Memo:   {memo}")
    hr(50)

    ans = input("  Type YES to confirm: ").strip()
    if ans != "YES":
        info("Cancelled")
        return

    tx_data = {
        "from": kp.key_id,
        "to": to_key_id,
        "amount": amount,
        "fee": fee,
        "timestamp": int(time.time()),
    }
    if memo:
        tx_data["memo"] = memo

    signature = wallet.sign_transaction(tx_data)

    info("Broadcasting...")
    try:
        result = node.send_transaction(
            from_key_id=kp.key_id,
            to_key_id=to_key_id,
            amount=amount,
            signature=signature,
            fee=fee,
            memo=memo,
        )
        tx_id = result.get("tx_id", result.get("id", str(result)))
        ok(f"Sent! TX: {tx_id}")
    except NodeError as e:
        die(f"Transaction failed: {e}")


def cmd_receive(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    username = node.get_username(wallet.key_id)

    print()
    hr(70)
    print(f"  {B}RECEIVE LAC{R}")
    hr(70)
    if username:
        print(f"  Username:  {CY}@{username}{R}  (shareable)")
    print(f"  Key ID:    {wallet.key_id}")
    hr(70)
    print()


def cmd_history(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    info("Fetching history...")
    txs = node.get_transactions(wallet.key_id, limit=args.limit)

    if not txs:
        info("No transactions found")
        return

    my_key = wallet.key_id

    print()
    hr(72)
    print(f"  {B}HISTORY{R}  (latest {len(txs)})")
    hr(72)
    print(f"  {'DIR':4}  {'AMOUNT':20}  {'FROM/TO':26}  {'TIME'}")
    hr(72)

    for tx in txs:
        tx_to = tx.get("to", tx.get("recipient", ""))
        tx_from = tx.get("from", tx.get("sender", ""))
        amount = float(tx.get("amount", 0))
        ts = tx.get("timestamp", 0)
        memo = tx.get("memo", "")

        is_in = my_key[:16] in (tx_to or "")
        direction = f"{GR}↓ IN {R}" if is_in else f"{RD}↑ OUT{R}"
        amt_str = (f"{GR}+{format_lac(amount)}{R}" if is_in
                   else f"{RD}-{format_lac(amount)}{R}")

        counterpart = tx_from if is_in else tx_to
        cp_short = trunc(counterpart, 12, 6) if counterpart else "—"

        from datetime import datetime as dt
        date_str = dt.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "—"

        line = f"  {direction}  {amt_str:30}  {cp_short:26}  {DIM}{date_str}{R}"
        print(line)
        if memo:
            print(f"         {DIM}memo: {memo}{R}")

    hr(72)
    print()


def cmd_node(args, node: LACNodeClient):
    info(f"Connecting to {node.node_url}...")
    result = node.test_connection()
    if not result["is_connected"]:
        die(f"Cannot connect: {result.get('error', '?')}")

    print()
    hr(50)
    print(f"  {B}NODE STATUS{R}")
    hr(50)
    print(f"  URL:          {node.node_url}")
    print(f"  Block height: {result['block_height']}")
    print(f"  Latency:      {result['latency_ms']} ms")
    raw = result.get("raw", {})
    for k in ("version", "peers", "mining", "uptime"):
        if k in raw:
            print(f"  {k.capitalize():13s} {raw[k]}")
    hr(50)
    print()


def cmd_faucet(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    info(f"Requesting faucet for {trunc(wallet.key_id)}...")
    try:
        result = node.faucet(wallet.key_id)
        ok(f"Response: {result}")
    except NodeError as e:
        die(str(e))


def cmd_accounts(args, node: LACNodeClient):
    wallet = load_wallet(Path(args.keystore))
    print()
    hr(78)
    print(f"  {B}ACCOUNTS{R}")
    hr(78)
    for acc in wallet.all_accounts():
        marker = f"{GR}●{R}" if acc["index"] == 0 else f"{DIM}○{R}"
        print(f"  {marker} [{acc['index']}] {acc['key_id']}")
        print(f"        {DIM}{acc['path']}{R}")
    hr(78)
    print()


# ── Entry point ────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nulla",
        description="Nulla — LAC Light Wallet",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.strip(),
    )
    p.add_argument("--node",      default=DEFAULT_NODE,       help="LAC node URL")
    p.add_argument("--keystore",  default=str(DEFAULT_KEYSTORE), help="Keystore path")

    sub = p.add_subparsers(dest="cmd", metavar="command")

    sub.add_parser("create",   help="Create new wallet")

    pi = sub.add_parser("import", help="Import from mnemonic")
    pi.add_argument("words", nargs="*", help="Mnemonic words (interactive if omitted)")

    sub.add_parser("balance",  help="Show balance")
    sub.add_parser("receive",  help="Show receive address")
    sub.add_parser("accounts", help="List derived accounts")
    sub.add_parser("node",     help="Node status")
    sub.add_parser("faucet",   help="Request testnet tokens (testnet only)")

    ps = sub.add_parser("send",    help="Send LAC")
    ps.add_argument("to",     help="Recipient key_id or @username")
    ps.add_argument("amount", help="Amount in LAC")
    ps.add_argument("--fee",  default="0.001", help="Fee [0.001]")
    ps.add_argument("--memo", default="",      help="Optional memo")

    ph = sub.add_parser("history", help="Transaction history")
    ph.add_argument("--limit", type=int, default=20, help="Max rows [20]")

    return p


def main():
    print(BANNER)
    parser = build_parser()
    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    node = LACNodeClient(args.node)

    handlers = {
        "create":   cmd_create,
        "import":   cmd_import,
        "balance":  cmd_balance,
        "send":     cmd_send,
        "receive":  cmd_receive,
        "history":  cmd_history,
        "node":     cmd_node,
        "faucet":   cmd_faucet,
        "accounts": cmd_accounts,
    }

    fn = handlers.get(args.cmd)
    if not fn:
        parser.print_help()
        return

    try:
        fn(args, node)
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted{R}")
    except NullaError as e:
        die(str(e))


if __name__ == "__main__":
    main()
