"""AKX Crypto Payment Gateway - Chain and Token API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db.engine import get_session
from src.models.chain import Chain
from src.models.token import Token, TokenChainSupport
from src.schemas.chain_token import (
    ChainCreate,
    ChainResponse,
    ChainUpdate,
    ChainWithTokens,
    TokenChainSupportCreate,
    TokenChainSupportResponse,
    TokenChainSupportUpdate,
    TokenChainSupportWithDetails,
    TokenCreate,
    TokenResponse,
    TokenUpdate,
    TokenWithChains,
)

router = APIRouter(prefix="/api", tags=["chains-tokens"])


# ============================================================================
# Chain Endpoints
# ============================================================================

@router.get("/chains", response_model=list[ChainResponse])
async def list_chains(
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
    session: AsyncSession = Depends(get_session),
):
    """List all blockchain networks.

    Returns:
        List of chains, ordered by sort_order
    """
    query = select(Chain).order_by(Chain.sort_order, Chain.id)

    if is_enabled is not None:
        query = query.where(Chain.is_enabled == is_enabled)

    result = await session.execute(query)
    chains = result.scalars().all()
    return chains


@router.get("/chains/{chain_id}", response_model=ChainResponse)
async def get_chain(
    chain_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get chain details by ID."""
    chain = await session.get(Chain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain


@router.get("/chains/{chain_id}/with-tokens", response_model=ChainWithTokens)
async def get_chain_with_tokens(
    chain_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get chain with list of supported tokens."""
    chain = await session.get(Chain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    # Get supported tokens
    query = (
        select(TokenChainSupport, Token)
        .join(Token)
        .where(TokenChainSupport.chain_id == chain_id)
        .where(TokenChainSupport.is_enabled)
        .order_by(Token.sort_order, Token.id)
    )
    result = await session.execute(query)
    supports = result.all()

    supported_tokens = []
    for support, token in supports:
        supported_tokens.append({
            "token_id": token.id,
            "token_code": token.code,
            "token_name": token.name,
            "contract_address": support.contract_address,
            "decimals": support.decimals or token.decimals,
            "is_native": support.is_native,
            "min_deposit": support.min_deposit,
            "min_withdrawal": support.min_withdrawal,
            "withdrawal_fee": support.withdrawal_fee,
        })

    chain_dict = chain.model_dump()
    chain_dict["supported_tokens"] = supported_tokens
    return chain_dict


@router.post("/chains", response_model=ChainResponse)
async def create_chain(
    chain_data: ChainCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new blockchain network.

    Requires super_admin role.
    """
    # Check if code already exists
    existing = await session.execute(select(Chain).where(Chain.code == chain_data.code))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Chain code already exists")

    chain = Chain(**chain_data.model_dump())
    session.add(chain)
    await session.commit()
    await session.refresh(chain)
    return chain


@router.patch("/chains/{chain_id}", response_model=ChainResponse)
async def update_chain(
    chain_id: int,
    chain_data: ChainUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update chain configuration.

    Requires super_admin role.
    """
    chain = await session.get(Chain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    # Update only provided fields
    update_data = chain_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(chain, field, value)

    from datetime import datetime
    chain.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(chain)
    return chain


@router.delete("/chains/{chain_id}")
async def delete_chain(
    chain_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a chain.

    Requires super_admin role.
    Note: Will fail if chain has associated token supports.
    """
    chain = await session.get(Chain, chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    await session.delete(chain)
    await session.commit()
    return {"message": "Chain deleted successfully"}


# ============================================================================
# Token Endpoints
# ============================================================================

@router.get("/tokens", response_model=list[TokenResponse])
async def list_tokens(
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
    is_stablecoin: bool | None = Query(
        None, description="Filter by stablecoin status"
    ),
    session: AsyncSession = Depends(get_session),
):
    """List all cryptocurrency tokens.

    Returns:
        List of tokens, ordered by sort_order
    """
    query = select(Token).order_by(Token.sort_order, Token.id)

    if is_enabled is not None:
        query = query.where(Token.is_enabled == is_enabled)

    if is_stablecoin is not None:
        query = query.where(Token.is_stablecoin == is_stablecoin)

    result = await session.execute(query)
    tokens = result.scalars().all()
    return tokens


@router.get("/tokens/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get token details by ID."""
    token = await session.get(Token, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.get("/tokens/{token_id}/with-chains", response_model=TokenWithChains)
async def get_token_with_chains(
    token_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Get token with list of supported chains.

    This is the primary method for frontend: select token first,
    then show available chains for that token.
    """
    token = await session.get(Token, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Get supported chains
    query = (
        select(TokenChainSupport, Chain)
        .join(Chain)
        .where(TokenChainSupport.token_id == token_id)
        .where(TokenChainSupport.is_enabled)
        .where(Chain.is_enabled)
        .order_by(Chain.sort_order, Chain.id)
    )
    result = await session.execute(query)
    supports = result.all()

    supported_chains = []
    for support, chain in supports:
        supported_chains.append({
            "chain_id": chain.id,
            "chain_code": chain.code,
            "chain_name": chain.name,
            "contract_address": support.contract_address,
            "decimals": support.decimals or token.decimals,
            "is_native": support.is_native,
            "min_deposit": support.min_deposit,
            "min_withdrawal": support.min_withdrawal,
            "withdrawal_fee": support.withdrawal_fee,
            "confirmation_blocks": chain.confirmation_blocks,
        })

    token_dict = token.model_dump()
    token_dict["supported_chains"] = supported_chains
    return token_dict


@router.post("/tokens", response_model=TokenResponse)
async def create_token(
    token_data: TokenCreate,
    session: AsyncSession = Depends(get_session),
):
    """Create a new cryptocurrency token.

    Requires super_admin role.
    """
    # Check if code already exists
    existing = await session.execute(select(Token).where(Token.code == token_data.code))
    if existing.scalars().first():
        raise HTTPException(status_code=400, detail="Token code already exists")

    token = Token(**token_data.model_dump())
    session.add(token)
    await session.commit()
    await session.refresh(token)
    return token


@router.patch("/tokens/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: int,
    token_data: TokenUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update token configuration.

    Requires super_admin role.
    """
    token = await session.get(Token, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    # Update only provided fields
    update_data = token_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(token, field, value)

    from datetime import datetime
    token.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(token)
    return token


@router.delete("/tokens/{token_id}")
async def delete_token(
    token_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Delete a token.

    Requires super_admin role.
    Note: Will fail if token has associated chain supports.
    """
    token = await session.get(Token, token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    await session.delete(token)
    await session.commit()
    return {"message": "Token deleted successfully"}


# ============================================================================
# TokenChainSupport Endpoints
# ============================================================================

@router.get(
    "/token-chain-supports", response_model=list[TokenChainSupportWithDetails]
)
async def list_token_chain_supports(
    token_id: int | None = Query(None, description="Filter by token ID"),
    chain_id: int | None = Query(None, description="Filter by chain ID"),
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
    session: AsyncSession = Depends(get_session),
):
    """List token-chain support configurations."""
    query = select(TokenChainSupport, Token, Chain).join(Token).join(Chain)

    if token_id is not None:
        query = query.where(TokenChainSupport.token_id == token_id)

    if chain_id is not None:
        query = query.where(TokenChainSupport.chain_id == chain_id)

    if is_enabled is not None:
        query = query.where(TokenChainSupport.is_enabled == is_enabled)

    result = await session.execute(query)
    supports_data = result.all()

    supports = []
    for support, token, chain in supports_data:
        support_dict = support.model_dump()
        support_dict["token"] = token
        support_dict["chain"] = chain
        supports.append(support_dict)

    return supports


@router.post("/token-chain-supports", response_model=TokenChainSupportResponse)
async def create_token_chain_support(
    support_data: TokenChainSupportCreate,
    session: AsyncSession = Depends(get_session),
):
    """Add token support on a specific chain.

    Requires super_admin role.
    """
    # Verify token and chain exist
    token = await session.get(Token, support_data.token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")

    chain = await session.get(Chain, support_data.chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")

    # Check if support already exists
    existing = await session.execute(
        select(TokenChainSupport)
        .where(TokenChainSupport.token_id == support_data.token_id)
        .where(TokenChainSupport.chain_id == support_data.chain_id)
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail="Token-chain support already exists"
        )

    support = TokenChainSupport(**support_data.model_dump())
    session.add(support)
    await session.commit()
    await session.refresh(support)
    return support


@router.patch("/token-chain-supports/{support_id}", response_model=TokenChainSupportResponse)
async def update_token_chain_support(
    support_id: int,
    support_data: TokenChainSupportUpdate,
    session: AsyncSession = Depends(get_session),
):
    """Update token-chain support configuration.

    Requires super_admin role.
    """
    support = await session.get(TokenChainSupport, support_id)
    if not support:
        raise HTTPException(status_code=404, detail="Token-chain support not found")

    # Update only provided fields
    update_data = support_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(support, field, value)

    from datetime import datetime
    support.updated_at = datetime.utcnow()

    await session.commit()
    await session.refresh(support)
    return support


@router.delete("/token-chain-supports/{support_id}")
async def delete_token_chain_support(
    support_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Remove token support from a chain.

    Requires super_admin role.
    """
    support = await session.get(TokenChainSupport, support_id)
    if not support:
        raise HTTPException(status_code=404, detail="Token-chain support not found")

    await session.delete(support)
    await session.commit()
    return {"message": "Token-chain support deleted successfully"}
