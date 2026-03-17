"""
Nulla Light Client — Core
Standalone cryptographic wallet for LAC blockchain.
Can be imported directly into lac_node.py for native integration.

Security properties:
  - AES-256-GCM keystore encryption
  - PBKDF2-SHA256 × 600,000 (OWASP 2023) key derivation
  - SLIP-0010 HD derivation for Ed25519 (hardened paths)
  - HMAC-SHA256 MAC verification before decryption
  - Constant-time MAC comparison (hmac.compare_digest)
"""

import os
import json
import hashlib
import hmac as _hmac
import secrets
import struct
import time
from typing import Optional, Tuple, Dict, List, Any
from pathlib import Path
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag

try:
    from mnemonic import Mnemonic
    HAS_MNEMONIC = True
except ImportError:
    HAS_MNEMONIC = False

NULLA_VERSION = "1.0.0"
KEYSTORE_VERSION = 1
PBKDF2_ITERATIONS = 600_000
LAC_COIN_TYPE = 999  # BIP44 coin type for LAC


# ── Exceptions ────────────────────────────────────────────────────────────────

class NullaError(Exception):
    """Base exception"""

class KeystoreError(NullaError):
    """Wrong password, corrupted file, version mismatch"""

class WalletError(NullaError):
    """Invalid mnemonic, key derivation failure"""

class CryptoError(NullaError):
    """Encryption/decryption failure"""


# ── SLIP-0010 HD Derivation ───────────────────────────────────────────────────

_SLIP10_SEED = b"ed25519 seed"


def _hmac_sha512(key: bytes, data: bytes) -> bytes:
    return _hmac.new(key, data, hashlib.sha512).digest()


def _derive_master(seed: bytes) -> Tuple[bytes, bytes]:
    """SLIP-0010 master key from seed bytes."""
    I = _hmac_sha512(_SLIP10_SEED, seed)
    return I[:32], I[32:]  # (secret_key, chain_code)


def _derive_child_hardened(parent_key: bytes, parent_chain: bytes, index: int) -> Tuple[bytes, bytes]:
    """
    SLIP-0010 hardened child derivation.
    Ed25519 ONLY supports hardened derivation (index | 0x80000000).
    """
    index_h = index | 0x80000000
    data = b"\x00" + parent_key + struct.pack(">I", index_h)
    I = _hmac_sha512(parent_chain, data)
    return I[:32], I[32:]


def derive_key_from_path(seed: bytes, path: str = "m/44'/999'/0'/0'/0'") -> bytes:
    """
    Derive Ed25519 private key from seed using SLIP-0010 path.
    All components are hardened (required for Ed25519).
    """
    key, chain = _derive_master(seed)
    parts = path.replace("m/", "").split("/")
    for part in parts:
        if not part:
            continue
        index = int(part.replace("'", ""))
        key, chain = _derive_child_hardened(key, chain, index)
    return key


# ── Keystore Crypto ───────────────────────────────────────────────────────────

