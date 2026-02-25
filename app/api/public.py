from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.db.models import (
    AgentSnapshot,
    BotProfile,
    BotStage,
    BurnEvent,
    BurnStatus,
    FeeClaim,
    ClaimStatus,
    LinkedToken,
    TokenSnapshot,
    TokenStatus,
    User,
)
from app.db.session import get_db
from app.schemas import (
    AgentLeaderboardResponse,
    AgentLeaderboardRow,
    LeaderboardSummary,
    TokenLeaderboardResponse,
    TokenLeaderboardRow,
)

router = APIRouter(prefix="/v1/public", tags=["public"])


# ── KPI Summary ────────────────────────────────────────────────────


@router.get("/leaderboard/summary", response_model=LeaderboardSummary)
async def leaderboard_summary(db: AsyncSession = Depends(get_db)):
    agents_count = (
        await db.scalar(select(func.count()).select_from(BotProfile))
    ) or 0

    tokens_count = (await db.scalar(select(func.count()).select_from(LinkedToken))) or 0

    earnings_paid = (
        await db.scalar(
            select(func.coalesce(func.sum(FeeClaim.amount_sol), 0.0)).where(
                FeeClaim.status == ClaimStatus.CONFIRMED
            )
        )
    ) or 0.0

    latest_snap = (
        select(
            TokenSnapshot.mint,
            func.max(TokenSnapshot.captured_at).label("max_t"),
        )
        .group_by(TokenSnapshot.mint)
        .subquery()
    )
    snap_q = (
        select(
            func.coalesce(func.sum(TokenSnapshot.mcap_usd), 0.0).label("total_mcap"),
            func.coalesce(func.sum(TokenSnapshot.volume_24h_usd), 0.0).label("total_vol"),
        )
        .join(
            latest_snap,
            (TokenSnapshot.mint == latest_snap.c.mint)
            & (TokenSnapshot.captured_at == latest_snap.c.max_t),
        )
    )
    snap_row = (await db.execute(snap_q)).one_or_none()
    total_mcap = snap_row.total_mcap if snap_row else 0.0
    total_vol = snap_row.total_vol if snap_row else 0.0

    top_agent_q = (
        select(
            BotProfile.name,
            func.coalesce(func.sum(FeeClaim.amount_sol), 0.0).label("earnings"),
        )
        .join(FeeClaim, FeeClaim.bot_id == BotProfile.id)
        .where(FeeClaim.status == ClaimStatus.CONFIRMED)
        .group_by(BotProfile.id, BotProfile.name)
        .order_by(func.sum(FeeClaim.amount_sol).desc())
        .limit(1)
    )
    top_agent = (await db.execute(top_agent_q)).one_or_none()

    top_token_q = (
        select(LinkedToken.name, TokenSnapshot.mcap_usd)
        .join(latest_snap, TokenSnapshot.mint == latest_snap.c.mint)
        .join(LinkedToken, LinkedToken.mint == TokenSnapshot.mint)
        .where(TokenSnapshot.captured_at == latest_snap.c.max_t)
        .order_by(TokenSnapshot.mcap_usd.desc())
        .limit(1)
    )
    top_token = (await db.execute(top_token_q)).one_or_none()

    return LeaderboardSummary(
        agents_count=agents_count,
        tokens_count=tokens_count,
        earnings_paid_sol=earnings_paid,
        total_mcap_usd=total_mcap,
        volume_24h_usd=total_vol,
        total_launches=tokens_count,
        top_agent_name=top_agent.name if top_agent else None,
        top_agent_earnings_sol=top_agent.earnings if top_agent else 0.0,
        top_token_name=top_token.name if top_token else None,
        top_token_mcap_usd=top_token.mcap_usd if top_token else 0.0,
    )


# ── Agent Leaderboard ──────────────────────────────────────────────


