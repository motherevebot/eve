"""Worker: claim creator fees from pump.fun for all armed/live bots."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    BotProfile,
    BotStage,
    BotWallet,
    FeeClaim,
    ClaimStatus,
    LinkedToken,
    PrincipalLedger,
)
from app.services.pump_portal import get_claimable_fees, build_claim_tx
from app.services.solana_rpc import send_raw_transaction, confirm_transaction
from app.services.wallet import sign_transaction

logger = logging.getLogger(__name__)


async def claim_fees_for_bot(db: AsyncSession, bot: BotProfile) -> FeeClaim | None:
    """Attempt to claim fees for a single bot."""
    wallet: BotWallet | None = bot.wallet
    token: LinkedToken | None = bot.linked_token

    if not wallet or not token:
        return None

    claimable = await get_claimable_fees(token.mint, wallet.public_key)
    if claimable <= 0:
        logger.debug("Bot %s: nothing to claim", bot.name)
        return None

    logger.info("Bot %s: claimable %.6f SOL from %s", bot.name, claimable, token.mint)

    raw_tx = await build_claim_tx(token.mint, wallet.public_key)
    if not raw_tx:
        logger.error("Bot %s: failed to build claim tx", bot.name)
        return None

    claim = FeeClaim(
        bot_id=bot.id,
        amount_sol=claimable,
        status=ClaimStatus.PENDING,
    )
    db.add(claim)
    await db.flush()

    try:
        signed = sign_transaction(raw_tx, wallet.encrypted_private_key)
        signature = await send_raw_transaction(signed)
        confirmed = await confirm_transaction(signature)

        claim.tx_signature = signature
        claim.status = ClaimStatus.CONFIRMED if confirmed else ClaimStatus.FAILED
    except Exception:
        logger.exception("Bot %s: claim tx failed", bot.name)
        claim.status = ClaimStatus.FAILED

    await db.flush()

    if claim.status == ClaimStatus.CONFIRMED:
        await _update_principal(db, bot.id, claim)

    return claim


async def _update_principal(db: AsyncSession, bot_id: uuid.UUID, claim: FeeClaim):
    result = await db.execute(
        select(PrincipalLedger).where(PrincipalLedger.bot_id == bot_id)
    )
    ledger = result.scalar_one_or_none()

    if ledger:
        ledger.running_total_sol += claim.amount_sol
        ledger.last_claim_id = claim.id
    else:
        ledger = PrincipalLedger(
            bot_id=bot_id,
            running_total_sol=claim.amount_sol,
            last_claim_id=claim.id,
        )
        db.add(ledger)


async def run_claim_fees_job(db: AsyncSession):
    result = await db.execute(
        select(BotProfile).where(
            BotProfile.stage.in_([BotStage.TRADING_ARMED, BotStage.LIVE])
        )
    )
    bots = result.scalars().all()
    logger.info("claim_fees_job: processing %d bots", len(bots))

    claimed = 0
    for bot in bots:
        claim = await claim_fees_for_bot(db, bot)
        if claim:
            claimed += 1

    await db.commit()
    logger.info("claim_fees_job: claimed for %d/%d bots", claimed, len(bots))
