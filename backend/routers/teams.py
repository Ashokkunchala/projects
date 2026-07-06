"""Teams routes — multi-organization and RBAC management."""

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from main import _check_rate_limit, _verify_token, db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="")


class CreateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class UpdateTeamRequest(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class AddMemberRequest(BaseModel):
    user_id: int
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(admin|member|viewer)$")


class InvitationRequest(BaseModel):
    email: str = Field(max_length=254)
    role: str = Field(default="member", pattern=r"^(admin|member|viewer)$")


INVITATION_EXPIRY_HOURS = 72


async def _require_org_access(org_id: int, user_id: int, required_roles: set | None = None):
    org = await db.get_organization_by_id(org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    role = await db.get_user_role_in_org(org_id, user_id)
    if not role:
        raise HTTPException(status_code=403, detail="You are not a member of this organization")
    if required_roles and role not in required_roles:
        raise HTTPException(
            status_code=403,
            detail=f"This action requires one of these roles: {', '.join(required_roles)}",
        )
    return org, role


@router.post("/api/teams", status_code=201)
async def create_team(req: CreateTeamRequest, request: Request, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:create:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    org = await db.create_organization(req.name.strip(), user_info["user_id"])
    if not org:
        raise HTTPException(status_code=400, detail="Could not create organization")
    return org


@router.get("/api/teams")
async def list_teams(user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:list:{user_info['user_id']}", max_attempts=30, window_seconds=60)
    orgs = await db.get_organizations_by_user(user_info["user_id"])
    return orgs


@router.get("/api/teams/{org_id}")
async def get_team(org_id: int, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:get:{org_id}:{user_info['user_id']}", max_attempts=30, window_seconds=60)
    org, _ = await _require_org_access(org_id, user_info["user_id"])
    return org


@router.put("/api/teams/{org_id}")
async def update_team(org_id: int, req: UpdateTeamRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:update:{org_id}:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    org, role = await _require_org_access(org_id, user_info["user_id"], {"owner", "admin"})
    updated = await db.update_organization(org_id, req.name.strip())
    if not updated:
        raise HTTPException(status_code=400, detail="Could not update organization")
    return updated


@router.delete("/api/teams/{org_id}")
async def delete_team(org_id: int, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:delete:{org_id}:{user_info['user_id']}", max_attempts=5, window_seconds=300)
    org, role = await _require_org_access(org_id, user_info["user_id"], {"owner"})
    ok = await db.delete_organization(org_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Could not delete organization")
    return {"message": "Organization deleted"}


@router.get("/api/teams/{org_id}/members")
async def list_members(org_id: int, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:members:list:{org_id}:{user_info['user_id']}", max_attempts=30, window_seconds=60)
    await _require_org_access(org_id, user_info["user_id"])
    members = await db.get_organization_members(org_id)
    return members


@router.post("/api/teams/{org_id}/members", status_code=201)
async def add_member(org_id: int, req: AddMemberRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:members:add:{org_id}:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    await _require_org_access(org_id, user_info["user_id"], {"owner", "admin"})

    target_user = await db.get_user_by_id(req.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    existing_role = await db.get_user_role_in_org(org_id, req.user_id)
    if existing_role:
        raise HTTPException(status_code=409, detail="User is already a member of this organization")

    member = await db.add_organization_member(org_id, req.user_id, req.role, user_info["user_id"])
    if not member:
        raise HTTPException(status_code=400, detail="Could not add member")
    return member


@router.put("/api/teams/{org_id}/members/{user_id}/role")
async def change_member_role(org_id: int, user_id: int, req: UpdateMemberRoleRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:members:role:{org_id}:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    org, role = await _require_org_access(org_id, user_info["user_id"], {"owner"})

    if user_id == user_info["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot change your own role")

    target_role = await db.get_user_role_in_org(org_id, user_id)
    if not target_role:
        raise HTTPException(status_code=404, detail="User is not a member of this organization")
    if target_role == "owner":
        raise HTTPException(status_code=400, detail="Cannot change the role of the organization owner")

    ok = await db.update_member_role(org_id, user_id, req.role)
    if not ok:
        raise HTTPException(status_code=400, detail="Could not update member role")
    return {"message": "Role updated"}


@router.delete("/api/teams/{org_id}/members/{user_id}")
async def remove_member(org_id: int, user_id: int, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:members:remove:{org_id}:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    await _require_org_access(org_id, user_info["user_id"], {"owner", "admin"})

    if user_id == user_info["user_id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself from the organization")

    target_role = await db.get_user_role_in_org(org_id, user_id)
    if not target_role:
        raise HTTPException(status_code=404, detail="User is not a member of this organization")
    if target_role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove the organization owner")

    ok = await db.remove_organization_member(org_id, user_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Could not remove member")
    return {"message": "Member removed"}


@router.get("/api/teams/{org_id}/invitations")
async def list_invitations(org_id: int, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:invitations:list:{org_id}:{user_info['user_id']}", max_attempts=30, window_seconds=60)
    await _require_org_access(org_id, user_info["user_id"])
    invs = await db.get_organization_invitations(org_id)
    return invs


@router.post("/api/teams/{org_id}/invitations", status_code=201)
async def create_invitation(org_id: int, req: InvitationRequest, request: Request, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:invite:{org_id}:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    await _require_org_access(org_id, user_info["user_id"], {"owner", "admin"})

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITATION_EXPIRY_HOURS)
    inv = await db.create_invitation(
        org_id=org_id,
        email=req.email.strip().lower(),
        role=req.role,
        invited_by=user_info["user_id"],
        token=token,
        expires_at=expires_at,
    )
    if not inv:
        raise HTTPException(status_code=400, detail="Could not create invitation")

    # Send invitation email
    try:
        from notifications import send_email
        org = await db.get_organization_by_id(org_id)
        org_name = org.get("name", "Unknown Organization") if org else "Unknown Organization"
        base_url = str(request.base_url).rstrip("/")
        accept_link = f"{base_url}/teams?invite={token}"
        await send_email(
            to=req.email.strip().lower(),
            subject=f"You've been invited to {org_name} on Cost Detective",
            body_text=f"You've been invited to join '{org_name}' on Cloud Cost Detective.\n\n"
                      f"Role: {req.role}\n\n"
                      f"Click here to accept: {accept_link}\n\n"
                      f"This invitation expires in {INVITATION_EXPIRY_HOURS} hours.",
            body_html=f"<h2>You're invited to join <strong>{org_name}</strong></h2>"
                      f"<p>Role: <strong>{req.role}</strong></p>"
                      f"<p><a href=\"{accept_link}\" style=\"display:inline-block;padding:12px 24px;background:#6366f1;color:#fff;text-decoration:none;border-radius:8px;\">Accept Invitation</a></p>"
                      f"<p>This invitation expires in {INVITATION_EXPIRY_HOURS} hours.</p>",
        )
    except Exception as e:
        logger.warning("invitation.email_failed", extra={"error": str(e), "email": req.email})

    return inv


@router.post("/api/teams/invitations/{token}/accept")
async def accept_invitation(token: str, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"teams:invite:accept:{user_info['user_id']}", max_attempts=5, window_seconds=300)

    inv = await db.get_invitation_by_token(token)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if inv.get("accepted"):
        raise HTTPException(status_code=400, detail="Invitation already accepted")

    exp = inv["expires_at"]
    if isinstance(exp, str):
        exp_dt = datetime.fromisoformat(exp)
    else:
        exp_dt = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
    if exp_dt <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invitation has expired")

    user = await db.get_user_by_id(user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["email"] != inv["email"]:
        raise HTTPException(status_code=403, detail="This invitation was sent to a different email address")

    existing_role = await db.get_user_role_in_org(inv["organization_id"], user_info["user_id"])
    if existing_role:
        raise HTTPException(status_code=409, detail="You are already a member of this organization")

    ok = await db.accept_invitation(token, user_info["user_id"])
    if not ok:
        raise HTTPException(status_code=400, detail="Could not accept invitation")
    return {"message": "Invitation accepted"}
