"""AKX Crypto Payment Gateway - Chain and Token API routes.

Provides REST API endpoints for chain and token management.
Business logic is delegated to ChainTokenService.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import SuperAdmin
from src.db.engine import get_db
from src.schemas.chain_token import (
    ChainCreate,
    ChainResponse,
    ChainUpdate,
    ChainWithTokens,
    TokenChainSupportCreate,
    TokenChainSupportDisplay,
    TokenChainSupportResponse,
    TokenChainSupportUpdate,
    TokenCreate,
    TokenResponse,
    TokenUpdate,
    TokenWithChains,
)
from src.services.chain_token_service import ChainTokenService

router = APIRouter(prefix="/api", tags=["chains-tokens"])


# ============ Dependency ============


def get_chain_token_service(db: Annotated[AsyncSession, Depends(get_db)]) -> ChainTokenService:
    """Create ChainTokenService instance."""
    return ChainTokenService(db)


# ============================================================================
# Chain Endpoints
# ============================================================================


@router.get("/chains", response_model=list[ChainResponse])
async def list_chains(
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
):
    """List all blockchain networks.

    Returns:
        List of chains, ordered by sort_order
    """
    return await service.list_chains(is_enabled=is_enabled)


@router.get("/chains/{chain_id}", response_model=ChainResponse)
async def get_chain(
    chain_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
):
    """Get chain details by ID."""
    chain = await service.get_chain(chain_id)
    if not chain:
        raise HTTPException(status_code=404, detail="Chain not found")
    return chain


@router.get("/chains/{chain_id}/with-tokens", response_model=ChainWithTokens)
async def get_chain_with_tokens(
    chain_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
):
    """Get chain with list of supported tokens."""
    result = await service.get_chain_with_tokens(chain_id)
    if not result:
        raise HTTPException(status_code=404, detail="Chain not found")
    return result


@router.post("/chains", response_model=ChainResponse)
async def create_chain(
    chain_data: ChainCreate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Create a new blockchain network.

    Requires super_admin role.
    """
    try:
        return await service.create_chain(chain_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/chains/{chain_id}", response_model=ChainResponse)
async def update_chain(
    chain_id: int,
    chain_data: ChainUpdate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Update chain configuration.

    Requires super_admin role.
    """
    result = await service.update_chain(chain_id, chain_data.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Chain not found")
    return result


@router.delete("/chains/{chain_id}")
async def delete_chain(
    chain_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Delete a chain.

    Requires super_admin role.
    Note: Will fail if chain has associated token supports.
    """
    deleted = await service.delete_chain(chain_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chain not found")
    return {"message": "Chain deleted successfully"}


# ============================================================================
# Token Endpoints
# ============================================================================


@router.get("/tokens", response_model=list[TokenResponse])
async def list_tokens(
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
    is_stablecoin: bool | None = Query(None, description="Filter by stablecoin status"),
):
    """List all cryptocurrency tokens.

    Returns:
        List of tokens, ordered by sort_order
    """
    return await service.list_tokens(is_enabled=is_enabled, is_stablecoin=is_stablecoin)


@router.get("/tokens/{token_id}", response_model=TokenResponse)
async def get_token(
    token_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
):
    """Get token details by ID."""
    token = await service.get_token(token_id)
    if not token:
        raise HTTPException(status_code=404, detail="Token not found")
    return token


@router.get("/tokens/{token_id}/with-chains", response_model=TokenWithChains)
async def get_token_with_chains(
    token_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
):
    """Get token with list of supported chains.

    This is the primary method for frontend: select token first,
    then show available chains for that token.
    """
    result = await service.get_token_with_chains(token_id)
    if not result:
        raise HTTPException(status_code=404, detail="Token not found")
    return result


@router.post("/tokens", response_model=TokenResponse)
async def create_token(
    token_data: TokenCreate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Create a new cryptocurrency token.

    Requires super_admin role.
    """
    try:
        return await service.create_token(token_data.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/tokens/{token_id}", response_model=TokenResponse)
async def update_token(
    token_id: int,
    token_data: TokenUpdate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Update token configuration.

    Requires super_admin role.
    """
    result = await service.update_token(token_id, token_data.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="Token not found")
    return result


@router.delete("/tokens/{token_id}")
async def delete_token(
    token_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Delete a token.

    Requires super_admin role.
    Note: Will fail if token has associated chain supports.
    """
    deleted = await service.delete_token(token_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token not found")
    return {"message": "Token deleted successfully"}


# ============================================================================
# TokenChainSupport Endpoints
# ============================================================================


@router.get("/token-chain-supports", response_model=list[TokenChainSupportDisplay])
async def list_token_chain_supports(
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    token_id: int | None = Query(None, description="Filter by token ID"),
    chain_id: int | None = Query(None, description="Filter by chain ID"),
    is_enabled: bool | None = Query(None, description="Filter by enabled status"),
):
    """List token-chain support configurations."""
    return await service.list_token_chain_supports(
        token_id=token_id, chain_id=chain_id, is_enabled=is_enabled
    )


@router.post("/token-chain-supports", response_model=TokenChainSupportResponse)
async def create_token_chain_support(
    support_data: TokenChainSupportCreate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Add token support on a specific chain.

    Requires super_admin role.
    """
    try:
        return await service.create_token_chain_support(support_data.model_dump())
    except ValueError as e:
        error_msg = str(e)
        if "not found" in error_msg:
            raise HTTPException(status_code=404, detail=error_msg)
        raise HTTPException(status_code=400, detail=error_msg)


@router.patch("/token-chain-supports/{support_id}", response_model=TokenChainSupportResponse)
async def update_token_chain_support(
    support_id: int,
    support_data: TokenChainSupportUpdate,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Update token-chain support configuration.

    Requires super_admin role.
    """
    result = await service.update_token_chain_support(
        support_id, support_data.model_dump(exclude_unset=True)
    )
    if not result:
        raise HTTPException(status_code=404, detail="Token-chain support not found")
    return result


@router.delete("/token-chain-supports/{support_id}")
async def delete_token_chain_support(
    support_id: int,
    service: Annotated[ChainTokenService, Depends(get_chain_token_service)],
    current_user: SuperAdmin,
):
    """Remove token support from a chain.

    Requires super_admin role.
    """
    deleted = await service.delete_token_chain_support(support_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Token-chain support not found")
    return {"message": "Token-chain support deleted successfully"}
