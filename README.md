<p align="center">
  <img src="https://cdn.dexscreener.com/cms/images/UIt8mU7dHi9GiTLf?width=800&height=800&quality=90" width="120" height="120" style="border-radius:24px" />
</p>

<h1 align="center">Eve — Autonomous Token Agent Engine</h1>

<p align="center">
  <strong>Self-sustaining buyback & burn engine for Solana tokens launched on pump.fun</strong>
</p>

<p align="center">
  <a href="https://x.com/TheMother_Eve">𝕏 Twitter</a> ·
  <a href="https://solscan.io/tx/4AMMKSEbf4DAGLFEyBLJzJjMfzXn4DHkAJHaSpxxHcFoyKJgr5bD4DPCXb1fRpXo2Zzgqeh6ADPCr1hsHvja5Ptu">Solscan</a>
</p>

---

## What is Eve?

Eve is an **autonomous agent engine** that manages the full lifecycle of Solana tokens launched via [pump.fun](https://pump.fun). Each token gets its own AI agent that:

1. **Claims creator fees** from pump.fun trading activity
2. **Buys back** its own token on the open market using [Jupiter](https://jup.ag)
3. **Burns** the purchased tokens permanently, reducing supply
4. **Reports** every action transparently on X/Twitter

No human intervention required. The loop runs indefinitely, creating deflationary pressure as long as the token trades.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Eve Agent Engine                         │
│                                                                 │
│  ┌───────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ Scheduler │──│  Claim Fees  │──│   Buyback    │            │
│  │ (asyncio) │  │  Worker      │  │   & Burn     │            │
│  │           │  │              │  │   Worker     │            │
│  │  5m / 10m │  │  pump.fun →  │  │  Jupiter →   │            │
│  │  cycles   │  │  SOL fees    │  │  SPL burn    │            │
│  └─────┬─────┘  └──────────────┘  └──────────────┘            │
│        │                                                       │
│  ┌─────┴─────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ Snapshots │  │  Reporting   │  │   Wallet     │            │
│  │ Worker    │  │  Worker      │  │   Service    │            │
│  │           │  │              │  │              │            │
│  │ DexScreen │  │  X/Twitter   │  │  Custodial   │            │
│  │ → DB      │  │  auto-post   │  │  Fernet enc  │            │
│  └───────────┘  └──────────────┘  └──────────────┘            │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │              Database (PostgreSQL / SQLite)             │    │
│  │  Users · Bots · Wallets · Tokens · Claims · Swaps ·    │    │
│  │  Burns · Snapshots · Reports · Ledger                  │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
   ┌──────────┐       ┌──────────────┐     ┌──────────────┐
   │ Solana   │       │  Jupiter     │     │  pump.fun    │
   │ RPC      │       │  DEX Agg.    │     │  SDK         │
   └──────────┘       └──────────────┘     └──────────────┘
```

---

## The Buyback & Burn Loop

This is the core mechanism that makes Eve tokens deflationary:

### Step 1 — Claim Creator Fees

Every pump.fun token generates creator fees from trading activity. Eve's `claim_fees` worker runs every **5 minutes**:

```
Scheduler → check claimable fees for each bot
           → build claim transaction via pump.fun SDK
           → sign with custodial wallet (Fernet-encrypted keys)
           → submit to Solana RPC
           → record FeeClaim in database
           → update PrincipalLedger
```

### Step 2 — Compute Excess Profit

Before buying back, Eve calculates how much SOL is available:

```
excess = wallet_balance - principal_claimed - reserve
```

- **`principal_claimed`** — running total of all fees claimed (tracked in `PrincipalLedger`)
- **`reserve`** — minimum SOL kept for transaction fees (default: 0.01 SOL)
- Only proceeds if `excess > threshold` (default: 0.05 SOL)

### Step 3 — Buyback via Jupiter

The `buyback_burn` worker runs every **10 minutes**:

```
excess SOL → Jupiter quote (SOL → token)
           → build swap transaction
           → sign with custodial wallet
           → submit to Solana
           → record BuybackSwap
```

Jupiter finds the best route across all Solana DEXes, ensuring optimal execution.

### Step 4 — Burn Tokens

Immediately after the buyback swap confirms:

```
bought tokens → derive Associated Token Account
              → build SPL Burn instruction
              → sign and submit
              → tokens permanently destroyed
              → record BurnEvent
```

The burn instruction uses the standard SPL Token program `Burn` opcode, making it verifiable on-chain.

### Step 5 — Report on X/Twitter

Every action is reported transparently:

```
📊 The Adam — Daily Report

Token: $Adam
Fees claimed (24h): 0.8200 SOL
Total fees: 5.2100 SOL
Burns (24h): 2
Total burns: 7

Powered by Eve 🌿
```

---

## Agent Lifecycle

Each bot progresses through these stages:

```
DRAFT → WALLET_READY → LAUNCHED → TRADING_ARMED → LIVE → PAUSED
  │          │              │            │           │        │
  │    Custodial wallet     │     Autonomous     Running   Manual
  │    generated (ed25519)  │     trading        buyback   pause
  │                    Token created   enabled    & burn
  │                    on pump.fun
  │
  User creates agent
```

| Stage | Description |
|-------|-------------|
| `DRAFT` | Agent created, no wallet yet |
| `WALLET_READY` | Custodial Solana wallet generated, encrypted private key stored |
| `LAUNCHED` | Token created on pump.fun, mint address linked |
| `TRADING_ARMED` | Creator fee claiming enabled |
| `LIVE` | Full autonomous loop: claim → buyback → burn → report |
| `PAUSED` | Agent temporarily stopped |

---

## Custodial Wallet Security

Eve manages wallets server-side for fully autonomous operation:

```
Keypair.generate()
     │
     ▼
public_key (base58) ──→ stored in DB (plain)
     │
secret_key (bytes)
     │
     ▼
hex(secret_key) ──→ Fernet.encrypt() ──→ stored in DB (encrypted)
                          │
                    WALLET_ENCRYPTION_KEY
                    (env variable, Fernet key)
```

When signing transactions:

```
encrypted_key ──→ Fernet.decrypt() ──→ hex → bytes ──→ Keypair
                                                          │
raw_tx_bytes ──→ VersionedTransaction.from_bytes()        │
                          │                                │
                          ▼                                ▼
                    VersionedTransaction(message, [keypair])
                          │
                          ▼
                    signed bytes → send to Solana RPC
```

---

## Data Models

```
User
 └── BotProfile (agent)
      ├── BotWallet (custodial Solana wallet)
      ├── LinkedToken (pump.fun token)
      ├── FeeClaim[] (creator fee claims)
      ├── BuybackSwap[] (Jupiter swaps)
      ├── BurnEvent[] (SPL token burns)
      ├── ReportPost[] (X/Twitter reports)
      └── PrincipalLedger (running fee total)

TokenSnapshot[] — periodic market data (price, mcap, volume)
AgentSnapshot[] — periodic agent stats (fees claimed, burns count)
```

---

## Services

| Service | Integration | Purpose |
|---------|-------------|---------|
| `pump_portal.py` | pump.fun SDK | Check claimable fees, build claim transactions |
| `jupiter.py` | Jupiter Aggregator API | Get swap quotes, build swap transactions |
| `token_ops.py` | SPL Token Program | Build burn instructions (opcode 8) |
| `solana_rpc.py` | Solana JSON-RPC | Balance checks, send transactions, confirmations |
| `wallet.py` | solders (Rust bindings) | Generate keypairs, sign VersionedTransactions |
| `encryption.py` | cryptography (Fernet) | Encrypt/decrypt private keys and OAuth tokens |
| `dexscreener.py` | DexScreener API | Fetch real-time market data for snapshots |
| `x_oauth.py` | X/Twitter API v2 | OAuth 2.0 PKCE, post tweets |

---

## Workers

| Worker | Interval | Job |
|--------|----------|-----|
| `claim_fees` | 5 min | Claim creator fees from pump.fun |
| `buyback_burn` | 10 min | Compute excess → Jupiter swap → SPL burn |
| `snapshot_tokens` | 5 min | Fetch price/mcap/volume from DexScreener |
| `snapshot_agents` | 1 hour | Aggregate fee/burn stats per agent |
| `daily_reports` | 24 hours | Post daily summary to X/Twitter |

All workers run as async tasks via a lightweight in-process scheduler.

---

## Tech Stack

- **Runtime**: Python 3.12, FastAPI, asyncio
- **Database**: PostgreSQL (production) / SQLite (development), SQLAlchemy 2.0 async
- **Solana**: `solders` (Rust bindings for keypairs, transactions), direct JSON-RPC
- **DEX**: Jupiter Aggregator API v6
- **Token Launch**: pump.fun via `@pump-fun/pump-sdk` (Next.js sidecar)
- **Encryption**: Fernet symmetric encryption (cryptography library)
- **Social**: X/Twitter API v2 (OAuth 2.0 PKCE)
- **Market Data**: DexScreener API

---

## Quick Start

```bash
# Clone
git clone https://github.com/motherevebot/eve.git
cd eve

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your keys

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Environment Variables

```env
# Database (PostgreSQL for production)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/eve

# Wallet encryption (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
WALLET_ENCRYPTION_KEY=your-fernet-key

# Solana RPC (use a paid RPC for production)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com

# X/Twitter OAuth 2.0
X_CLIENT_ID=your-client-id
X_CLIENT_SECRET=your-client-secret
X_REDIRECT_URI=https://your-domain.com/v1/auth/x/callback

# JWT
JWT_SECRET=your-secret-key

# Trading thresholds
EXCESS_PROFIT_THRESHOLD_SOL=0.05
MAX_BUYBACK_SOL=1.0
RESERVE_SOL=0.01
```

---

## Project Structure

```
eve/
├── app/
│   ├── main.py              # FastAPI app, startup hooks
│   ├── config.py             # Pydantic settings from .env
│   ├── schemas.py            # Request/response models
│   │
│   ├── api/
│   │   ├── auth.py           # X/Twitter OAuth 2.0 flow
│   │   ├── bots.py           # CRUD for agent profiles
│   │   ├── accounting.py     # Fee claims & burn history
│   │   ├── public.py         # Leaderboard & token detail
│   │   ├── reports.py        # Report management
│   │   ├── upload.py         # Image uploads
│   │   ├── metadata.py       # Token metadata for pump.fun
│   │   └── deps.py           # Auth dependencies
│   │
│   ├── db/
│   │   ├── models.py         # SQLAlchemy 2.0 models
│   │   ├── session.py        # Async session factory
│   │   └── base.py           # Declarative base
│   │
│   ├── services/
│   │   ├── wallet.py         # Custodial wallet & signing
│   │   ├── encryption.py     # Fernet encryption
│   │   ├── solana_rpc.py     # Solana JSON-RPC client
│   │   ├── jupiter.py        # Jupiter DEX aggregator
│   │   ├── pump_portal.py    # pump.fun SDK bridge
│   │   ├── token_ops.py      # SPL Token burn instructions
│   │   ├── dexscreener.py    # Market data fetcher
│   │   ├── x_oauth.py        # X/Twitter API
│   │   ├── jwt_auth.py       # JWT token service
│   │   └── redis_store.py    # Session/cache store
│   │
│   └── workers/
│       ├── scheduler.py      # Async task scheduler
│       ├── claim_fees.py     # Fee claiming worker
│       ├── buyback_burn.py   # Buyback & burn worker
│       ├── snapshots.py      # Market data snapshots
│       └── reporting.py      # X/Twitter report posting
│
├── requirements.txt
├── .env.example
└── README.md
```

---

## How It Works — In One Diagram

```
                    ┌─────────────────┐
                    │    pump.fun     │
                    │  Token Trading  │
                    └────────┬────────┘
                             │
                     Creator Fees (SOL)
                             │
                             ▼
                    ┌─────────────────┐
                    │   Eve Agent     │
                    │   Claim Fees    │◄──── every 5 min
                    └────────┬────────┘
                             │
                        SOL in wallet
                             │
                             ▼
                    ┌─────────────────┐
                    │  Excess Profit  │
                    │  Calculation    │
                    │                 │
                    │ balance - total │
                    │ claimed - rsrv  │
                    └────────┬────────┘
                             │
                     excess > threshold?
                      │              │
                     NO             YES
                      │              │
                   (wait)            ▼
                           ┌─────────────────┐
                           │   Jupiter Swap  │
                           │   SOL → Token   │◄──── every 10 min
                           └────────┬────────┘
                                    │
                              token amount
                                    │
                                    ▼
                           ┌─────────────────┐
                           │   SPL Burn      │
                           │   Token → 🔥    │
                           └────────┬────────┘
                                    │
                                    ▼
                           ┌─────────────────┐
                           │   Post to X     │
                           │   @TheMother_Eve│
                           └─────────────────┘
```

---

## License

MIT

---

<p align="center">
  <strong>Eve</strong> — The Mother of All Agents 🌿
</p>
