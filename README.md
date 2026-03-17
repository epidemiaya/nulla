# Nulla — Bitcoin Light Wallet

Мінімалістичний Bitcoin light client у стилі Electrum.
Standalone додаток — пізніше інтегрується в LAC для свапів BTC↔LAC.

## Архітектура

```
nulla_core.py       BIP39/32/44/84 HD wallet, bech32, keystore AES-GCM
nulla_electrum.py   ElectrumX protocol client (SSL TCP, JSON-RPC)
nulla_tx.py         Bitcoin transaction builder (P2WPKH + P2PKH, BIP143)
nulla_cli.py        CLI interface
nulla_server.py     Flask JSON API + React SPA
ui/                 React frontend (Bitcoin orange, dark)
```

## Features

- **BIP39** — 24-word mnemonic (256-bit entropy)
- **BIP84** — Native SegWit (bc1…) addresses
- **BIP44** — Legacy (1…) addresses
- **ElectrumX** — підключення до Bitcoin мережі без повного вузла
- **UTXO** — coin selection, fee estimation, change management
- **BIP143** — правильний sighash для SegWit транзакцій
- **Keystore** — AES-256-GCM + PBKDF2 × 600k + HMAC-SHA256
- **CLI + Web UI** — обидва інтерфейси

## Швидкий старт

```bash
git clone https://github.com/epidemiaya/nulla
cd nulla

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt

# Збірка UI
cd ui && npm install && npm run build && cd ..

# Запуск (відкриє браузер)
python nulla_server.py
```

Відкрий: **http://localhost:7421**

---

## CLI

```bash
python nulla_cli.py create           # Новий гаманець
python nulla_cli.py import word1 ... # Відновлення з мнемоніки
python nulla_cli.py balance          # Баланс
python nulla_cli.py receive          # Адреса для отримання
python nulla_cli.py send bc1q... 0.001  # Відправка
python nulla_cli.py utxos            # Список UTXO
python nulla_cli.py history          # Історія транзакцій
python nulla_cli.py fee              # Поточні fee rates
python nulla_cli.py node             # Статус ElectrumX сервера
python nulla_cli.py accounts         # Всі адреси

# Testnet
python nulla_cli.py --testnet balance
```

---

## ElectrumX сервери (mainnet)

Nulla автоматично вибирає доступний сервер зі списку:
- `electrum.blockstream.info:700`
- `electrum.bitaroo.net:50002`
- `fortress.qtornado.com:443`
- `electrum.jochen-hoenicke.de:50006`
- і ще кілька

---

## Безпека

| Компонент | Деталь |
|-----------|--------|
| secp256k1 | `coincurve` (libsecp256k1, те саме що Bitcoin Core) |
| Підпис | ECDSA deterministic (RFC6979), low-S (BIP62) |
| Keystore | AES-256-GCM, PBKDF2-SHA256 × 600,000 ітерацій |
| MAC | HMAC-SHA256 перед дешифруванням (constant-time compare) |
| Сервер | Bind тільки на 127.0.0.1 |
| Пам'ять | `wallet.lock()` очищає ключі |

---

## Roadmap

- [x] BIP39/84/44 HD wallet
- [x] ElectrumX client
- [x] P2WPKH транзакції
- [x] CLI + Web UI
- [ ] BIP44/49 (P2SH-SegWit) підтримка
- [ ] Hardware wallet (Trezor/Ledger)
- [ ] LAC↔BTC atomic swap модуль

---

## Ліцензія

MIT — частина екосистеми LightAnonChain.
