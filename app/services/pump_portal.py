"""
Pump.fun integration — fee balance checks and claim transaction building.
Calls the Next.js launcher service which wraps the official @pump-fun/pump-sdk.
"""

import base64
import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def get_claimable_fees(mint: str, creator_wallet: str) -> float:
    """
    Check total claimable creator fees (from both Pump and PumpSwap programs)
    via the launcher service's /api/pump/fee-balance endpoint.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{settings.launcher_service_url}/api/pump/fee-balance",
                params={"creator": creator_wallet},
            )
            if resp.status_code != 200:
                logger.warning(
                    "fee-balance check failed: %d %s", resp.status_code, resp.text[:200]
                )
                return 0.0

            data = resp.json()
            return float(data.get("balance_sol", 0.0))

    except httpx.ConnectError:
        logger.warning("Launcher service not reachable for fee-balance")
        return 0.0
    except Exception:
        logger.exception("get_claimable_fees failed")
        return 0.0


async def build_claim_tx(mint: str, creator_wallet: str) -> bytes | None:
    """
    Build a collectCoinCreatorFee transaction via the launcher service's
    /api/pump/build-claim-fees endpoint.
    Returns serialized unsigned transaction bytes for signing, or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{settings.launcher_service_url}/api/pump/build-claim-fees",
                json={"creator": creator_wallet},
            )
            if resp.status_code == 404:
                logger.debug("No claimable fees for %s", creator_wallet)
                return None
            if resp.status_code != 200:
                logger.error(
                    "build-claim-fees failed: %d %s", resp.status_code, resp.text[:300]
                )
                return None

            data = resp.json()

        tx_b64 = data.get("tx")
        if not tx_b64:
            logger.error("Launcher returned no transaction data")
            return None

        return base64.b64decode(tx_b64)

    except httpx.ConnectError:
        logger.warning("Launcher service not reachable for build-claim-fees")
        return None
    except Exception:
        logger.exception("build_claim_tx failed")
        return None