@router.get("/leaderboard/agents", response_model=AgentLeaderboardResponse)
async def leaderboard_agents(
    sort: str = Query("earnings", regex="^(earnings|name|newest)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, le=100),
    db: AsyncSession = Depends(get_db),
):
    base = (
        select(
            BotProfile.id.label("bot_id"),
            BotProfile.name,
            BotProfile.stage,
            BotProfile.created_at,
            func.coalesce(func.sum(FeeClaim.amount_sol), 0.0).label("earnings"),
        )
        .outerjoin(FeeClaim, (FeeClaim.bot_id == BotProfile.id) & (FeeClaim.status == ClaimStatus.CONFIRMED))
        .group_by(BotProfile.id, BotProfile.name, BotProfile.stage, BotProfile.created_at)
    )

    sub = base.subquery()

    total_matched = (await db.scalar(select(func.count()).select_from(sub))) or 0
    total_earnings_sol = (
        await db.scalar(select(func.coalesce(func.sum(sub.c.earnings), 0.0)))
    ) or 0.0

    sort_map = {
        "earnings": sub.c.earnings.desc(),
        "name": sub.c.name.asc(),
        "newest": sub.c.created_at.desc(),
    }
    order = sort_map.get(sort, sub.c.earnings.desc())
    rows_q = (
        select(sub).order_by(order).offset((page - 1) * page_size).limit(page_size)
    )
    rows = (await db.execute(rows_q)).all()

    items = [
        AgentLeaderboardRow(
            rank=(page - 1) * page_size + i + 1,
            bot_id=r.bot_id,
            name=r.name,
            earnings_sol=r.earnings,
            sol_per_token=r.earnings,
            stage=r.stage.value if hasattr(r.stage, "value") else str(r.stage),
        )
        for i, r in enumerate(rows)
    ]

    avg = total_earnings_sol / total_matched if total_matched else 0.0

    return AgentLeaderboardResponse(
        items=items,
        total_matched=total_matched,
        total_earnings_sol=total_earnings_sol,
        avg_earnings_sol=avg,
        page=page,
        page_size=page_size,
    )


# ── Token Leaderboard ──────────────────────────────────────────────


@router.get("/leaderboard/tokens", response_model=TokenLeaderboardResponse)
async def leaderboard_tokens(
    sort: str = Query("mcap", regex="^(mcap|price|volume|newest)$"),
    status: str = Query("all", regex="^(all|graduated|bonding)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, le=100),
    db: AsyncSession = Depends(get_db),
):
    latest_snap = (
        select(
            TokenSnapshot.mint,
            func.max(TokenSnapshot.captured_at).label("max_t"),
        )
        .group_by(TokenSnapshot.mint)
        .subquery()
    )

    base = (
        select(
            LinkedToken.mint,
            LinkedToken.symbol,
            LinkedToken.name,
            LinkedToken.image_url,
            LinkedToken.created_at,
            func.coalesce(TokenSnapshot.mcap_usd, 0.0).label("mcap_usd"),
            func.coalesce(TokenSnapshot.price_usd, 0.0).label("price_usd"),
            func.coalesce(TokenSnapshot.volume_24h_usd, 0.0).label("volume_24h_usd"),
            func.coalesce(
                TokenSnapshot.status,
                literal(TokenStatus.UNKNOWN.value),
            ).label("status"),
        )
        .outerjoin(latest_snap, LinkedToken.mint == latest_snap.c.mint)
        .outerjoin(
            TokenSnapshot,
            (TokenSnapshot.mint == latest_snap.c.mint)
            & (TokenSnapshot.captured_at == latest_snap.c.max_t),
        )
    )

    if status == "graduated":
        base = base.where(TokenSnapshot.status == TokenStatus.GRADUATED)
    elif status == "bonding":
        base = base.where(TokenSnapshot.status == TokenStatus.BONDING)

    sub = base.subquery()
    total_matched = (await db.scalar(select(func.count()).select_from(sub))) or 0

    agg = await db.execute(
        select(
            func.coalesce(func.sum(sub.c.mcap_usd), 0.0),
            func.coalesce(func.sum(sub.c.volume_24h_usd), 0.0),
        )
    )
    agg_row = agg.one()
    total_mcap = agg_row[0]
    total_vol = agg_row[1]

    sort_map = {
        "mcap": sub.c.mcap_usd.desc(),
        "price": sub.c.price_usd.desc(),
        "volume": sub.c.volume_24h_usd.desc(),
        "newest": sub.c.created_at.desc(),
    }
    rows = (
        await db.execute(
            select(sub)
            .order_by(sort_map.get(sort, sub.c.mcap_usd.desc()))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()

    items = [
        TokenLeaderboardRow(
            rank=(page - 1) * page_size + i + 1,
            mint=r.mint,
            symbol=r.symbol,
            name=r.name,
            image_url=r.image_url,
            mcap_usd=r.mcap_usd,
            price_usd=r.price_usd,
            volume_24h_usd=r.volume_24h_usd,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
        )
        for i, r in enumerate(rows)
    ]

    return TokenLeaderboardResponse(
        items=items,
        total_matched=total_matched,
        total_mcap_usd=total_mcap,
        total_volume_24h_usd=total_vol,
        graduated_count=0,
        page=page,
        page_size=page_size,
    )


# ── Single Token Detail ───────────────────────────────────────────


@router.get("/tokens/{mint}")
async def get_token_detail(mint: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(LinkedToken).where(LinkedToken.mint == mint)
    )
    token = result.scalar_one_or_none()
    if not token:
        raise HTTPException(404, "Token not found")

    # Latest snapshot
    snap_result = await db.execute(
        select(TokenSnapshot)
        .where(TokenSnapshot.mint == mint)
        .order_by(TokenSnapshot.captured_at.desc())
        .limit(1)
    )
    snapshot = snap_result.scalar_one_or_none()

    # Bot info
    bot_result = await db.execute(
        select(BotProfile).where(BotProfile.id == token.bot_id)
    )
    bot = bot_result.scalar_one_or_none()

    # Fee claims
    fees_result = await db.execute(
        select(FeeClaim)
        .where(FeeClaim.bot_id == token.bot_id, FeeClaim.status == ClaimStatus.CONFIRMED)
        .order_by(FeeClaim.created_at.desc())
        .limit(20)
    )
    fees = fees_result.scalars().all()

    # Burn events
    burns_result = await db.execute(
        select(BurnEvent)
        .where(BurnEvent.bot_id == token.bot_id, BurnEvent.status == BurnStatus.CONFIRMED)
        .order_by(BurnEvent.created_at.desc())
        .limit(20)
    )
    burns = burns_result.scalars().all()

    # Snapshot history for mini chart
    history_result = await db.execute(
        select(TokenSnapshot)
        .where(TokenSnapshot.mint == mint)
        .order_by(TokenSnapshot.captured_at.asc())
        .limit(100)
    )
    history = history_result.scalars().all()

    total_fees = sum(f.amount_sol for f in fees)
    total_burned = sum(b.amount_burned for b in burns)

    return {
        "token": {
            "mint": token.mint,
            "name": token.name,
            "symbol": token.symbol,
            "image_url": token.image_url,
            "description": token.description,
            "created_at": token.created_at.isoformat() if token.created_at else None,
        },
        "market": {
            "price_usd": snapshot.price_usd if snapshot else 0,
            "mcap_usd": snapshot.mcap_usd if snapshot else 0,
            "volume_24h_usd": snapshot.volume_24h_usd if snapshot else 0,
            "liquidity_usd": snapshot.liquidity_usd if snapshot else 0,
            "status": (snapshot.status.value if snapshot and hasattr(snapshot.status, "value") else str(snapshot.status)) if snapshot else "unknown",
        },
        "agent": {
            "id": bot.id if bot else None,
            "name": bot.name if bot else None,
            "stage": bot.stage.value if bot and hasattr(bot.stage, "value") else (str(bot.stage) if bot else None),
        } if bot else None,
        "stats": {
            "total_fees_sol": round(total_fees, 4),
            "total_burned_tokens": total_burned,
            "fee_claims_count": len(fees),
            "burn_events_count": len(burns),
        },
        "fees": [
            {
                "amount_sol": f.amount_sol,
                "tx_signature": f.tx_signature,
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in fees
        ],
        "burns": [
            {
                "amount_burned": b.amount_burned,
                "tx_signature": b.tx_signature,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in burns
        ],
        "price_history": [
            {
                "price_usd": h.price_usd,
                "mcap_usd": h.mcap_usd,
                "captured_at": h.captured_at.isoformat() if h.captured_at else None,
            }
            for h in history
        ],
    }
