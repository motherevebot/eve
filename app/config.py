from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Eve API"
    debug: bool = False

    # Default: SQLite for local dev; set to postgresql+asyncpg://... for production
    database_url: str = "sqlite+aiosqlite:///./eve_dev.db"
    redis_url: str = "redis://localhost:6379/0"

    # Encryption key for custodial wallet private keys (Fernet)
    wallet_encryption_key: str = ""

    # X / Twitter OAuth 2.0
    x_client_id: str = ""
    x_client_secret: str = ""
    x_redirect_uri: str = "http://localhost:8000/v1/auth/x/callback"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 168  # 7 days

    # Solana RPC
    solana_rpc_url: str = "https://api.mainnet-beta.solana.com"

    # Launcher service (Next.js API routes that wrap pump-fun SDK)
    launcher_service_url: str = "http://localhost:3000"

    # Metadata endpoint base URL (where pump.fun can fetch token metadata)
    metadata_base_url: str = "http://localhost:8000"

    # Trading thresholds
    excess_profit_threshold_sol: float = 0.05
    max_buyback_sol: float = 1.0
    reserve_sol: float = 0.01

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
