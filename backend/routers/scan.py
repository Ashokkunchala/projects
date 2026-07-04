"""Scan routes — validate, analyze, progress WebSocket, history."""

import asyncio
import json as _json
import logging
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from main import (
    AnalyzeRequest,
    AWS_REGIONS,
    AZURE_REGIONS,
    GCP_REGIONS,
    SSOCredentialItem,
    VALID_AZURE_SERVICE_IDS,
    VALID_GCP_SERVICE_IDS,
    VALID_SERVICE_IDS,
    ValidateRequest,
    _AZURE_AVAILABLE,
    _check_rate_limit,
    _GCP_AVAILABLE,
    _is_sso_expiry_error,
    _MAX_ANALYSES_PER_USER,
    _push,
    _run_analysis,
    _validate_project_id,
    _validate_subscription_id,
    _verify_token,
    _verify_token_str,
    _redis_client,
    db,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="")


@router.post("/api/validate")
async def validate_credentials(req: ValidateRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"validate:{user_info['user_id']}", max_attempts=10, window_seconds=60)
    provider = req.cloud_provider.lower()

    if provider == "aws":
        import boto3 as _b3
        import botocore.exceptions

        if req.sso_credentials:
            try:
                sc = req.sso_credentials[0]
                sess = _b3.Session(
                    aws_access_key_id=sc.access_key,
                    aws_secret_access_key=sc.secret_key,
                    aws_session_token=sc.session_token or None,
                )
                identity = sess.client("sts", region_name="us-east-1").get_caller_identity()
                account = identity.get("Account", "")
                n = len(req.sso_credentials)
                return {"ok": True, "message": f"SSO credentials verified — {n} account{'s' if n != 1 else ''} ready to scan"}
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail="SSO credentials have expired. Please re-authenticate via AWS SSO in Settings.",
                )

        key_id = (req.aws_access_key_id or "").strip()
        secret = (req.aws_secret_access_key or "").strip()
        use_org = req.use_organizations
        if not key_id or not secret:
            if not use_org:
                raise HTTPException(
                    status_code=400,
                    detail="Enter your AWS Access Key ID and Secret Access Key in the Settings panel.",
                )
        try:
            if key_id and secret:
                session = _b3.Session(aws_access_key_id=key_id, aws_secret_access_key=secret)
            else:
                session = _b3.Session()
            sts = session.client("sts", region_name="us-east-1")
            identity = sts.get_caller_identity()
            account = identity.get("Account", "")
        except botocore.exceptions.NoCredentialsError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "AWS credentials not found. Enter your Access Key ID and Secret Access Key in the Settings panel."
                ),
            )
        except botocore.exceptions.ProfileNotFound:
            raise HTTPException(status_code=400, detail="AWS SSO profile not found. Run 'aws sso login' on the host and ensure ~/.aws/config is mounted.")
        except Exception as e:
            if _is_sso_expiry_error(e):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Your AWS Organizations session has expired. "
                        "Please run 'aws sso login' to re-authenticate."
                    ),
                )
            raise HTTPException(
                status_code=400,
                detail="AWS credential check failed. Verify your credentials are configured correctly.",
            )

        if req.use_organizations and req.accounts:
            from cloud_organizations import _build_sso_profile_map
            sso_map = _build_sso_profile_map()
            missing = [aid for aid in req.accounts if aid not in sso_map]
            if missing:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"No SSO profile found for account(s): {', '.join(missing)}. "
                        "Run 'aws sso login' or add the account manually."
                    ),
                )

        return {"ok": True, "message": f"AWS credentials verified (account: {account})"}

    elif provider == "azure":
        if not _AZURE_AVAILABLE:
            raise HTTPException(
                status_code=400,
                detail="Azure SDK not installed. Rebuild the backend container.",
            )
        sub_id = _validate_subscription_id(req.subscription_id or "")
        _az_tenant = (req.azure_tenant_id or "").strip()
        _az_client = (req.azure_client_id or "").strip()
        _az_secret = (req.azure_client_secret or "").strip()
        try:
            from azure.mgmt.resource import SubscriptionClient as _SubClient
            import azure_scanner as _az
            cred = _az._get_credential(_az_tenant, _az_client, _az_secret)
            sub_client = _SubClient(cred)
            sub = sub_client.subscriptions.get(sub_id)
            sub_name = sub.display_name or sub_id
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "does not exist" in msg or "404" in msg:
                raise HTTPException(
                    status_code=400,
                    detail="Azure subscription not found. Verify the Subscription ID and your account permissions.",
                )
            if "credential" in msg or "authentication" in msg or "unauthorized" in msg or "401" in msg:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Azure credentials could not be verified. "
                        "Enter your Tenant ID, Client ID, and Client Secret in the Azure Credentials panel, "
                        "or ensure DefaultAzureCredential is available on the server."
                    ),
                )
            raise HTTPException(status_code=400, detail="Azure validation failed. Check your credentials and subscription ID.")

        return {"ok": True, "message": f"Azure credentials verified (subscription: {sub_name})"}

    elif provider == "gcp":
        if not _GCP_AVAILABLE:
            raise HTTPException(
                status_code=400,
                detail="GCP SDK not installed. Rebuild the backend container.",
            )
        proj_id = _validate_project_id(req.project_id or "")
        try:
            import gcp_scanner as _gcp
            from googleapiclient.discovery import build as _gcp_build
            api_key = (req.gcp_api_key or "").strip()
            creds = _gcp._get_credentials_from_key(api_key) if api_key else _gcp._get_credentials()
            if creds is None:
                svc = _gcp_build("cloudresourcemanager", "v1", developerKey=api_key)
            else:
                svc = _gcp_build("cloudresourcemanager", "v1", credentials=creds)
            project = svc.projects().get(projectId=proj_id).execute()
            proj_name = project.get("name", proj_id)
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "not found" in msg or "404" in msg:
                raise HTTPException(
                    status_code=400,
                    detail="GCP project not found. Verify the Project ID and your account permissions.",
                )
            if "credential" in msg or "authentication" in msg or "unauthorized" in msg or "403" in msg:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "GCP credentials could not be verified. "
                        "Set GOOGLE_APPLICATION_CREDENTIALS or GCP_CREDENTIALS_JSON "
                        "environment variable."
                    ),
                )
            raise HTTPException(status_code=400, detail="GCP validation failed. Check your credentials and project ID.")

        return {"ok": True, "message": f"GCP credentials verified (project: {proj_name})"}

    else:
        raise HTTPException(status_code=400, detail=f"Unknown cloud provider: {provider}")


