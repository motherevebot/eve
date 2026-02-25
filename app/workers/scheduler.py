"""
Lightweight in-process scheduler using asyncio tasks.
For production, replace with Celery Beat, APScheduler, or Arq cron.
"""

import asyncio
import logging

from app.db.session import async_session
from app.workers.claim_fees import run_claim_fees_job
from app.workers.buyback_burn import run_buyback_burn_job
from app.workers.snapshots import snapshot_tokens_job, snapshot_agents_job
from app.workers.reporting import run_daily_reports

logger = logging.getLogger(__name__)

CLAIM_INTERVAL = 300       # 5 minutes
BUYBACK_INTERVAL = 600     # 10 minutes
TOKEN_SNAP_INTERVAL = 300  # 5 minutes
AGENT_SNAP_INTERVAL = 3600 # 1 hour
DAILY_REPORT_INTERVAL = 86400  # 24 hours


async def _loop(name: str, coro_factory, interval: int):
    """Run a job in a loop with the given interval."""
    while True:
        try:
            async with async_session() as db:
                logger.info("scheduler: running %s", name)
                await coro_factory(db)
        except Exception:
            logger.exception("scheduler: %s failed", name)
        await asyncio.sleep(interval)


async def start_scheduler():
    """Launch all periodic workers as background tasks."""
    logger.info("scheduler: starting all periodic jobs")
    tasks = [
        asyncio.create_task(_loop("claim_fees", run_claim_fees_job, CLAIM_INTERVAL)),
        asyncio.create_task(_loop("buyback_burn", run_buyback_burn_job, BUYBACK_INTERVAL)),
        asyncio.create_task(_loop("snapshot_tokens", snapshot_tokens_job, TOKEN_SNAP_INTERVAL)),
        asyncio.create_task(_loop("snapshot_agents", snapshot_agents_job, AGENT_SNAP_INTERVAL)),
        asyncio.create_task(_loop("daily_reports", run_daily_reports, DAILY_REPORT_INTERVAL)),
    ]
    await asyncio.gather(*tasks)
