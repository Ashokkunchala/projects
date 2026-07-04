"""Config routes — regions, services, accounts."""

import asyncio
import json as _json
import os

from fastapi import APIRouter, Depends, HTTPException, Response

from main import (
    AWS_REGIONS,
    AWS_SERVICES,
    AZURE_REGIONS,
    AZURE_SERVICES,
    GCP_REGIONS,
    GCP_SERVICES,
    VALID_ACCOUNT_RE,
    AccountRequest,
    _accounts_file_lock,
    _verify_token,
    _write_accounts_inplace,
)

router = APIRouter(prefix="")


@router.get("/api/regions")
async def get_regions(provider: str = "aws", _: dict = Depends(_verify_token)):
    if provider == "azure":
        return Response(
            content=_json.dumps({"regions": AZURE_REGIONS}),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    if provider == "gcp":
        return Response(
            content=_json.dumps({"regions": GCP_REGIONS}),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    return Response(
        content=_json.dumps({"regions": AWS_REGIONS}),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/services")
async def get_services(provider: str = "aws", _: dict = Depends(_verify_token)):
    if provider == "azure":
        return Response(
            content=_json.dumps({"services": AZURE_SERVICES}),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    if provider == "gcp":
        return Response(
            content=_json.dumps({"services": GCP_SERVICES}),
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    return Response(
        content=_json.dumps({"services": AWS_SERVICES}),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/api/config/accounts")
async def get_org_accounts(_: dict = Depends(_verify_token)):
    from cloud_organizations import _build_sso_profile_map, load_accounts_from_file

    sso_map = _build_sso_profile_map()
    accounts = [
        {"account_id": aid, "name": name, "email": "", "profile_name": name}
        for aid, name in sorted(sso_map.items())
    ]

    sso_ids = set(sso_map.keys())
    for acct in load_accounts_from_file():
        if acct.get("account_id") not in sso_ids:
            accounts.append(acct)

    return {"accounts": accounts}


@router.post("/api/config/accounts")
async def add_account(req: AccountRequest, _: dict = Depends(_verify_token)):
    from cloud_organizations import _build_sso_profile_map
    filepath = os.getenv("AWS_ACCOUNTS_FILE", "/app/cloud_accounts.json")

    sso_map = _build_sso_profile_map()
    if req.account_id in sso_map:
        return {"account": {
            "account_id": req.account_id,
            "name": sso_map[req.account_id],
            "email": "",
            "profile_name": sso_map[req.account_id],
        }}

    async with _accounts_file_lock:
        def _read() -> list:
            if not os.path.exists(filepath):
                return []
            try:
                with open(filepath) as f:
                    return _json.load(f).get("accounts", [])
            except Exception:
                return []

        accounts = await asyncio.to_thread(_read)

        if any(a.get("account_id") == req.account_id for a in accounts):
            raise HTTPException(status_code=400, detail="Account already exists")

        new_entry = {
            "account_id": req.account_id,
            "name": req.name,
            "email": req.email,
            "profile_name": sso_map.get(req.account_id, ""),
            "role_arn": req.role_arn if req.role_arn else f"arn:aws:iam::{req.account_id}:role/CostDetectiveRole",
        }
        accounts.append(new_entry)
        await asyncio.to_thread(_write_accounts_inplace, filepath, accounts)

    return {"account": new_entry}


@router.delete("/api/config/accounts/{account_id}")
async def remove_account(account_id: str, _: dict = Depends(_verify_token)):
    if not VALID_ACCOUNT_RE.match(account_id):
        raise HTTPException(status_code=400, detail="account_id must be exactly 12 digits")
    filepath = os.getenv("AWS_ACCOUNTS_FILE", "/app/cloud_accounts.json")

    async with _accounts_file_lock:
        def _read() -> list:
            if not os.path.exists(filepath):
                return []
            try:
                with open(filepath) as f:
                    return _json.load(f).get("accounts", [])
            except Exception:
                return []

        accounts = await asyncio.to_thread(_read)
        updated = [a for a in accounts if a.get("account_id") != account_id]
        if updated != accounts:
            await asyncio.to_thread(_write_accounts_inplace, filepath, updated)

    return {"status": "removed"}
