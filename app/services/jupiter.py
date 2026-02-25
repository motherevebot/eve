"""Jupiter DEX aggregator — swap SOL → token for buyback."""

import logging

import httpx

logger = logging.getLogger(__name__)

JUPITER_API = "https://api.jup.ag"
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000


async def get_quote(
    input_mint: str,
    output_mint: str,
    amount_lamports: int,
    slippage_bps: int = 100,
) -> dict | None:
    """
    Get a swap quote from Jupiter.
    Returns the full quote response dict or None.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            f"{JUPITER_API}/quote",
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount_lamports),
                "slippageBps": str(slippage_bps),
            },
        )
        if resp.status_code != 200:
            logger.warning("Jupiter quote failed: %s %s", resp.status_code, resp.text[:200])
            return None
        return resp.json()


async def build_swap_tx(
    quote: dict,
    user_public_key: str,
) -> bytes | None:
    """
    Build a swap transaction via Jupiter's /swap endpoint.
    Returns serialized transaction bytes for signing.
    """
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            f"{JUPITER_API}/swap",
            json={
                "quoteResponse": quote,
                "userPublicKey": user_public_key,
                "wrapAndUnwrapSol": True,
            },
        )
        if resp.status_code != 200:
            logger.error("Jupiter swap tx build failed: %s %s", resp.status_code, resp.text[:300])
            return None

        data = resp.json()

    swap_tx = data.get("swapTransaction")
    if not swap_tx:
        logger.error("Jupiter returned no swapTransaction")
        return None

    import base64
    return base64.b64decode(swap_tx)


async def get_sol_price_usd() -> float:
    """Fetch current SOL/USD price via Jupiter price API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{JUPITER_API}/price",
            params={"ids": SOL_MINT},
        )
        if resp.status_code != 200:
            return 0.0
        data = resp.json()

    price_data = data.get("data", {}).get(SOL_MINT, {})
    return float(price_data.get("price", 0.0))


async def get_token_price_usd(mint: str) -> float:
    """Fetch token price in USD via Jupiter price API."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{JUPITER_API}/price",
            params={"ids": mint},
        )
        if resp.status_code != 200:
            return 0.0
        data = resp.json()

    price_data = data.get("data", {}).get(mint, {})
    return float(price_data.get("price", 0.0))
