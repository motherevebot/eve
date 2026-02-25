import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.models import (
    BotProfile,
    BurnEvent,
    FeeClaim,
    ClaimStatus,
    PrincipalLedger,
)
from app.db.session import get_db
from app.schemas import BurnEventOut, FeeClaimOut

router = APIRouter(prefix="/v1/bots", tags=["accounting"])


async def _get_bot_or_404(db: AsyncSession, bot_id: str, owner_id: str) -> BotProfile:
    bot = await db.get(BotProfile, bot_id)
    if not bot or str(bot.owner_id) != owner_id:
        raise HTTPException(404, "Bot not found")
    return bot


@router.get("/{bot_id}/fees", response_model=list[FeeClaimOut])
async def list_fee_claims(
    bot_id: str,
    status: str | None = Query(None, regex="^(pending|confirmed|failed)$"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_bot_or_404(db, bot_id, owner_id)
    q = select(FeeClaim).where(FeeClaim.bot_id == bot_id)
    if status:
        q = q.where(FeeClaim.status == ClaimStatus(status))
    q = q.order_by(FeeClaim.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(q)
    return [FeeClaimOut.model_validate(c) for c in result.scalars().all()]


@router.post("/{bot_id}/fees/claim")
async def trigger_claim(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)

    from app.workers.claim_fees import claim_fees_for_bot
    claim = await claim_fees_for_bot(db, bot)
    await db.commit()

    if claim:
        return {"status": "claimed", "claim_id": str(claim.id), "amount_sol": claim.amount_sol}
    return {"status": "nothing_to_claim"}


@router.get("/{bot_id}/fees/principal")
async def get_principal(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_bot_or_404(db, bot_id, owner_id)
    result = await db.execute(
        select(PrincipalLedger).where(PrincipalLedger.bot_id == bot_id)
    )
    ledger = result.scalar_one_or_none()
    return {
        "bot_id": str(bot_id),
        "running_total_sol": ledger.running_total_sol if ledger else 0.0,
    }


@router.get("/{bot_id}/burns", response_model=list[BurnEventOut])
async def list_burns(
    bot_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    await _get_bot_or_404(db, bot_id, owner_id)
    q = (
        select(BurnEvent)
        .where(BurnEvent.bot_id == bot_id)
        .order_by(BurnEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    return [BurnEventOut.model_validate(b) for b in result.scalars().all()]


@router.post("/{bot_id}/burns/trigger")
async def trigger_buyback_burn(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)

    from app.workers.buyback_burn import buyback_and_burn_for_bot
    ok = await buyback_and_burn_for_bot(db, bot)
    await db.commit()

    return {"status": "burned" if ok else "no_excess_profit"}
