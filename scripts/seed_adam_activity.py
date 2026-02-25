"""Add fee claims and burn events to The Adam agent."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.base import Base
from app.db.models import (
    BotProfile, LinkedToken, FeeClaim, ClaimStatus,
    BurnEvent, BurnStatus, AgentSnapshot,
)
from app.db.session import engine, async_session
from sqlalchemy import select
from datetime import datetime, timedelta, timezone


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        result = await db.execute(
            select(BotProfile).join(LinkedToken).where(
                LinkedToken.mint == "Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump"
            )
        )
        bot = result.scalar_one_or_none()
        if not bot:
            print("ERROR: The Adam bot not found. Run seed_adam.py first.")
            return

        now = datetime.now(timezone.utc)
        mint = "Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump"

        # Fee claims — total 5.21 SOL
        fee_claims = [
            {"amount_sol": 0.82, "hours_ago": 2, "tx": "5aR1kX...claim1"},
            {"amount_sol": 0.65, "hours_ago": 5, "tx": "3bT9mQ...claim2"},
            {"amount_sol": 0.91, "hours_ago": 12, "tx": "7cU2nR...claim3"},
            {"amount_sol": 0.73, "hours_ago": 18, "tx": "9dV4pS...claim4"},
            {"amount_sol": 0.58, "hours_ago": 26, "tx": "2eW6qT...claim5"},
            {"amount_sol": 0.44, "hours_ago": 34, "tx": "8fX8rU...claim6"},
            {"amount_sol": 0.61, "hours_ago": 48, "tx": "4gY1sV...claim7"},
            {"amount_sol": 0.47, "hours_ago": 60, "tx": "6hZ3tW...claim8"},
        ]

        for fc in fee_claims:
            claim = FeeClaim(
                bot_id=bot.id,
                amount_sol=fc["amount_sol"],
                tx_signature=fc["tx"],
                status=ClaimStatus.CONFIRMED,
            )
            db.add(claim)
            await db.flush()
            # Manually set created_at
            claim.created_at = now - timedelta(hours=fc["hours_ago"])

        print(f"Added {len(fee_claims)} fee claims (total {sum(f['amount_sol'] for f in fee_claims):.2f} SOL)")

        # Burn events — total ~3.89 SOL worth of tokens burned
        burn_events = [
            {"amount": 185420, "hours_ago": 3, "tx": "1aB2cD...burn1"},
            {"amount": 142300, "hours_ago": 8, "tx": "3eF4gH...burn2"},
            {"amount": 198750, "hours_ago": 16, "tx": "5iJ6kL...burn3"},
            {"amount": 167200, "hours_ago": 24, "tx": "7mN8oP...burn4"},
            {"amount": 134800, "hours_ago": 36, "tx": "9qR1sT...burn5"},
            {"amount": 112500, "hours_ago": 50, "tx": "2uV3wX...burn6"},
            {"amount": 156030, "hours_ago": 62, "tx": "4yZ5aB...burn7"},
        ]

        for be in burn_events:
            burn = BurnEvent(
                bot_id=bot.id,
                amount_burned=be["amount"],
                mint=mint,
                tx_signature=be["tx"],
                status=BurnStatus.CONFIRMED,
            )
            db.add(burn)
            await db.flush()
            burn.created_at = now - timedelta(hours=be["hours_ago"])

        print(f"Added {len(burn_events)} burn events (total {sum(b['amount'] for b in burn_events):,.0f} tokens)")

        # Update agent snapshot
        agent_snap = AgentSnapshot(
            bot_id=bot.id,
            claimed_fees_total_sol=5.21,
            claimed_fees_24h_sol=2.38,
            burns_total=len(burn_events),
            burns_24h=3,
        )
        db.add(agent_snap)

        await db.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
