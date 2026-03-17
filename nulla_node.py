"""
Nulla Light Client — LAC Node Client
Handles all communication with a LAC node REST API.
Stateless: every method does one job and returns parsed data.
"""

import time
import json
import requests
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

NODE_DEFAULT = "https://lac-beta.uk"
TIMEOUT_DEFAULT = 15
MAX_RETRIES = 3
RETRY_BACKOFF = [1, 2, 4]  # seconds


class NodeError(Exception):
    """Generic node error"""

class NodeConnectionError(NodeError):
    """Cannot reach node"""

class NodeAPIError(NodeError):
    """Node returned an error response"""
    def __init__(self, msg: str, status: int = 0):
        super().__init__(msg)
        self.status = status


class LACNodeClient:
    """
    HTTP client for LAC node REST API.
    Thread-safe (each method creates its own request).
    """

    def __init__(self, url: str = NODE_DEFAULT, timeout: int = TIMEOUT_DEFAULT):
        self.node_url = url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Nulla/1.0.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ── Internal request helpers ──────────────────────────────────────────────

    def _url(self, endpoint: str) -> str:
        return self.node_url + "/" + endpoint.lstrip("/")

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        url = self._url(endpoint)
        last_err = None
        for attempt, backoff in enumerate(RETRY_BACKOFF):
            try:
                resp = self._session.request(method, url, timeout=self.timeout, **kwargs)
                if resp.status_code == 404:
                    raise NodeAPIError(f"Not found: {endpoint}", 404)
                if resp.status_code == 429:
                    raise NodeAPIError("Rate limited", 429)
                if resp.status_code >= 500:
                    raise NodeAPIError(f"Server error {resp.status_code}", resp.status_code)
                resp.raise_for_status()
                try:
                    return resp.json()
                except Exception:
                    return {"raw": resp.text}
            except (requests.ConnectionError, requests.exceptions.SSLError) as e:
                last_err = NodeConnectionError(f"Cannot connect to {self.node_url}: {e}")
            except requests.Timeout:
                last_err = NodeConnectionError(f"Timeout connecting to {self.node_url}")
            except NodeAPIError:
                raise
            except requests.HTTPError as e:
                raise NodeAPIError(str(e), getattr(e.response, "status_code", 0))

            if attempt < len(RETRY_BACKOFF) - 1:
                time.sleep(backoff)

        raise last_err

    def _get(self, endpoint: str, params: dict = None) -> Any:
        return self._request("GET", endpoint, params=params)

    def _post(self, endpoint: str, data: dict) -> Any:
        return self._request("POST", endpoint, json=data)

    # ── Node status ───────────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        """
        Node info: block height, version, peers, etc.
        Tries multiple common LAC endpoints.
        """
        for ep in ["/status", "/node/status", "/info"]:
            try:
                return self._get(ep)
            except NodeAPIError:
                continue
        raise NodeConnectionError(f"No status endpoint found at {self.node_url}")

    def ping(self) -> bool:
        try:
            self.get_status()
            return True
        except NodeError:
            return False

    def get_block_height(self) -> int:
        status = self.get_status()
        for key in ("block_count", "height", "blocks", "chain_length"):
            if key in status:
                return int(status[key])
        return 0

    # ── Balance ───────────────────────────────────────────────────────────────

    def get_balance(self, key_id: str) -> Dict:
        """
        Fetch balance for key_id (64-char LAC public key hex).
        Returns: {key_id, balance, pending, stash}
        """
        result = {}
        for ep in [f"/balance/{key_id}", f"/account/{key_id}"]:
            try:
                result = self._get(ep)
                break
            except NodeAPIError as e:
                if e.status == 404:
                    continue
                raise

        return {
            "key_id": key_id,
            "balance": float(result.get("balance", 0)),
            "pending": float(result.get("pending", 0)),
            "stash": float(result.get("stash", 0)),
            "level": result.get("level", 0),
        }

    # ── Transactions ──────────────────────────────────────────────────────────

    def get_transactions(self, key_id: str, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Transaction history for key_id."""
        for ep in [
            f"/transactions/{key_id}",
            f"/history/{key_id}",
            "/transactions",
        ]:
            try:
                params = {"limit": limit, "offset": offset}
                if ep == "/transactions":
                    params["key_id"] = key_id
                result = self._get(ep, params=params)
                if isinstance(result, list):
                    return result
                if isinstance(result, dict):
                    for key in ("transactions", "history", "items", "data"):
                        if key in result:
                            return result[key]
                return []
            except NodeAPIError as e:
                if e.status == 404:
                    continue
                raise
        return []

    def get_transaction(self, tx_id: str) -> Optional[Dict]:
        try:
            return self._get(f"/transaction/{tx_id}")
        except NodeAPIError:
            return None

    def send_transaction(
        self,
        from_key_id: str,
        to_key_id: str,
        amount: float,
        signature: str,
        fee: float = 0.001,
        memo: str = "",
        tx_type: str = "transfer",
    ) -> Dict:
        """Broadcast a signed transaction."""
        tx: Dict[str, Any] = {
            "from": from_key_id,
            "to": to_key_id,
            "amount": amount,
            "fee": fee,
            "signature": signature,
            "timestamp": int(time.time()),
            "type": tx_type,
        }
        if memo:
            tx["memo"] = memo

        for ep in ["/transaction", "/send", "/broadcast"]:
            try:
                return self._post(ep, tx)
            except NodeAPIError as e:
                if e.status == 404:
                    continue
                raise
        raise NodeAPIError("No transaction endpoint found")

    # ── Messages ──────────────────────────────────────────────────────────────

    def send_message(self, from_key_id: str, to: str, text: str, signature: str = "") -> Dict:
        """Send encrypted message. `to` is key_id or username."""
        payload: Dict[str, Any] = {
            "from": from_key_id,
            "to": to,
            "text": text,
            "timestamp": int(time.time()),
        }
        if signature:
            payload["signature"] = signature
        return self._post("/message", payload)

    def get_messages(self, key_id: str, since: int = 0) -> List[Dict]:
        try:
            result = self._get(f"/messages/{key_id}", params={"since": since})
            if isinstance(result, list):
                return result
            return result.get("messages", [])
        except NodeAPIError:
            return []

    # ── Username registry ─────────────────────────────────────────────────────

    def get_username(self, key_id: str) -> Optional[str]:
        try:
            r = self._get(f"/username/{key_id}")
            return r.get("username")
        except NodeAPIError:
            return None

    def resolve_username(self, username: str) -> Optional[str]:
        """Resolve @username → key_id."""
        username = username.lstrip("@")
        try:
            r = self._get(f"/resolve/{username}")
            return r.get("key_id")
        except NodeAPIError:
            return None

    # ── Faucet (testnet) ──────────────────────────────────────────────────────

    def faucet(self, address: str) -> Dict:
        return self._post("/faucet", {"address": address})

    # ── Mempool ───────────────────────────────────────────────────────────────

    def get_mempool(self) -> List[Dict]:
        try:
            result = self._get("/mempool")
            if isinstance(result, list):
                return result
            return result.get("transactions", result.get("pending", []))
        except NodeAPIError:
            return []

    # ── Connection test ───────────────────────────────────────────────────────

    def test_connection(self) -> Dict:
        """Returns dict with is_connected, latency_ms, block_height."""
        t0 = time.time()
        try:
            status = self.get_status()
            latency = int((time.time() - t0) * 1000)
            height = self.get_block_height()
            return {
                "is_connected": True,
                "latency_ms": latency,
                "block_height": height,
                "node_url": self.node_url,
                "raw": status,
            }
        except NodeError as e:
            return {
                "is_connected": False,
                "error": str(e),
                "node_url": self.node_url,
            }
