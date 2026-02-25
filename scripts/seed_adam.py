"""Seed The Adam token into the database with real DexScreener data."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db.session import engine, get_db
from app.db.base import Base
from app.db.models import (
    User, BotProfile, BotStage, BotWallet, LinkedToken,
    TokenSnapshot, TokenStatus, AgentSnapshot,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    from app.db.session import async_session

    async with async_session() as db:
        existing = await db.execute(
            select(LinkedToken).where(LinkedToken.mint == "Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump")
        )
        if existing.scalar_one_or_none():
            print("Token already exists, updating snapshot...")
        else:
            # Ensure a user exists
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            if not user:
                user = User(
                    x_user_id="dev_adam_creator",
                    x_handle="CovenantAdam",
                    x_display_name="Adam Creator",
                    x_avatar_url="https://cdn.dexscreener.com/cms/images/UIt8mU7dHi9GiTLf?width=800&height=800&quality=90",
                )
                db.add(user)
                await db.flush()

            # Create bot profile
            bot = BotProfile(
                owner_id=user.id,
                name="The Adam",
                stage=BotStage.LIVE,
            )
            db.add(bot)
            await db.flush()

            # Create linked token
            token = LinkedToken(
                bot_id=bot.id,
                mint="Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump",
                symbol="Adam",
                name="The Adam",
                token_program="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
                image_url="https://cdn.dexscreener.com/cms/images/UIt8mU7dHi9GiTLf?width=800&height=800&quality=90",
                description="The Adam — AI agent token on Solana. Autonomous trading via creator fees, buyback & burn mechanics. Website: theadam.bot | Twitter: @CovenantAdam",
                metadata_uri="https://theadam.bot",
                tx_signature="seeded",
            )
            db.add(token)
            await db.flush()
            print(f"Created bot '{bot.name}' (id={bot.id}) with token {token.mint}")

        # Add/update token snapshot with real DexScreener data
        snapshot = TokenSnapshot(
            mint="Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump",
            price_usd=0.00004303,
            mcap_usd=42908.0,
            volume_24h_usd=441686.45,
            liquidity_usd=19500.68,
            status=TokenStatus.GRADUATED,
        )
        db.add(snapshot)

        # Add agent snapshot too
        result = await db.execute(
            select(BotProfile).join(LinkedToken).where(
                LinkedToken.mint == "Br34SVc9DPCJtasCquNNcWznCNXp65NgMzpPP7i2pump"
            )
        )
        bot = result.scalar_one_or_none()
        if bot:
            agent_snap = AgentSnapshot(
                bot_id=bot.id,
                claimed_fees_total_sol=2.45,
                claimed_fees_24h_sol=0.38,
                burns_total=12,
                burns_24h=3,
            )
            db.add(agent_snap)

        await db.commit()
        print("Done! Token snapshot added.")


if __name__ == "__main__":
    asyncio.run(seed())
