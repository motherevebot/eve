"""Worker: compute excess profit → buyback token via Jupiter → burn tokens."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models import (
    BotProfile,
    BotStage,
    BotWallet,
    BurnEvent,
    BurnStatus,
    BuybackSwap,
    LinkedToken,
    PrincipalLedger,
    SwapStatus,
)
from app.services.jupiter import (
    LAMPORTS_PER_SOL,
    SOL_MINT,
    build_swap_tx,
    get_quote,
)
from app.services.solana_rpc import (
    confirm_transaction,
    get_sol_balance,
    send_raw_transaction,
)
from app.services.token_ops import build_burn_tx
from app.services.wallet import sign_transaction

logger = logging.getLogger(__name__)


async def _get_principal(db: AsyncSession, bot_id: uuid.UUID) -> float:
    result = await db.execute(
        select(PrincipalLedger.running_total_sol).where(PrincipalLedger.bot_id == bot_id)
    )
    return result.scalar_one_or_none() or 0.0


async def compute_excess_profit(db: AsyncSession, bot: BotProfile) -> float:
    wallet: BotWallet | None = bot.wallet
    if not wallet:
        return 0.0

    sol_balance = await get_sol_balance(wallet.public_key)
    principal = await _get_principal(db, bot.id)
    reserve = wallet.reserve_sol or settings.reserve_sol

    excess = sol_balance - principal - reserve
    logger.debug(
        "Bot %s: balance=%.6f principal=%.6f reserve=%.6f excess=%.6f",
        bot.name, sol_balance, principal, reserve, excess,
    )
    return max(excess, 0.0)


async def buyback_and_burn_for_bot(db: AsyncSession, bot: BotProfile) -> bool:
    wallet: BotWallet | None = bot.wallet
    token: LinkedToken | None = bot.linked_token
    if not wallet or not token:
        return False

    excess = await compute_excess_profit(db, bot)
    if excess < settings.excess_profit_threshold_sol:
        logger.debug("Bot %s: excess %.6f below threshold", bot.name, excess)
        return False

    buyback_sol = min(excess, settings.max_buyback_sol)
    amount_lamports = int(buyback_sol * LAMPORTS_PER_SOL)

    logger.info("Bot %s: buyback %.6f SOL → %s", bot.name, buyback_sol, token.symbol)

    # ── Step 1: Jupiter quote + swap ──────────────────────────────
    quote = await get_quote(
        input_mint=SOL_MINT,
        output_mint=token.mint,
        amount_lamports=amount_lamports,
        slippage_bps=150,
    )
    if not quote:
        logger.error("Bot %s: Jupiter quote failed", bot.name)
        return False

    out_amount = int(quote.get("outAmount", 0))

    swap_record = BuybackSwap(
        bot_id=bot.id,
        input_amount_sol=buyback_sol,
        output_amount_token=out_amount,
        slippage_bps=150,
        status=SwapStatus.PENDING,
    )
    db.add(swap_record)
    await db.flush()

    swap_tx = await build_swap_tx(quote, wallet.public_key)
    if not swap_tx:
        swap_record.status = SwapStatus.FAILED
        await db.flush()
        return False

    try:
        signed = sign_transaction(swap_tx, wallet.encrypted_private_key)
        sig = await send_raw_transaction(signed)
        confirmed = await confirm_transaction(sig)
        swap_record.tx_signature = sig
        swap_record.status = SwapStatus.CONFIRMED if confirmed else SwapStatus.FAILED
    except Exception:
        logger.exception("Bot %s: swap tx failed", bot.name)
        swap_record.status = SwapStatus.FAILED
        await db.flush()
        return False

    await db.flush()

    if swap_record.status != SwapStatus.CONFIRMED:
        return False

    logger.info("Bot %s: swap confirmed, out=%d tokens", bot.name, out_amount)

    # ── Step 2: Burn the bought tokens ────────────────────────────
    burn_record = BurnEvent(
        bot_id=bot.id,
        amount_burned=out_amount,
        mint=token.mint,
        status=BurnStatus.PENDING,
    )
    db.add(burn_record)
    await db.flush()

    burn_tx_bytes = await build_burn_tx(
        owner_pubkey=wallet.public_key,
        mint=token.mint,
        amount_raw=out_amount,
        token_program=token.token_program,
    )

    if burn_tx_bytes:
        try:
            signed_burn = sign_transaction(burn_tx_bytes, wallet.encrypted_private_key)
            burn_sig = await send_raw_transaction(signed_burn)
            burn_ok = await confirm_transaction(burn_sig)
            burn_record.tx_signature = burn_sig
            burn_record.status = BurnStatus.CONFIRMED if burn_ok else BurnStatus.FAILED
        except Exception:
            logger.exception("Bot %s: burn tx failed", bot.name)
            burn_record.status = BurnStatus.FAILED
    else:
        burn_record.status = BurnStatus.FAILED

    await db.flush()
    return burn_record.status == BurnStatus.CONFIRMED


async def run_buyback_burn_job(db: AsyncSession):
    result = await db.execute(
        select(BotProfile).where(
            BotProfile.stage.in_([BotStage.TRADING_ARMED, BotStage.LIVE])
        )
    )
    bots = result.scalars().all()
    logger.info("buyback_burn_job: processing %d bots", len(bots))

    burned = 0
    for bot in bots:
        ok = await buyback_and_burn_for_bot(db, bot)
        if ok:
            burned += 1

    await db.commit()
    logger.info("buyback_burn_job: burned for %d/%d bots", burned, len(bots))
