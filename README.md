# Nulla — LAC Light Wallet

Privacy-first light client for the [LightAnonChain (LAC)](https://lac-beta.uk) blockchain.
Standalone app — integrates directly into `lac_node.py` when ready.

## Features

- **BIP39 HD wallet** — 24-word mnemonic, SLIP-0010 Ed25519 derivation
- **AES-256-GCM keystore** — PBKDF2 × 600k iterations, HMAC-verified
- **E2E encryption** — X25519 ECDH + HKDF + AES-GCM
- **Full node client** — balance, send, history, username registry
- **Web UI** — dark terminal aesthetic, mobile-first PWA-ready
- **CLI** — `nulla balance`, `nulla send`, `nulla history`, ...
- **Zero telemetry** — keys never leave your device

---

## Quick Start

### 1. Python setup

```bash
git clone https://github.com/epidemiaya/nulla
cd nulla

python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Build the UI

```bash
cd ui
npm install
npm run build
cd ..
```

### 3. Run

```bash
# Web UI + API server (opens browser automatically)
python nulla_server.py

# Or with custom node
python nulla_server.py --node https://your-lac-node.example.com --port 7421
```

Open: **http://localhost:7421**

---

## CLI Usage

```bash
# Alias (optional)
alias nulla="python nulla_cli.py"

nulla create                        # Create new wallet
nulla import word1 word2 ... word24 # Restore from mnemonic
nulla balance                       # Show balance
nulla receive                       # Show your address
nulla send <key_id> 10.0            # Send 10 LAC
nulla send @alice 5.0 --memo "ty"   # Send to username
nulla history --limit 50            # Transaction history
nulla node                          # Node status
nulla faucet                        # Get testnet tokens
nulla accounts                      # List HD accounts

# Options
nulla --node https://my-node.com balance
nulla --keystore /path/to/wallet.nulla balance
```

---

## LAC Integration

`nulla_core.py` is a self-contained library with no LAC-specific imports.
To integrate into `lac_node.py`:

```python
from nulla_core import NullaWallet, NullaKeyPair

# Load wallet
wallet = NullaWallet.load("~/.nulla/wallet.nulla", password)

# Sign a transaction
signature = wallet.sign_transaction(tx_dict)

# E2E encrypt a message
encrypted = wallet.default_keypair().encrypt_to(recipient_x25519_pub, message)
```

---

## Keystore Format

```json
{
  "version": 1,
  "nulla_version": "1.0.0",
  "metadata": { "created": "...", "accounts_derived": 5 },
  "accounts": [{ "index": 0, "path": "m/44'/999'/0'/0'/0'", "key_id": "..." }],
  "crypto": {
    "cipher": "aes-256-gcm",
    "ciphertext": "...",
    "nonce": "...",
    "mac": "...",
    "kdf": "pbkdf2",
    "kdfparams": {
      "iterations": 600000,
      "hash": "sha256",
      "salt": "...",
      "dklen": 32
    }
  }
}
```

---

## Security Notes

- Private keys are derived using SLIP-0010 with **hardened** paths only
  (Ed25519 does not support non-hardened child keys)
- Keystore uses PBKDF2-SHA256 × 600,000 iterations (OWASP 2023 recommendation)
- MAC verification uses `hmac.compare_digest` (constant-time)
- GCM authentication tag validates integrity before decryption
- The server **only binds to 127.0.0.1** — not accessible from network
- `wallet.lock()` overwrites key material before clearing references

---

## Dev Mode (UI hot reload)

```bash
# Terminal 1 — Flask API
python nulla_server.py --no-browser

# Terminal 2 — Vite dev server
cd ui && npm run dev
# Open http://localhost:5173
```

---

## File Structure

```
nulla/
├── nulla_core.py      HD wallet + keystore crypto
├── nulla_node.py      LAC node REST client
├── nulla_cli.py       CLI interface
├── nulla_server.py    Flask server + JSON API
├── requirements.txt
├── README.md
└── ui/
    ├── src/
    │   ├── main.jsx
    │   └── App.jsx    Full React SPA
    ├── index.html
    ├── package.json
    └── vite.config.js
```

---

## License

MIT — part of the LightAnonChain ecosystem.
