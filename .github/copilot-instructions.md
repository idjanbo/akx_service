# AKX Crypto Payment Gateway - Copilot Instructions

## Project Overview
A cryptocurrency payment gateway backend API built with FastAPI, supporting multi-chain transactions (TRON, Ethereum, Solana) with USDT as the primary settlement currency.

## Tech Stack
- **Package Manager**: `uv` (Astral) - use `uv add` for dependencies, `uv run` for execution
- **Framework**: FastAPI with full async/await patterns
- **ORM**: SQLModel with async MySQL driver (`aiomysql` or `asyncmy`)
- **Database**: MySQL 8.0+ (InnoDB)
- **Auth**: Clerk SDK for JWT verification, synced to local `users` table
- **Validation**: Pydantic V2

## Development Workflows
```bash
# Install dependencies
uv sync

# Run dev server
uv run fastapi dev src/main.py

# Run production
uv run fastapi run src/main.py

# Add dependencies
uv add <package>
uv add --dev <dev-package>

# Run tests
uv run pytest

# Type checking
uv run mypy src/
```

## Required Environment Variables
```bash
# Database
DATABASE_URL=mysql+aiomysql://user:pass@localhost:3306/akx_db

# Security (32-byte key, base64 encoded)
AES_ENCRYPTION_KEY=<base64-encoded-32-byte-key>

# Clerk Authentication
CLERK_SECRET_KEY=sk_live_xxx
CLERK_PUBLISHABLE_KEY=pk_live_xxx

# TRON (Primary Chain)
TRON_API_KEY=<trongrid-api-key>
TRON_NETWORK=mainnet  # or shasta for testnet

# Redis (Task Queue)
REDIS_URL=redis://localhost:6379

# Ethereum (Secondary)
ETH_RPC_URL=https://mainnet.infura.io/v3/xxx

# Solana (Tertiary)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

## Architecture: Modular Monolith
```
/src
  /api              # Routes by domain (auth, merchant, admin, webhook)
  /core             # Config, AES encryption, exceptions
  /db               # Async MySQL engine setup
  /models           # SQLModel entities
  /schemas          # Pydantic DTOs
  /services         # Business logic layer
  /chains           # Blockchain abstraction (factory pattern)
  /workers          # Celery tasks (block scanner, sweeper, webhook retry)
```

## Background Tasks (Celery)
```bash
# Start all workers
uv run celery -A src.workers.celery_app worker -l info

# Start beat scheduler (periodic tasks)
uv run celery -A src.workers.celery_app beat -l info

# Start workers per chain (production)
uv run celery -A src.workers.celery_app worker -Q tron -l info -c 1
uv run celery -A src.workers.celery_app worker -Q ethereum -l info -c 1
uv run celery -A src.workers.celery_app worker -Q solana -l info -c 1
uv run celery -A src.workers.celery_app worker -Q common -l info -c 2
```

Tasks are defined in `src/workers/chain_scanners/` and `src/workers/common_tasks.py`:
- `scan_tron_blocks` - Every 10 seconds (queue: tron)
- `scan_ethereum_blocks` - Every 15 seconds (queue: ethereum)
- `scan_solana_blocks` - Every 5 seconds (queue: solana)
- `sweep_funds` - Every 5 minutes (queue: common)
- `retry_webhooks` - Every 60 seconds (queue: common)
- `process_withdrawals` - Every 30 seconds (queue: common)

## Critical Patterns

### Database Fields (MySQL-specific)
- **All indexed strings** MUST have `max_length` in Field (e.g., `Field(max_length=255)`)
- **Money fields** MUST use `DECIMAL(32, 8)` - NEVER float
- Use MySQL JSON type for chain metadata

### Private Key Security
- **NEVER** store plaintext private keys
- Encrypt with AES-256-GCM before database storage
- Decrypt in memory only when needed, clear immediately after use
- Encryption key MUST come from environment variable

### Payment API Authentication
- Merchants have two keys: `deposit_key` and `withdraw_key`
- All payment API requests signed with HMAC-SHA256
- Signature: `HMAC-SHA256(message, key)`
- Request timestamp must be within 5 minutes

### Blockchain Integration (TRON First)
- Use `/chains/base.py` as `ChainInterface` abstract class
- **Priority**: Implement TRON first (`/chains/tron.py` with `tronpy`)
- TRON requires 19 confirmations for finality
- USDT-TRC20 contract: `TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t` (mainnet)

### Order State Machine
Withdrawal states: `PENDING -> PROCESSING -> SUCCESS/FAILED`
- All state transitions must be logged
- Ledger entries require: `pre_balance`, `change_amount`, `post_balance`

### Fee Calculation
Formula: `(amount * percentage) + fixed_fee`
- Global pricing in USDT
- Merchants have separate "balance" and "fee balance" accounts

## Role-Based Access
1. **Super Admin**: System config, fee rates, merchant management
2. **Merchant**: Deposits/withdrawals, API keys, reports
3. **Support**: Read-only queries

Sensitive operations (withdrawals, key export, security settings) require Google Auth (TOTP).

## Key Libraries
- `tronpy` - TRON interactions (primary)
- `web3.py` - Ethereum interactions
- `solana-py` - Solana interactions
- `cryptography` - AES-256-GCM encryption
- `clerk-backend-api` - Authentication
- `celery` - Task queue (Redis)

## Key Files (update as implemented)
- `src/core/security.py` - AES encryption utilities
- `src/core/config.py` - Pydantic Settings configuration
- `src/db/engine.py` - Async MySQL engine + session factory
- `src/chains/base.py` - ChainInterface abstract class
- `src/chains/tron.py` - TRON chain implementation
- `src/models/` - SQLModel definitions (User, Wallet, Order, Transaction, Webhook, FeeConfig, Merchant)
- `src/api/auth.py` - Clerk JWT verification + user sync
- `src/api/payment.py` - Payment API (deposit/withdraw/query)
- `src/api/merchant.py` - Merchant REST API endpoints
- `src/api/admin.py` - Admin dashboard + system management
- `src/api/webhook.py` - Webhook configuration endpoints
- `src/services/wallet_service.py` - Wallet generation + encryption
- `src/services/order_service.py` - Order management + ledger
- `src/services/webhook_service.py` - Webhook delivery + retries
- `src/workers/celery_app.py` - Celery configuration
- `src/workers/chain_scanners/` - Per-chain block scanners
- `src/workers/common_tasks.py` - Common background tasks
- `src/workers/sweeper.py` - Fund collection worker
- `docs/PAYMENT_API.md` - Payment API documentation
