import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Use String(36) so it works on both Postgres and SQLite
GUID = String(36)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# ── Enums ──────────────────────────────────────────────────────────


class BotStage(str, enum.Enum):
    DRAFT = "draft"
    WALLET_READY = "wallet_ready"
    LAUNCHED = "launched"
    TRADING_ARMED = "trading_armed"
    LIVE = "live"
    PAUSED = "paused"


class ClaimStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class SwapStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class BurnStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class ReportType(str, enum.Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    EVENT_LAUNCH = "event_launch"
    EVENT_CLAIM = "event_claim"
    EVENT_BURN = "event_burn"


class TokenStatus(str, enum.Enum):
    BONDING = "bonding"
    GRADUATED = "graduated"
    UNKNOWN = "unknown"


# ── User ───────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    x_user_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    x_handle: Mapped[str] = mapped_column(String(64))
    x_display_name: Mapped[str | None] = mapped_column(String(256))
    x_avatar_url: Mapped[str | None] = mapped_column(Text)

    # Encrypted X OAuth tokens
    x_access_token_enc: Mapped[str | None] = mapped_column(Text)
    x_refresh_token_enc: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    bots: Mapped[list["BotProfile"]] = relationship(back_populates="owner", lazy="selectin")


# ── BotProfile ─────────────────────────────────────────────────────


class BotProfile(Base):
    __tablename__ = "bot_profiles"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    stage: Mapped[BotStage] = mapped_column(Enum(BotStage), default=BotStage.DRAFT)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    owner: Mapped["User"] = relationship(back_populates="bots")
    wallet: Mapped["BotWallet | None"] = relationship(back_populates="bot", uselist=False, lazy="selectin")
    linked_token: Mapped["LinkedToken | None"] = relationship(back_populates="bot", uselist=False, lazy="selectin")
    fee_claims: Mapped[list["FeeClaim"]] = relationship(back_populates="bot", lazy="noload")
    buyback_swaps: Mapped[list["BuybackSwap"]] = relationship(back_populates="bot", lazy="noload")
    burn_events: Mapped[list["BurnEvent"]] = relationship(back_populates="bot", lazy="noload")
    reports: Mapped[list["ReportPost"]] = relationship(back_populates="bot", lazy="noload")


# ── BotWallet ──────────────────────────────────────────────────────


class BotWallet(Base):
    __tablename__ = "bot_wallets"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), unique=True, index=True)
    public_key: Mapped[str] = mapped_column(String(64), unique=True)
    encrypted_private_key: Mapped[str] = mapped_column(Text)
    reserve_sol: Mapped[float] = mapped_column(Float, default=0.01)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="wallet")


# ── LinkedToken ────────────────────────────────────────────────────


class LinkedToken(Base):
    __tablename__ = "linked_tokens"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), unique=True, index=True)
    mint: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(128))
    token_program: Mapped[str] = mapped_column(String(64), default="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
    image_url: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    metadata_uri: Mapped[str | None] = mapped_column(Text)
    tx_signature: Mapped[str | None] = mapped_column(String(128))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="linked_token")


# ── FeeClaim ───────────────────────────────────────────────────────


class FeeClaim(Base):
    __tablename__ = "fee_claims"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    amount_sol: Mapped[float] = mapped_column(Float)
    tx_signature: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[ClaimStatus] = mapped_column(Enum(ClaimStatus), default=ClaimStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="fee_claims")

    __table_args__ = (Index("ix_fee_claims_bot_status", "bot_id", "status"),)


# ── PrincipalLedger ────────────────────────────────────────────────


class PrincipalLedger(Base):
    __tablename__ = "principal_ledger"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    running_total_sol: Mapped[float] = mapped_column(Float, default=0.0)
    last_claim_id: Mapped[str | None] = mapped_column(ForeignKey("fee_claims.id"))

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


# ── BuybackSwap ───────────────────────────────────────────────────


class BuybackSwap(Base):
    __tablename__ = "buyback_swaps"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    input_amount_sol: Mapped[float] = mapped_column(Float)
    output_amount_token: Mapped[float | None] = mapped_column(Float)
    slippage_bps: Mapped[int | None] = mapped_column(BigInteger)
    tx_signature: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[SwapStatus] = mapped_column(Enum(SwapStatus), default=SwapStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="buyback_swaps")


# ── BurnEvent ──────────────────────────────────────────────────────


class BurnEvent(Base):
    __tablename__ = "burn_events"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    amount_burned: Mapped[float] = mapped_column(Float)
    mint: Mapped[str] = mapped_column(String(64))
    tx_signature: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[BurnStatus] = mapped_column(Enum(BurnStatus), default=BurnStatus.PENDING)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="burn_events")


# ── ReportPost ─────────────────────────────────────────────────────


class ReportPost(Base):
    __tablename__ = "report_posts"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType))
    x_tweet_id: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="draft")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    bot: Mapped["BotProfile"] = relationship(back_populates="reports")


# ── TokenSnapshot (for public leaderboard) ─────────────────────────


class TokenSnapshot(Base):
    __tablename__ = "token_snapshots"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    mint: Mapped[str] = mapped_column(String(64), index=True)
    price_usd: Mapped[float] = mapped_column(Float, default=0.0)
    mcap_usd: Mapped[float] = mapped_column(Float, default=0.0)
    volume_24h_usd: Mapped[float] = mapped_column(Float, default=0.0)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    status: Mapped[TokenStatus] = mapped_column(Enum(TokenStatus), default=TokenStatus.UNKNOWN)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_token_snapshots_mint_time", "mint", "captured_at"),)


# ── AgentSnapshot (for public leaderboard) ─────────────────────────


class AgentSnapshot(Base):
    __tablename__ = "agent_snapshots"

    id: Mapped[str] = mapped_column(GUID, primary_key=True, default=_new_uuid)
    bot_id: Mapped[str] = mapped_column(ForeignKey("bot_profiles.id"), index=True)
    claimed_fees_total_sol: Mapped[float] = mapped_column(Float, default=0.0)
    claimed_fees_24h_sol: Mapped[float] = mapped_column(Float, default=0.0)
    burns_total: Mapped[int] = mapped_column(BigInteger, default=0)
    burns_24h: Mapped[int] = mapped_column(BigInteger, default=0)

    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_agent_snapshots_bot_time", "bot_id", "captured_at"),)
