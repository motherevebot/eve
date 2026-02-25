import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.models import BotProfile, ReportPost, ReportType
from app.db.session import get_db
from app.schemas import ReportOut

router = APIRouter(prefix="/v1/bots", tags=["reports"])


@router.get("/{bot_id}/reports", response_model=list[ReportOut])
async def list_reports(
    bot_id: str,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await db.get(BotProfile, bot_id)
    if not bot or str(bot.owner_id) != owner_id:
        raise HTTPException(404, "Bot not found")

    q = (
        select(ReportPost)
        .where(ReportPost.bot_id == bot_id)
        .order_by(ReportPost.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(q)
    return [ReportOut.model_validate(r) for r in result.scalars().all()]


@router.post("/{bot_id}/reports/post-now")
async def post_report_now(
    bot_id: str,
    report_type: str = Query("daily", regex="^(daily|weekly)$"),
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await db.get(BotProfile, bot_id)
    if not bot or str(bot.owner_id) != owner_id:
        raise HTTPException(404, "Bot not found")

    token = bot.linked_token
    if not token:
        raise HTTPException(400, "No linked token")

    from app.workers.reporting import (
        _daily_report,
        _get_burns_in_period,
        _get_fees_in_period,
        _get_total_burns,
        _get_total_fees,
        _post_and_record,
        _weekly_report,
    )

    now = datetime.now(timezone.utc)

    if report_type == "daily":
        day_ago = now - timedelta(hours=24)
        fees_p = await _get_fees_in_period(db, bot.id, day_ago)
        fees_t = await _get_total_fees(db, bot.id)
        burns_p = await _get_burns_in_period(db, bot.id, day_ago)
        burns_t = await _get_total_burns(db, bot.id)
        content = _daily_report(bot.name, token.symbol, fees_p, fees_t, burns_p, burns_t)
        await _post_and_record(db, bot, ReportType.DAILY, content)
    else:
        week_ago = now - timedelta(days=7)
        fees_p = await _get_fees_in_period(db, bot.id, week_ago)
        fees_t = await _get_total_fees(db, bot.id)
        burns_p = await _get_burns_in_period(db, bot.id, week_ago)
        burns_t = await _get_total_burns(db, bot.id)
        content = _weekly_report(bot.name, token.symbol, fees_p, fees_t, burns_p, burns_t)
        await _post_and_record(db, bot, ReportType.WEEKLY, content)

    await db.commit()
    return {"status": "posted", "content": content}
