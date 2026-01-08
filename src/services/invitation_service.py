"""Invitation Service - Business logic for user invitations via Clerk.

This service handles sending invitations through Clerk API and managing
invitation records.
"""

from enum import Enum

from clerk_backend_api import Clerk
from clerk_backend_api.models import Invitation
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.models.user import SupportPermission, User, UserRole


class InvitationStatus(str, Enum):
    """Invitation status."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


def _get_clerk_client() -> Clerk:
    """Get Clerk API client."""
    settings = get_settings()
    return Clerk(bearer_auth=settings.clerk_secret_key)


class InvitationService:
    """Service for managing user invitations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._clerk = _get_clerk_client()

    # ============ Invite Merchant (超管邀请商户) ============

    async def invite_merchant(
        self,
        inviter: User,
        email: str,
    ) -> Invitation:
        """Invite a new merchant.

        Args:
            inviter: The super admin inviting the merchant
            email: Email address to send invitation to

        Returns:
            Clerk Invitation object

        Raises:
            ValueError: If inviter is not super admin or email invalid
        """
        if inviter.role != UserRole.SUPER_ADMIN:
            raise ValueError("Only super admin can invite merchants")

        # Check if email already exists
        from sqlmodel import select

        result = await self.db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"User with email {email} already exists")

        settings = get_settings()

        # Create invitation via Clerk API
        # Note: Clerk Python SDK uses request={} pattern for parameters
        invitation = self._clerk.invitations.create(
            request={
                "email_address": email,
                "public_metadata": {
                    "role": UserRole.MERCHANT.value,
                    "invited_by": inviter.id,
                },
                "redirect_url": f"{settings.frontend_url}/sign-up",
            }
        )

        return invitation

    # ============ Invite Support (商户邀请客服) ============

    async def invite_support(
        self,
        merchant: User,
        email: str,
        permissions: list[str],
    ) -> Invitation:
        """Invite a new support user for a merchant.

        Args:
            merchant: The merchant inviting the support user
            email: Email address to send invitation to
            permissions: List of permission strings to grant

        Returns:
            Clerk Invitation object

        Raises:
            ValueError: If merchant is invalid, email exists, or permissions invalid
        """
        if merchant.role != UserRole.MERCHANT:
            raise ValueError("Only merchants can invite support users")

        # Check if email already exists
        from sqlmodel import select

        result = await self.db.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()
        if existing:
            raise ValueError(f"User with email {email} already exists")

        # Validate permissions
        valid_permissions = {p.value for p in SupportPermission}
        for perm in permissions:
            if perm not in valid_permissions:
                raise ValueError(f"Invalid permission: {perm}")

        settings = get_settings()

        # Create invitation via Clerk API
        # Note: Clerk Python SDK uses request={} pattern for parameters
        invitation = self._clerk.invitations.create(
            request={
                "email_address": email,
                "public_metadata": {
                    "role": UserRole.SUPPORT.value,
                    "parent_id": merchant.id,
                    "permissions": permissions,
                    "invited_by": merchant.id,
                },
                "redirect_url": f"{settings.frontend_url}/sign-up",
            }
        )

        return invitation

    # ============ List Invitations ============

    async def list_invitations(
        self,
        user: User,
        status: InvitationStatus | None = None,
    ) -> list[dict]:
        """List invitations for a user.

        - Super admins see merchant invitations they sent
        - Merchants see support invitations they sent

        Args:
            user: Current user
            status: Filter by status (optional)

        Returns:
            List of invitation dicts
        """
        # Get all invitations from Clerk
        # Note: Clerk API doesn't support filtering by metadata,
        # so we fetch all and filter locally
        # SDK returns List[Invitation] directly
        invitations = self._clerk.invitations.list() or []

        # Filter based on user role and who invited
        result = []
        for inv in invitations:
            metadata = inv.public_metadata or {}

            # Super admin sees merchant invitations they sent
            if user.role == UserRole.SUPER_ADMIN:
                if metadata.get("role") == UserRole.MERCHANT.value:
                    if metadata.get("invited_by") == user.id:
                        result.append(self._invitation_to_dict(inv))

            # Merchant sees support invitations they sent
            elif user.role == UserRole.MERCHANT:
                if metadata.get("role") == UserRole.SUPPORT.value:
                    if metadata.get("parent_id") == user.id:
                        result.append(self._invitation_to_dict(inv))

        # Filter by status if specified
        if status:
            result = [r for r in result if r["status"] == status.value]

        return result

    # ============ Resend Invitation ============

    async def resend_invitation(
        self,
        user: User,
        invitation_id: str,
    ) -> Invitation:
        """Resend an invitation.

        Args:
            user: Current user (must be the original inviter)
            invitation_id: Clerk invitation ID

        Returns:
            Updated Clerk Invitation object

        Raises:
            ValueError: If invitation not found or user not authorized
        """
        # Get the invitation by listing and filtering
        # Note: Clerk SDK doesn't have a direct get method, only list
        invitations = self._clerk.invitations.list()
        invitation = None
        for inv in invitations:
            if inv.id == invitation_id:
                invitation = inv
                break

        if not invitation:
            raise ValueError(f"Invitation {invitation_id} not found")

        # Verify ownership
        metadata = invitation.public_metadata or {}
        invited_by = metadata.get("invited_by")

        if invited_by != user.id:
            raise ValueError("Not authorized to resend this invitation")

        # Revoke old invitation and create new one
        self._clerk.invitations.revoke(invitation_id=invitation_id)

        settings = get_settings()

        # Create new invitation with same metadata
        new_invitation = self._clerk.invitations.create(
            request={
                "email_address": invitation.email_address,
                "public_metadata": metadata,
                "redirect_url": f"{settings.frontend_url}/sign-up",
            }
        )

        return new_invitation

    # ============ Revoke Invitation ============

    async def revoke_invitation(
        self,
        user: User,
        invitation_id: str,
    ) -> bool:
        """Revoke a pending invitation.

        Args:
            user: Current user (must be the original inviter)
            invitation_id: Clerk invitation ID

        Returns:
            True if revoked

        Raises:
            ValueError: If invitation not found or user not authorized
        """
        # Get the invitation by listing and filtering
        invitations = self._clerk.invitations.list()
        invitation = None
        for inv in invitations:
            if inv.id == invitation_id:
                invitation = inv
                break

        if not invitation:
            raise ValueError(f"Invitation {invitation_id} not found")

        # Verify ownership
        metadata = invitation.public_metadata or {}
        invited_by = metadata.get("invited_by")

        if invited_by != user.id:
            raise ValueError("Not authorized to revoke this invitation")

        # Revoke invitation
        self._clerk.invitations.revoke(invitation_id=invitation_id)
        return True

    # ============ Helper Methods ============

    def _invitation_to_dict(self, invitation: Invitation) -> dict:
        """Convert Clerk Invitation to dict."""
        metadata = invitation.public_metadata or {}

        # Determine status
        status = "pending"
        if invitation.status:
            status = invitation.status

        return {
            "id": invitation.id,
            "email": invitation.email_address,
            "role": metadata.get("role"),
            "permissions": metadata.get("permissions", []),
            "status": status,
            "created_at": invitation.created_at,
            "expires_at": invitation.expires_at if hasattr(invitation, "expires_at") else None,
        }
