from datetime import datetime

from pydantic import BaseModel, ConfigDict


# ── Shared ─────────────────────────────────────────────────────────


class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── User ───────────────────────────────────────────────────────────


class UserOut(OrmBase):
    id: str
    x_handle: str
    x_display_name: str | None = None
    x_avatar_url: str | None = None
    created_at: datetime


# ── Bot ────────────────────────────────────────────────────────────


class BotCreate(BaseModel):
    name: str


class WalletOut(OrmBase):
    public_key: str
    reserve_sol: float


class LinkedTokenOut(OrmBase):
    mint: str
    symbol: str
    name: str
    image_url: str | None = None


class BotOut(OrmBase):
    id: str
    name: str
    stage: str
    created_at: datetime
    updated_at: datetime
    wallet: WalletOut | None = None
    linked_token: LinkedTokenOut | None = None


class BotList(BaseModel):
    items: list[BotOut]
    count: int


# ── FeeClaim ───────────────────────────────────────────────────────


class FeeClaimOut(OrmBase):
    id: str
    amount_sol: float
    tx_signature: str | None = None
    status: str
    created_at: datetime


# ── BurnEvent ──────────────────────────────────────────────────────


class BurnEventOut(OrmBase):
    id: str
    amount_burned: float
    mint: str
    tx_signature: str | None = None
    status: str
    created_at: datetime


# ── Reports ────────────────────────────────────────────────────────


class ReportOut(OrmBase):
    id: str
    report_type: str
    x_tweet_id: str | None = None
    content: str | None = None
    status: str
    created_at: datetime


# ── Public: Leaderboard ────────────────────────────────────────────


class LeaderboardSummary(BaseModel):
    agents_count: int = 0
    tokens_count: int = 0
    earnings_paid_sol: float = 0.0
    total_mcap_usd: float = 0.0
    volume_24h_usd: float = 0.0
    total_launches: int = 0
    top_agent_name: str | None = None
    top_agent_earnings_sol: float = 0.0
    top_token_name: str | None = None
    top_token_mcap_usd: float = 0.0


class AgentLeaderboardRow(BaseModel):
    rank: int
    bot_id: str
    name: str
    stage: str = "draft"
    x_handle: str | None = None
    tokens_count: int = 1
    earnings_sol: float = 0.0
    sol_per_token: float = 0.0


class AgentLeaderboardResponse(BaseModel):
    items: list[AgentLeaderboardRow]
    total_matched: int
    total_earnings_sol: float
    avg_earnings_sol: float
    page: int
    page_size: int


class TokenLeaderboardRow(BaseModel):
    rank: int
    mint: str
    symbol: str
    name: str
    image_url: str | None = None
    mcap_usd: float = 0.0
    price_usd: float = 0.0
    volume_24h_usd: float = 0.0
    status: str = "unknown"


class TokenLeaderboardResponse(BaseModel):
    items: list[TokenLeaderboardRow]
    total_matched: int
    total_mcap_usd: float
    total_volume_24h_usd: float
    graduated_count: int
    page: int
    page_size: int
