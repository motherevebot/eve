"""DexScreener API — fetch real-time token market data."""

import logging

import httpx

logger = logging.getLogger(__name__)

DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"


async def get_token_data(mint: str) -> dict | None:
    """
    Fetch token market data from DexScreener.
    Returns dict with keys: price_usd, mcap_usd, volume_24h_usd, liquidity_usd, status.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{DEXSCREENER_API}/tokens/{mint}")
            if resp.status_code != 200:
                logger.warning("DexScreener %s: %d", mint, resp.status_code)
                return None
            data = resp.json()

        pairs = data.get("pairs") or []
        if not pairs:
            return None

        # Use the highest-liquidity pair
        pair = max(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))

        price = float(pair.get("priceUsd", 0) or 0)
        mcap = float(pair.get("marketCap", 0) or 0)
        # fdv as fallback for mcap
        if mcap == 0:
            mcap = float(pair.get("fdv", 0) or 0)
        volume_24h = float(pair.get("volume", {}).get("h24", 0) or 0)
        liquidity = float(pair.get("liquidity", {}).get("usd", 0) or 0)

        # Graduated if listed on Raydium/Orca, bonding if only on pump.fun
        dex_id = pair.get("dexId", "").lower()
        if dex_id in ("raydium", "orca", "meteora"):
            status = "graduated"
        elif "pump" in dex_id:
            status = "bonding"
        else:
            status = "unknown"

        return {
            "price_usd": price,
            "mcap_usd": mcap,
            "volume_24h_usd": volume_24h,
            "liquidity_usd": liquidity,
            "status": status,
        }

    except Exception:
        logger.exception("DexScreener fetch failed for %s", mint)
        return None
