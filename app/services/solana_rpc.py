"""Solana RPC helpers — using httpx for async JSON-RPC calls."""

import asyncio
import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
_LAMPORTS_PER_SOL = 1_000_000_000


async def _rpc_call(method: str, params: list) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.solana_rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        resp.raise_for_status()
        return resp.json()


async def get_sol_balance(pubkey: str) -> float:
    data = await _rpc_call("getBalance", [pubkey])
    lamports = data.get("result", {}).get("value", 0)
    return lamports / _LAMPORTS_PER_SOL


async def get_token_balance(pubkey: str, mint: str) -> float:
    data = await _rpc_call(
        "getTokenAccountsByOwner",
        [pubkey, {"mint": mint}, {"encoding": "jsonParsed"}],
    )
    accounts = data.get("result", {}).get("value", [])
    if not accounts:
        return 0.0
    info = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]
    return float(info.get("uiAmount", 0) or 0)


async def get_latest_blockhash() -> str:
    data = await _rpc_call("getLatestBlockhash", [{"commitment": "finalized"}])
    return data["result"]["value"]["blockhash"]


async def send_raw_transaction(raw_tx: bytes) -> str:
    encoded = base64.b64encode(raw_tx).decode()
    data = await _rpc_call("sendTransaction", [encoded, {"encoding": "base64"}])
    if "error" in data:
        raise RuntimeError(f"sendTransaction failed: {data['error']}")
    return data["result"]


async def confirm_transaction(signature: str, timeout_sec: int = 60) -> bool:
    for _ in range(timeout_sec // 2):
        data = await _rpc_call("getSignatureStatuses", [[signature]])
        statuses = data.get("result", {}).get("value", [None])
        if statuses[0] is not None:
            s = statuses[0]
            if s.get("err") is not None:
                return False
            if s.get("confirmationStatus") in ("confirmed", "finalized"):
                return True
        await asyncio.sleep(2)
    return False


async def get_token_supply(mint: str) -> dict:
    """Get token supply info — returns {amount, decimals, uiAmount}."""
    data = await _rpc_call("getTokenSupply", [mint])
    return data.get("result", {}).get("value", {})
