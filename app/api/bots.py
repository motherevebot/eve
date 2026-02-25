import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_id
from app.db.models import BotProfile, BotStage, BotWallet, LinkedToken
from app.db.session import get_db
from app.schemas import BotCreate, BotList, BotOut

router = APIRouter(prefix="/v1/bots", tags=["bots"])


async def _get_bot_or_404(db: AsyncSession, bot_id: str, owner_id: str) -> BotProfile:
    bot = await db.get(BotProfile, bot_id)
    if not bot or str(bot.owner_id) != owner_id:
        raise HTTPException(404, "Bot not found")
    return bot


# ── List / Create / Get ───────────────────────────────────────────


@router.get("", response_model=BotList)
async def list_bots(
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    q = select(BotProfile).where(BotProfile.owner_id == owner_id)
    result = await db.execute(q)
    bots = result.scalars().all()
    return BotList(items=[BotOut.model_validate(b) for b in bots], count=len(bots))


@router.post("", response_model=BotOut, status_code=201)
async def create_bot(
    body: BotCreate,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = BotProfile(name=body.name, owner_id=owner_id, stage=BotStage.DRAFT)
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return BotOut.model_validate(bot)


@router.get("/{bot_id}", response_model=BotOut)
async def get_bot(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)
    return BotOut.model_validate(bot)


# ── Actions ───────────────────────────────────────────────────────


@router.post("/{bot_id}/actions/create-wallet", response_model=BotOut)
async def action_create_wallet(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)
    if bot.wallet:
        raise HTTPException(400, "Wallet already exists")
    if bot.stage != BotStage.DRAFT:
        raise HTTPException(400, f"Cannot create wallet in stage {bot.stage.value}")

    from app.services.wallet import create_custodial_wallet
    pub, enc_priv = create_custodial_wallet()
    wallet = BotWallet(bot_id=bot.id, public_key=pub, encrypted_private_key=enc_priv)
    db.add(wallet)
    bot.stage = BotStage.WALLET_READY
    await db.commit()
    await db.refresh(bot)
    return BotOut.model_validate(bot)


class LaunchTokenBody(BaseModel):
    name: str
    symbol: str
    description: str = ""
    image_url: str = ""
    initial_buy_sol: float = 0.0


@router.post("/{bot_id}/actions/launch-token", response_model=BotOut)
async def action_launch_token(
    bot_id: str,
    body: LaunchTokenBody,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    """Create a token on pump.fun and link it to the bot."""
    import base64
    import logging

    import httpx
    from solders.keypair import Keypair

    from app.config import settings
    from app.services.metadata import build_metadata, metadata_to_json
    from app.services.solana_rpc import send_raw_transaction, confirm_transaction
    from app.services.wallet import get_keypair, sign_versioned_transaction_multi

    logger = logging.getLogger(__name__)

    bot = await _get_bot_or_404(db, bot_id, owner_id)
    if bot.linked_token:
        raise HTTPException(400, "Token already linked")
    if bot.stage != BotStage.WALLET_READY:
        raise HTTPException(400, f"Cannot launch token in stage {bot.stage.value}")

    wallet: BotWallet | None = bot.wallet
    if not wallet:
        raise HTTPException(400, "No wallet — create wallet first")

    # 1. Generate a fresh mint keypair
    mint_kp = Keypair()
    mint_pubkey = str(mint_kp.pubkey())

    # 2. Store metadata so pump.fun can fetch it
    # First save a preliminary LinkedToken so the metadata endpoint works
    meta = build_metadata(
        name=body.name,
        symbol=body.symbol,
        description=body.description,
        image=body.image_url,
    )
    metadata_uri = f"{settings.metadata_base_url}/v1/metadata/{bot_id}"

    # 3. Call Next.js launcher service to build the create transaction
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.launcher_service_url}/api/pump/build-create",
                json={
                    "mint": mint_pubkey,
                    "creator": wallet.public_key,
                    "name": body.name,
                    "symbol": body.symbol,
                    "uri": metadata_uri,
                    "solAmount": body.initial_buy_sol,
                },
            )
            if resp.status_code != 200:
                logger.error("Launcher build-create failed: %d %s", resp.status_code, resp.text[:500])
                raise HTTPException(502, f"Launcher service error: {resp.text[:200]}")

            data = resp.json()
    except httpx.ConnectError:
        raise HTTPException(503, "Launcher service not reachable — is Next.js running?")

    tx_base64 = data["tx"]
    tx_bytes = base64.b64decode(tx_base64)

    # 4. Sign with both the mint keypair and the custodial wallet keypair
    try:
        signed_bytes = sign_versioned_transaction_multi(
            tx_bytes,
            wallet.encrypted_private_key,
            extra_keypairs=[mint_kp],
        )
    except Exception as e:
        logger.exception("Transaction signing failed")
        raise HTTPException(500, f"Signing failed: {e}")

    # 5. Submit to Solana
    try:
        signature = await send_raw_transaction(signed_bytes)
        confirmed = await confirm_transaction(signature, timeout_sec=30)
    except Exception as e:
        logger.exception("Transaction submission failed")
        raise HTTPException(502, f"Transaction failed: {e}")

    if not confirmed:
        raise HTTPException(502, "Transaction not confirmed in time")

    # 6. Store the linked token
    token = LinkedToken(
        bot_id=bot.id,
        mint=mint_pubkey,
        symbol=body.symbol,
        name=body.name,
        token_program="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
        image_url=body.image_url or None,
        description=body.description or None,
        metadata_uri=metadata_uri,
        tx_signature=signature,
    )
    db.add(token)
    bot.stage = BotStage.LAUNCHED
    await db.commit()
    await db.refresh(bot)

    logger.info(
        "Token launched: mint=%s symbol=%s tx=%s",
        mint_pubkey, body.symbol, signature,
    )
    return BotOut.model_validate(bot)


@router.post("/{bot_id}/actions/arm", response_model=BotOut)
async def action_arm(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)
    if bot.stage != BotStage.LAUNCHED:
        raise HTTPException(400, f"Cannot arm bot in stage {bot.stage.value}")
    bot.stage = BotStage.TRADING_ARMED
    await db.commit()
    await db.refresh(bot)
    return BotOut.model_validate(bot)


@router.post("/{bot_id}/actions/pause", response_model=BotOut)
async def action_pause(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)
    if bot.stage not in (BotStage.TRADING_ARMED, BotStage.LIVE):
        raise HTTPException(400, f"Cannot pause bot in stage {bot.stage.value}")
    bot.stage = BotStage.PAUSED
    await db.commit()
    await db.refresh(bot)
    return BotOut.model_validate(bot)


@router.post("/{bot_id}/actions/resume", response_model=BotOut)
async def action_resume(
    bot_id: str,
    owner_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    bot = await _get_bot_or_404(db, bot_id, owner_id)
    if bot.stage != BotStage.PAUSED:
        raise HTTPException(400, f"Cannot resume bot in stage {bot.stage.value}")
    bot.stage = BotStage.TRADING_ARMED
    await db.commit()
    await db.refresh(bot)
    return BotOut.model_validate(bot)