def _pbkdf2_key(password: str, salt: bytes) -> bytes:
    """Derive 32-byte AES key from password."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(password.encode("utf-8"))


def _aes_gcm_encrypt(key: bytes, plaintext: bytes) -> Tuple[bytes, bytes]:
    """AES-256-GCM encrypt. Returns (nonce, ciphertext_with_tag)."""
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return nonce, ct


def _aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """AES-256-GCM decrypt. Raises CryptoError on auth failure."""
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except InvalidTag:
        raise CryptoError("GCM authentication tag mismatch — wrong key or tampered data")


# ── Key Pair ──────────────────────────────────────────────────────────────────

class NullaKeyPair:
    """
    Ed25519 + X25519 key pair from 32-byte seed.
    Compatible with lac_crypto.py key format.
    """

    __slots__ = ("_seed", "_ed_priv", "_x_priv")

    def __init__(self, seed_32: bytes):
        if len(seed_32) != 32:
            raise WalletError(f"Expected 32-byte seed, got {len(seed_32)}")
        self._seed = seed_32
        self._ed_priv = Ed25519PrivateKey.from_private_bytes(seed_32)
        self._x_priv = X25519PrivateKey.from_private_bytes(seed_32)

    # ── Public key accessors ──────────────────────────────────────────────────

    @property
    def ed25519_pub_bytes(self) -> bytes:
        return self._ed_priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    @property
    def x25519_pub_bytes(self) -> bytes:
        return self._x_priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    @property
    def key_id(self) -> str:
        """
        LAC-compatible key_id: hex of Ed25519 public key (64 hex chars).
        This is the primary identity in LAC's UTXO/account model.
        """
        return self.ed25519_pub_bytes.hex()

    @property
    def address(self) -> str:
        """
        Alias for key_id. In LAC the full pubkey IS the address.
        Short display via address[:16] + '...' + address[-8:]
        """
        return self.key_id

    @property
    def address_short(self) -> str:
        a = self.key_id
        return f"{a[:12]}...{a[-8:]}"

    # ── Signing ───────────────────────────────────────────────────────────────

    def sign(self, message: bytes) -> bytes:
        return self._ed_priv.sign(message)

    def sign_hex(self, message: bytes) -> str:
        return self.sign(message).hex()

    def sign_json(self, data: dict) -> str:
        """Sign canonical JSON of dict, return signature hex."""
        payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
        return self.sign_hex(payload)

    # ── E2E Encryption ────────────────────────────────────────────────────────

    def encrypt_to(self, recipient_x25519_pub_bytes: bytes, plaintext: bytes) -> bytes:
        """
        X25519 ECDH + HKDF-SHA256 + AES-256-GCM.
        Wire format: nonce(12) || ciphertext_with_tag
        """
        recipient_pub = X25519PublicKey.from_public_bytes(recipient_x25519_pub_bytes)
        shared = self._x_priv.exchange(recipient_pub)
        sym_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None,
            info=b"nulla-e2e-v1", backend=default_backend()
        ).derive(shared)
        nonce, ct = _aes_gcm_encrypt(sym_key, plaintext)
        return nonce + ct

    def decrypt_from(self, sender_x25519_pub_bytes: bytes, data: bytes) -> bytes:
        """Decrypt message encrypted with encrypt_to."""
        sender_pub = X25519PublicKey.from_public_bytes(sender_x25519_pub_bytes)
        shared = self._x_priv.exchange(sender_pub)
        sym_key = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None,
            info=b"nulla-e2e-v1", backend=default_backend()
        ).derive(shared)
        return _aes_gcm_decrypt(sym_key, data[:12], data[12:])

    def wipe(self):
        """Overwrite sensitive material (best-effort in Python)."""
        self._seed = b"\x00" * 32


# ── Wallet ─────────────────────────────────────────────────────────────────────

class NullaWallet:
    """
    BIP39 HD wallet with encrypted keystore persistence.

    Usage:
        wallet = NullaWallet.generate("mypassword")
        wallet.save("~/.nulla/wallet.nulla", "mypassword")

        wallet = NullaWallet.load("~/.nulla/wallet.nulla", "mypassword")
        wallet.default_keypair().sign(b"hello")
    """

    def __init__(self):
        self._keypairs: Dict[str, NullaKeyPair] = {}
        self._mnemonic: Optional[str] = None
        self._seed: Optional[bytes] = None
        self._unlocked: bool = False
        self.metadata: Dict[str, Any] = {}

    # ── Factory methods ───────────────────────────────────────────────────────

    @classmethod
    def generate(cls, password: str, words: int = 24) -> "NullaWallet":
        """Generate new wallet with BIP39 mnemonic."""
        w = cls()
        if HAS_MNEMONIC:
            mnemo = Mnemonic("english")
            strength = 256 if words >= 24 else 128
            w._mnemonic = mnemo.generate(strength=strength)
            w._seed = Mnemonic.to_seed(w._mnemonic, passphrase="")
        else:
            # Fallback: raw 32-byte entropy (no BIP39)
            entropy = secrets.token_bytes(32)
            w._seed = entropy
            w._mnemonic = entropy.hex()

        w._derive_accounts(count=5)
        w._unlocked = True
        w.metadata = {
            "created": datetime.utcnow().isoformat() + "Z",
            "nulla_version": NULLA_VERSION,
            "accounts_derived": 5,
            "has_bip39": HAS_MNEMONIC,
        }
        return w

    @classmethod
    def from_mnemonic(cls, mnemonic: str, password: str) -> "NullaWallet":
        """Restore wallet from mnemonic phrase."""
        w = cls()
        mnemonic = mnemonic.strip()
        if HAS_MNEMONIC:
            mnemo = Mnemonic("english")
            if not mnemo.check(mnemonic):
                raise WalletError("Invalid BIP39 mnemonic (checksum failed)")
            w._seed = Mnemonic.to_seed(mnemonic, passphrase="")
        else:
            try:
                w._seed = bytes.fromhex(mnemonic)
            except ValueError:
                raise WalletError("Invalid mnemonic (expected hex without bip_utils installed)")

        w._mnemonic = mnemonic
        w._derive_accounts(count=5)
        w._unlocked = True
        w.metadata = {
            "restored": datetime.utcnow().isoformat() + "Z",
            "nulla_version": NULLA_VERSION,
            "accounts_derived": 5,
        }
        return w

    # ── Key derivation ────────────────────────────────────────────────────────

    def _path_for(self, index: int) -> str:
        return f"m/44'/{LAC_COIN_TYPE}'/0'/0'/{index}'"

    def _derive_accounts(self, count: int = 5):
        if self._seed is None:
            raise WalletError("No seed available")
        for i in range(count):
            path = self._path_for(i)
            if path not in self._keypairs:
                priv = derive_key_from_path(self._seed, path)
                self._keypairs[path] = NullaKeyPair(priv)

    def derive_more(self, total: int = 10):
        """Derive additional accounts."""
        self._require_unlocked()
        self._derive_accounts(total)

    def _require_unlocked(self):
        if not self._unlocked:
            raise WalletError("Wallet is locked")

    # ── Accessors ─────────────────────────────────────────────────────────────

    def default_keypair(self) -> NullaKeyPair:
        self._require_unlocked()
        return self._keypairs[self._path_for(0)]

    def keypair_at(self, index: int) -> NullaKeyPair:
        self._require_unlocked()
        path = self._path_for(index)
        if path not in self._keypairs:
            self._derive_accounts(index + 1)
        return self._keypairs[path]

    @property
    def address(self) -> str:
        return self.default_keypair().address

    @property
    def key_id(self) -> str:
        return self.default_keypair().key_id

    @property
    def mnemonic(self) -> Optional[str]:
        self._require_unlocked()
        return self._mnemonic

    def all_accounts(self) -> List[Dict]:
        self._require_unlocked()
        return [
            {
                "index": i,
                "path": self._path_for(i),
                "key_id": kp.key_id,
                "address": kp.address,
                "address_short": kp.address_short,
            }
            for i, kp in enumerate(self._keypairs.values())
        ]

    # ── Transaction signing ───────────────────────────────────────────────────

    def sign_transaction(self, tx: dict) -> str:
        """Sign canonical JSON of transaction dict. Returns hex signature."""
        self._require_unlocked()
        return self.default_keypair().sign_json(tx)

    # ── Keystore: save ────────────────────────────────────────────────────────

    def save(self, filepath: str, password: str) -> None:
        """
        Encrypt and save wallet to file.
        Format: JSON keystore (similar to Ethereum keystore v3 but with HMAC).
        """
        self._require_unlocked()

        salt = secrets.token_bytes(32)
        aes_key = _pbkdf2_key(password, salt)

        secret_blob = json.dumps({
            "mnemonic": self._mnemonic,
            "seed_hex": self._seed.hex() if self._seed else None,
        }).encode("utf-8")

        nonce, ciphertext = _aes_gcm_encrypt(aes_key, secret_blob)

        # Additional HMAC-SHA256 over (salt + nonce + ciphertext) for belt-and-suspenders
        mac = _hmac.new(aes_key, salt + nonce + ciphertext, hashlib.sha256).hexdigest()

        keystore = {
            "version": KEYSTORE_VERSION,
            "nulla_version": NULLA_VERSION,
            "metadata": self.metadata,
            "accounts": self.all_accounts(),
            "crypto": {
                "cipher": "aes-256-gcm",
                "ciphertext": ciphertext.hex(),
                "nonce": nonce.hex(),
                "mac": mac,
                "kdf": "pbkdf2",
                "kdfparams": {
                    "iterations": PBKDF2_ITERATIONS,
                    "hash": "sha256",
                    "salt": salt.hex(),
                    "dklen": 32,
                },
            },
        }

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temp file
        tmp = str(path) + ".tmp"
        with open(tmp, "w") as f:
            json.dump(keystore, f, indent=2)
        os.replace(tmp, str(path))

    # ── Keystore: load ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, filepath: str, password: str) -> "NullaWallet":
        """Decrypt and load wallet from keystore file."""
        try:
            with open(filepath, "r") as f:
                ks = json.load(f)
        except FileNotFoundError:
            raise KeystoreError(f"Keystore not found: {filepath}")
        except json.JSONDecodeError:
            raise KeystoreError("Corrupted keystore (invalid JSON)")

        v = ks.get("version")
        if v != KEYSTORE_VERSION:
            raise KeystoreError(f"Unsupported keystore version {v!r}")

        crypto = ks["crypto"]
        params = crypto["kdfparams"]

        salt = bytes.fromhex(params["salt"])
        aes_key = _pbkdf2_key(password, salt)

        ciphertext = bytes.fromhex(crypto["ciphertext"])
        nonce = bytes.fromhex(crypto["nonce"])

        # Verify MAC before decryption (timing-safe)
        expected_mac = _hmac.new(aes_key, salt + nonce + ciphertext, hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(expected_mac, crypto["mac"]):
            raise KeystoreError("Wrong password or corrupted keystore (MAC mismatch)")

        try:
            plaintext = _aes_gcm_decrypt(aes_key, nonce, ciphertext)
        except CryptoError:
            raise KeystoreError("Decryption failed (GCM tag invalid)")

        secret = json.loads(plaintext)

        w = cls()
        w._mnemonic = secret.get("mnemonic")
        seed_hex = secret.get("seed_hex")
        w._seed = bytes.fromhex(seed_hex) if seed_hex else None
        w.metadata = ks.get("metadata", {})
        w._derive_accounts(count=len(ks.get("accounts", [])) or 5)
        w._unlocked = True
        return w

    # ── Lock ──────────────────────────────────────────────────────────────────

    def lock(self):
        """Wipe sensitive data from memory and lock the wallet."""
        for kp in self._keypairs.values():
            kp.wipe()
        self._keypairs.clear()
        if self._seed:
            self._seed = b"\x00" * len(self._seed)
            self._seed = None
        self._mnemonic = None
        self._unlocked = False


# ── Utilities ──────────────────────────────────────────────────────────────────

def validate_key_id(key_id: str) -> bool:
    """LAC key_id is 64 hex chars (32-byte Ed25519 pubkey)."""
    if len(key_id) != 64:
        return False
    try:
        int(key_id, 16)
        return True
    except ValueError:
        return False


def format_lac(amount: float, decimals: int = 4) -> str:
    return f"{amount:,.{decimals}f} LAC"