@router.post("/api/analyze")
async def analyze(req: AnalyzeRequest, user_info: dict = Depends(_verify_token)):
    provider = req.cloud_provider

    if provider == "azure":
        valid_regions = set(AZURE_REGIONS)
        valid_services = VALID_AZURE_SERVICE_IDS
    elif provider == "gcp":
        valid_regions = set(GCP_REGIONS)
        valid_services = VALID_GCP_SERVICE_IDS
    else:
        valid_regions = set(AWS_REGIONS)
        valid_services = VALID_SERVICE_IDS

    invalid_regions = [r for r in req.regions if r not in valid_regions]
    if invalid_regions:
        raise HTTPException(status_code=400, detail=f"Unknown region(s): {', '.join(invalid_regions)}")

    invalid_services = [s for s in req.services if s not in valid_services]
    if invalid_services:
        raise HTTPException(status_code=400, detail=f"Unknown service(s): {', '.join(invalid_services)}")

    if provider == "aws" and req.use_organizations and req.accounts is not None and len(req.accounts) == 0:
        raise HTTPException(status_code=400, detail="Select at least one account when using Organizations mode")

    analysis_id = str(uuid.uuid4())
    user_id = user_info["user_id"]

    _running = await db.get_running_analyses_for_user(user_id)
    _running_ids = {a["id"] for a in (_running or [])}
    if len(_running_ids) >= _MAX_ANALYSES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {_MAX_ANALYSES_PER_USER} analyses running. Wait for one to finish.",
        )

    if provider == "azure":
        _validate_subscription_id(req.subscription_id or "")
    if provider == "gcp":
        _validate_project_id(req.project_id or "")

    await db.create_analysis(
        analysis_id, user_id, req.regions, req.services,
        req.accounts or [], cloud_provider=provider,
    )
    asyncio.create_task(_run_analysis(analysis_id, user_id, req))

    return {"analysis_id": analysis_id, "status": "started"}


@router.websocket("/ws/progress/{analysis_id}")
async def ws_progress(websocket: WebSocket, analysis_id: str):
    token = websocket.cookies.get("token", "")
    user_info = _verify_token_str(token)
    if not user_info:
        await websocket.close(code=4001)
        return
    await websocket.accept()

    saved = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    progress_msgs = await _redis_client.progress_get_all(analysis_id)
    in_flight = len(progress_msgs) > 0 and progress_msgs[-1].get("status") not in ("complete", "error")

    if not in_flight and not saved:
        await websocket.send_json({"message": "Analysis not found", "status": "error"})
        return

    if in_flight and saved is None:
        await websocket.send_json({"message": "Access denied", "status": "error"})
        return

    if not in_flight:
        if saved and saved.get("analysis_result"):
            await websocket.send_json({"message": "Analysis complete!", "status": "complete", "data": saved["analysis_result"]})
        elif saved and saved.get("status") == "failed":
            await websocket.send_json({"message": saved.get("error_message", "Analysis failed"), "status": "error"})
        else:
            await websocket.send_json({"message": "Analysis not found", "status": "error"})
        return

    sent_index = len(progress_msgs)
    idle_ticks = 0
    keepalive_ticks = 0

    try:
        while True:
            messages = await _redis_client.progress_get_all(analysis_id)

            if messages:
                idle_ticks = 0
                keepalive_ticks = 0
                for msg in messages[sent_index:]:
                    await websocket.send_json(msg)
                    sent_index += 1
                    if msg.get("status") in ("complete", "error"):
                        return
            else:
                idle_ticks += 1
                if idle_ticks > 300:
                    await websocket.send_json({"message": "Analysis not found", "status": "error"})
                    return

            keepalive_ticks += 1
            if keepalive_ticks >= 100:
                keepalive_ticks = 0
                await websocket.send_json({"message": "", "status": "keepalive"})

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("websocket.error", extra={"analysis_id": analysis_id, "error": str(exc)})


@router.get("/api/history")
async def get_history(
    user_info: dict = Depends(_verify_token),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=limit, offset=offset)
    return {"analyses": analyses}


@router.get("/api/history/{analysis_id}")
async def get_analysis(analysis_id: str, user_info: dict = Depends(_verify_token)):
    analysis = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.delete("/api/history/{analysis_id}", status_code=200)
async def delete_analysis(analysis_id: str, user_info: dict = Depends(_verify_token)):
    deleted = await db.delete_analysis(analysis_id, user_info["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"status": "deleted"}
