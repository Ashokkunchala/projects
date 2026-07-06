"""AI Cloud Cost Detective — FastAPI backend (production-grade, Redis-backed)."""

import asyncio
import csv
import io
import json as _json
import logging
import os
import re
import secrets
import ssl
import tempfile
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from time import time
from typing import Optional

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Cookie, Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator

load_dotenv()

from log_config import configure_logging
configure_logging()
logger = logging.getLogger(__name__)

import ai_analyzer
import cloud_scanner
import db
import redis_client as _redis_client
import export_utils as _export_utils
from cloud_organizations import resolve_scan_credentials

try:
    import azure_scanner as _azure_scanner
    _AZURE_AVAILABLE = True
except ImportError:
    _AZURE_AVAILABLE = False

try:
    import gcp_scanner as _gcp_scanner
    _GCP_AVAILABLE = True
except ImportError:
    _GCP_AVAILABLE = False

try:
    import free_tier as _free_tier
    _FREE_TIER_AVAILABLE = True
except ImportError:
    _FREE_TIER_AVAILABLE = False

try:
    import free_tier_usage as _free_tier_usage
    import infra_visualizer as _infra_visualizer
    _FEATURES_AVAILABLE = True
except ImportError:
    _FEATURES_AVAILABLE = False

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = 8

if not JWT_SECRET or len(JWT_SECRET) < 32:
    raise RuntimeError(
        "JWT_SECRET must be set to a random string of at least 32 characters. "
        "Generate one with: python3 -c \"import secrets; print(secrets.token_hex(32))\""
    )

# Redis-backed state (rate limiting, scan progress, SSO sessions).
# Falls back to in-memory when Redis is unavailable — see redis_client.py.
_MAX_CONCURRENT_SCANS = int(os.getenv("MAX_CONCURRENT_SCANS", "5"))
_MAX_ANALYSES_PER_USER = int(os.getenv("MAX_ANALYSES_PER_USER", "3"))
_analysis_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_SCANS)

# Lock for concurrent file writes to cloud_accounts.json
_accounts_file_lock = asyncio.Lock()

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
VALID_ACCOUNT_RE = re.compile(r'^\d{12}$')
# Azure subscription IDs are UUIDs
AZURE_SUB_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
# GCP project IDs: 6–30 lowercase letters/digits/hyphens, must start with letter
GCP_PROJECT_RE = re.compile(r'^[a-z][a-z0-9\-]{4,28}[a-z0-9]$')


async def _check_rate_limit(key: str, max_attempts: int = 10, window_seconds: int = 60):
    allowed = await _redis_client.rate_limit_check(key, max_attempts, window_seconds)
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait before trying again.")


# ─── lifespan ────────────────────────────────────────────────────────────────

_ANALYSIS_RETENTION_DAYS = int(os.getenv("ANALYSIS_RETENTION_DAYS", "2"))


async def _history_purge_loop():
    """Background task: delete old analyses and expired revoked tokens every 12 hours."""
    while True:
        try:
            n = await db.purge_old_analyses(days=_ANALYSIS_RETENTION_DAYS)
            if n:
                logger.info("purge.analyses.complete", extra={"deleted": n, "days": _ANALYSIS_RETENTION_DAYS})
            await db.purge_revoked_tokens()
        except Exception as exc:
            logger.error("purge.error", extra={"error": str(exc)}, exc_info=exc)
        await asyncio.sleep(12 * 3600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await db.create_tables()
    await db.fail_stale_analyses()
    await _redis_client.init_redis()

    # Guard: refuse to run with multiple workers without Redis
    workers = int(os.getenv("UVICORN_WORKERS", "1"))
    if workers > 1 and _redis_client.is_fallback():
        logger.error(
            "startup.multi_worker_no_redis",
            extra={
                "workers": workers,
                "detail": (
                    "UVICORN_WORKERS > 1 requires Redis for shared state. "
                    "Rate limiting, SSO sessions, and scan progress will break silently "
                    "across processes. Set UVICORN_WORKERS=1 or configure REDIS_URL."
                ),
            },
        )

    # Run an immediate purge on startup, then every 12 hours
    asyncio.create_task(_history_purge_loop())

    # Start anomaly detection background loop
    try:
        from anomaly_detector import anomaly_check_loop
        asyncio.create_task(anomaly_check_loop())
        logger.info("anomaly.check.started")
    except Exception as e:
        logger.warning("anomaly.check.not_started", extra={"error": str(e)})

    yield
    await _redis_client.close_redis()
    await db.close_pool()


# ─── app setup ───────────────────────────────────────────────────────────────

_DEBUG = os.getenv("DEBUG", "false").lower() == "true"
# httpOnly cookies require HTTPS in production; disable only when running plain HTTP locally
_COOKIE_SECURE = not _DEBUG

app = FastAPI(
    title="AI Cloud Cost Detective",
    description=(
        "Multi-cloud cost analysis backend. Scans AWS, Azure, and GCP resources "
        "and returns prioritised cost-saving recommendations via AI or built-in rules.\n\n"
        "**Interactive docs** are available at `/docs` (Swagger UI) and `/redoc` (ReDoc) "
        "when `DEBUG=true`. To generate a static OpenAPI spec for CI or integrators:\n"
        "```\n"
        "python3 -c \"from main import app; import json; print(json.dumps(app.openapi(), indent=2))\" "
        "> openapi.json\n"
        "```"
    ),
    lifespan=lifespan,
    # Docs are only served in debug/dev mode. In production, generate a static
    # openapi.json at build time (see description above) and commit it to the repo.
    docs_url="/docs" if _DEBUG else None,
    redoc_url="/redoc" if _DEBUG else None,
    openapi_url="/openapi.json" if _DEBUG else None,
)

# Trust X-Real-IP only from the Docker internal network (172.18.x.x),
# not from arbitrary sources — prevents IP spoofing via X-Forwarded-For.
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="172.18.0.0/16")


@app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    """Attach a request-ID to every request for log correlation."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ALLOWED_ORIGINS: comma-separated list of allowed origins, or "*" to allow all.
# Example in backend/.env:
#   ALLOWED_ORIGINS=http://1.2.3.4:3000,http://myapp.com
_raw_origins = os.getenv("ALLOWED_ORIGINS", "")
_CORS_ORIGINS: list[str] | str = (
    "*"
    if _raw_origins.strip() == "*"
    else [
        o.strip()
        for o in _raw_origins.split(",")
        if o.strip()
    ] or [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=_CORS_ORIGINS != "*",
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── observability ────────────────────────────────────────────────────────────

# Expose a Prometheus-compatible /metrics endpoint when ENABLE_METRICS=true.
# Scrape from within the Docker network; not meant for public exposure.
if os.getenv("ENABLE_METRICS", "false").lower() == "true":
    try:
        from prometheus_fastapi_instrumentator import Instrumentator
        Instrumentator(
            should_group_status_codes=True,
            should_ignore_untemplated=True,
            excluded_handlers=["/health", "/metrics"],
        ).instrument(app).expose(app)
        logger.info("metrics.enabled", extra={"endpoint": "/metrics"})
    except ImportError:
        logger.warning("metrics.disabled", extra={"reason": "prometheus-fastapi-instrumentator not installed"})

# ─── auth helpers ─────────────────────────────────────────────────────────────

def _create_token(user_id: int, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        # email omitted — user_id is sufficient; avoids PII in token
        "jti": str(uuid.uuid4()),
        "exp": now + timedelta(hours=JWT_EXPIRY_HOURS),
        "iat": now,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def _check_revoked(payload: dict) -> None:
    jti = payload.get("jti")
    if jti and await db.is_token_revoked(jti):
        raise HTTPException(status_code=401, detail="Token has been revoked — please log in again")


def _decode_token(raw: str) -> dict:
    try:
        return jwt.decode(raw, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired — please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


_bearer = HTTPBearer(auto_error=False)

async def _verify_token(
    token_cookie: Optional[str] = Cookie(default=None, alias="token"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    raw = token_cookie or (credentials.credentials if credentials else None)
    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = _decode_token(raw)
    await _check_revoked(payload)
    return payload


def _verify_token_str(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return {}


# ─── request / response models ────────────────────────────────────────────────

_DUMMY_HASH = bcrypt.hashpw(b"dummy-constant-password", bcrypt.gensalt()).decode()


class AuthRequest(BaseModel):
    """Used for signup (kept for schema compatibility) — min 8 chars."""
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not EMAIL_RE.match(v.strip()):
            raise ValueError("Invalid email address")
        return v.strip().lower()


class LoginRequest(BaseModel):
    """Login — no min_length so short/wrong passwords always get 401, not 422."""
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Invalid email address")
        return v


class SSOCredentialItem(BaseModel):
    """Typed SSO credential — replaces unvalidated Optional[list]."""
    account_id: str = Field(pattern=r'^\d{12}$')
    account_name: str = Field(max_length=256)
    access_key: str = Field(min_length=16, max_length=128)
    secret_key: str = Field(min_length=32, max_length=256)
    session_token: Optional[str] = Field(default=None, max_length=4096)


class AnalyzeRequest(BaseModel):
    cloud_provider: str = "aws"
    regions: list[str] = Field(min_length=1)
    services: list[str] = Field(min_length=1)
    accounts: Optional[list[str]] = None
    use_organizations: bool = False
    # Azure
    subscription_id: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    # GCP
    project_id: Optional[str] = None
    gcp_api_key: Optional[str] = None
    # AWS static credentials
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    # AI engine (optional — overrides server env vars)
    ai_provider: Optional[str] = None
    ai_api_key: Optional[str] = None
    # SSO pre-authenticated credentials — strictly typed to catch malformed payloads early
    sso_credentials: Optional[list[SSOCredentialItem]] = None

    @field_validator("cloud_provider")
    @classmethod
    def validate_cloud_provider(cls, v: str) -> str:
        if v not in ("aws", "azure", "gcp"):
            raise ValueError("cloud_provider must be 'aws', 'azure', or 'gcp'")
        return v

    @field_validator("accounts")
    @classmethod
    def validate_accounts(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for aid in v:
            if not VALID_ACCOUNT_RE.match(str(aid)):
                raise ValueError(f"Invalid account ID: {aid!r} — must be exactly 12 digits")
        return v


AWS_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1",
    "eu-north-1", "ap-northeast-1", "ap-northeast-2",
    "ap-southeast-1", "ap-southeast-2", "ap-south-1",
    "sa-east-1", "ca-central-1", "me-south-1",
]

AWS_SERVICES = [
    # ── Compute ──────────────────────────────────────────────────────────────
    {"id": "kubernetes",        "name": "Kubernetes (EKS)",              "description": "EKS clusters, node groups, and worker nodes"},
    {"id": "ec2",               "name": "EC2 / EBS / EIP / NAT",       "description": "Instances, volumes, snapshots, Elastic IPs, NAT gateways, CloudWatch Logs"},
    {"id": "elb",               "name": "Load Balancers",               "description": "ALB, NLB, and Classic load balancers"},
    {"id": "autoscaling",       "name": "Auto Scaling",                 "description": "Auto Scaling Groups"},
    {"id": "ecs",               "name": "ECS",                         "description": "Elastic Container Service clusters and services"},
    {"id": "eks",               "name": "EKS",                         "description": "Elastic Kubernetes Service clusters"},
    {"id": "ecr",               "name": "ECR",                         "description": "Elastic Container Registry repositories"},
    {"id": "app_runner",        "name": "App Runner",                  "description": "App Runner services"},
    {"id": "elastic_beanstalk", "name": "Elastic Beanstalk",           "description": "Beanstalk environments"},
    {"id": "batch",             "name": "AWS Batch",                   "description": "Batch compute environments and job queues"},
    {"id": "lightsail",         "name": "Lightsail",                   "description": "Lightsail instances and disks"},
    # ── Databases ────────────────────────────────────────────────────────────
    {"id": "rds",               "name": "RDS",                         "description": "Relational databases, clusters, snapshots"},
    {"id": "elasticache",       "name": "ElastiCache",                 "description": "Redis and Memcached clusters"},
    {"id": "dynamodb",          "name": "DynamoDB",                    "description": "NoSQL tables"},
    {"id": "dax",               "name": "DynamoDB Accelerator (DAX)",  "description": "DAX clusters"},
    {"id": "redshift",          "name": "Redshift",                    "description": "Data warehouse clusters"},
    {"id": "documentdb",        "name": "DocumentDB",                  "description": "MongoDB-compatible clusters"},
    {"id": "neptune",           "name": "Neptune",                     "description": "Graph database clusters"},
    {"id": "timestream",        "name": "Timestream",                  "description": "Time-series databases"},
    {"id": "qldb",              "name": "QLDB",                        "description": "Quantum Ledger Database"},
    {"id": "keyspaces",         "name": "Keyspaces",                   "description": "Cassandra-compatible keyspaces"},
    {"id": "memorydb",          "name": "MemoryDB",                    "description": "Redis-compatible in-memory clusters"},
    {"id": "dms",               "name": "Database Migration Service",  "description": "DMS replication instances and tasks"},
    # ── Storage ──────────────────────────────────────────────────────────────
    {"id": "s3",                "name": "S3",                          "description": "Object storage buckets (global)"},
    {"id": "efs",               "name": "EFS",                         "description": "Elastic File System file systems"},
    {"id": "fsx",               "name": "FSx",                         "description": "Managed file systems (Lustre, Windows, ONTAP, OpenZFS)"},
    {"id": "backup",            "name": "AWS Backup",                  "description": "Backup vaults and recovery points"},
    # ── Serverless ───────────────────────────────────────────────────────────
    {"id": "lambda",            "name": "Lambda",                      "description": "Serverless functions"},
    # ── Networking & CDN ─────────────────────────────────────────────────────
    {"id": "cloudfront",        "name": "CloudFront",                  "description": "CDN distributions (global)"},
    {"id": "apigateway",        "name": "API Gateway",                 "description": "REST and HTTP APIs"},
    {"id": "transit_gateway",   "name": "Transit Gateway",             "description": "Transit gateways and attachments"},
    {"id": "vpc_endpoints",     "name": "VPC Endpoints",               "description": "Interface and gateway VPC endpoints"},
    {"id": "global_accelerator","name": "Global Accelerator",          "description": "Global accelerators (global)"},
    {"id": "direct_connect",    "name": "Direct Connect",              "description": "Dedicated network connections"},
    {"id": "network_firewall",  "name": "Network Firewall",            "description": "Managed network firewalls"},
    {"id": "route53",           "name": "Route 53",                    "description": "DNS hosted zones and health checks (global)"},
    {"id": "transfer_family",   "name": "Transfer Family",             "description": "SFTP/FTP/FTPS servers"},
    {"id": "waf",               "name": "WAF",                         "description": "Web Application Firewall ACLs"},
    # ── Messaging ────────────────────────────────────────────────────────────
    {"id": "sqs",               "name": "SQS",                         "description": "Simple Queue Service queues"},
    {"id": "sns",               "name": "SNS",                         "description": "Simple Notification Service topics"},
    {"id": "kinesis",           "name": "Kinesis",                     "description": "Kinesis Data Streams"},
    {"id": "msk",               "name": "MSK (Managed Kafka)",         "description": "Managed Streaming for Apache Kafka clusters"},
    {"id": "mq",                "name": "Amazon MQ",                   "description": "ActiveMQ and RabbitMQ brokers"},
    {"id": "eventbridge",       "name": "EventBridge",                 "description": "Event buses and rules"},
    {"id": "step_functions",    "name": "Step Functions",              "description": "State machines"},
    {"id": "appsync",           "name": "AppSync",                     "description": "GraphQL APIs"},
    # ── Analytics ────────────────────────────────────────────────────────────
    {"id": "emr",               "name": "EMR",                         "description": "Elastic MapReduce clusters"},
    {"id": "glue",              "name": "AWS Glue",                    "description": "ETL jobs and crawlers"},
    {"id": "athena",            "name": "Athena",                      "description": "Serverless query workgroups"},
    {"id": "opensearch",        "name": "OpenSearch",                  "description": "OpenSearch Service domains"},
    {"id": "quicksight",        "name": "QuickSight",                  "description": "BI users and datasets (global)"},
    # ── AI / ML ──────────────────────────────────────────────────────────────
    {"id": "sagemaker",         "name": "SageMaker",                   "description": "Notebook instances, endpoints, training jobs"},
    {"id": "bedrock",           "name": "Bedrock",                     "description": "Foundation model custom jobs"},
    {"id": "rekognition",       "name": "Rekognition",                 "description": "Custom labels projects"},
    {"id": "comprehend",        "name": "Comprehend",                  "description": "Document classifiers and entity recognizers"},
    {"id": "lex",               "name": "Lex",                         "description": "Chatbot definitions"},
    # ── Security ─────────────────────────────────────────────────────────────
    {"id": "kms",               "name": "KMS",                         "description": "Customer-managed encryption keys"},
    {"id": "secretsmanager",    "name": "Secrets Manager",             "description": "Stored secrets"},
    {"id": "ssm",               "name": "Systems Manager",             "description": "SSM parameters and maintenance windows"},
    {"id": "acm_pca",           "name": "ACM Private CA",              "description": "Private certificate authorities"},
    {"id": "guardduty",         "name": "GuardDuty",                   "description": "Threat detection detectors"},
    {"id": "macie",             "name": "Macie",                       "description": "Data classification sessions"},
    {"id": "inspector",         "name": "Inspector",                   "description": "Vulnerability scanning"},
    {"id": "security_hub",      "name": "Security Hub",                "description": "Security Hub hubs"},
    {"id": "firewall_manager",  "name": "Firewall Manager",            "description": "WAF/Shield policies (global)"},
    {"id": "shield",            "name": "Shield Advanced",             "description": "DDoS protection subscriptions (global)"},
    {"id": "license_manager",   "name": "License Manager",             "description": "License configurations"},
    # ── Management & Observability ───────────────────────────────────────────
    {"id": "cloudwatch_synthetics", "name": "CloudWatch Synthetics",   "description": "Canary monitors"},
    {"id": "cloudtrail",        "name": "CloudTrail",                  "description": "Audit trails"},
    {"id": "config_service",    "name": "AWS Config",                  "description": "Config recorders and delivery channels"},
    {"id": "xray",              "name": "X-Ray",                       "description": "Distributed tracing groups and sampling rules"},
    # ── Developer Tools ──────────────────────────────────────────────────────
    {"id": "codebuild",         "name": "CodeBuild",                   "description": "Build projects"},
    {"id": "codepipeline",      "name": "CodePipeline",                "description": "CI/CD pipelines"},
    {"id": "codeartifact",      "name": "CodeArtifact",                "description": "Artifact repositories"},
    # ── Business Apps ────────────────────────────────────────────────────────
    {"id": "connect",           "name": "Amazon Connect",              "description": "Contact center instances"},
    {"id": "ses",               "name": "SES",                         "description": "Email identities and configuration sets"},
    {"id": "workspaces",        "name": "WorkSpaces",                  "description": "Virtual desktops"},
    {"id": "pinpoint",          "name": "Pinpoint",                    "description": "Customer engagement apps"},
    # ── Media ────────────────────────────────────────────────────────────────
    {"id": "mediaconvert",      "name": "MediaConvert",                "description": "Video transcoding queues"},
    {"id": "medialive",         "name": "MediaLive",                   "description": "Live video channels and inputs"},
    {"id": "ivs",               "name": "IVS",                         "description": "Interactive Video Service channels"},
    # ── Extended Services ──────────────────────────────────────────────────────
    {"id": "acm",               "name": "Certificate Manager (ACM)",   "description": "SSL/TLS certificates"},
    {"id": "amplify",           "name": "Amplify",                     "description": "Web and mobile app hosting"},
    {"id": "cloudformation",    "name": "CloudFormation",              "description": "Infrastructure as Code stacks"},
    {"id": "cognito_idp",       "name": "Cognito User Pools",          "description": "User sign-up, sign-in, and identity"},
    {"id": "cognito_sync",      "name": "Cognito Identity Pools",      "description": "Federated identity pools"},
    {"id": "datasync",          "name": "DataSync",                    "description": "Online data transfer"},
    {"id": "detective",         "name": "Detective",                   "description": "Security investigation graphs"},
    {"id": "directory_service", "name": "Directory Service",           "description": "Managed Microsoft AD directories"},
    {"id": "emr_serverless",    "name": "EMR Serverless",              "description": "Serverless Spark/Hive applications"},
    {"id": "grafana",           "name": "Managed Grafana",             "description": "Managed Grafana workspaces"},
    {"id": "iot_core",          "name": "IoT Core",                    "description": "IoT device registry and management"},
    {"id": "lakeformation",     "name": "Lake Formation",              "description": "Data lake resources"},
    {"id": "mwaa",              "name": "MWAA (Airflow)",              "description": "Managed Workflows for Apache Airflow"},
    {"id": "personalize",       "name": "Personalize",                 "description": "ML-powered recommendations"},
    {"id": "polly",             "name": "Polly",                       "description": "Text-to-speech lexicons"},
    {"id": "storagegateway",    "name": "Storage Gateway",             "description": "Hybrid cloud storage gateways"},
    {"id": "textract",          "name": "Textract",                    "description": "Document text extraction adapters"},
    {"id": "transcribe",        "name": "Transcribe",                  "description": "Speech-to-text transcription jobs"},
    {"id": "translate",         "name": "Translate",                   "description": "Translation terminologies"},
    {"id": "budgets",           "name": "AWS Budgets",                 "description": "Budget plans and alerts (global)"},
]

VALID_SERVICE_IDS = {s["id"] for s in AWS_SERVICES}

AZURE_REGIONS = [
    "eastus", "eastus2", "westus", "westus2", "westus3",
    "centralus", "northcentralus", "southcentralus",
    "northeurope", "westeurope", "uksouth", "ukwest",
    "francecentral", "germanywestcentral", "switzerlandnorth",
    "norwayeast", "swedencentral",
    "southeastasia", "eastasia",
    "japaneast", "japanwest",
    "australiaeast", "australiasoutheast",
    "centralindia", "southindia",
    "brazilsouth", "canadacentral", "canadaeast",
    "uaenorth", "southafricanorth",
]

AZURE_SERVICES = [
    {"id": "virtual_machines",  "name": "Virtual Machines",      "description": "Azure VMs (running, stopped, deallocated)"},
    {"id": "managed_disks",     "name": "Managed Disks",          "description": "Attached and unattached managed disks"},
    {"id": "snapshots",         "name": "Disk Snapshots",         "description": "VM disk snapshots"},
    {"id": "storage_accounts",  "name": "Storage Accounts",       "description": "Blob, file, queue, and table storage"},
    {"id": "sql_databases",     "name": "Azure SQL Databases",    "description": "Azure SQL Server databases"},
    {"id": "cosmosdb",          "name": "Cosmos DB",              "description": "Globally distributed NoSQL accounts"},
    {"id": "redis",             "name": "Azure Cache for Redis",  "description": "In-memory Redis cache instances"},
    {"id": "app_services",      "name": "App Services",           "description": "Web apps and function apps"},
    {"id": "aks",               "name": "AKS Clusters",           "description": "Managed Kubernetes clusters"},
    {"id": "public_ips",        "name": "Public IP Addresses",    "description": "Reserved and associated public IPs"},
    {"id": "app_service_plans",    "name": "App Service Plans",       "description": "App Service hosting plans (SKU, site count)"},
    {"id": "load_balancers",       "name": "Load Balancers",          "description": "Azure Load Balancers (Standard, Basic, Gateway)"},
    {"id": "application_gateways", "name": "Application Gateways",    "description": "Application Gateway and WAF instances"},
    {"id": "nat_gateways",         "name": "NAT Gateways",            "description": "Azure NAT Gateway resources"},
    {"id": "key_vault",            "name": "Key Vaults",              "description": "Azure Key Vault instances"},
    {"id": "container_registry",   "name": "Container Registry",      "description": "Azure Container Registry (ACR) instances"},
    {"id": "service_bus",          "name": "Service Bus",             "description": "Service Bus namespaces"},
    {"id": "event_hubs",           "name": "Event Hubs",              "description": "Event Hub namespaces"},
    {"id": "postgresql",           "name": "Azure Database for PostgreSQL", "description": "PostgreSQL single-server instances"},
    {"id": "mysql",                "name": "Azure Database for MySQL", "description": "MySQL single-server instances"},
]

VALID_AZURE_SERVICE_IDS = {s["id"] for s in AZURE_SERVICES}

GCP_REGIONS = [
    "us-central1", "us-east1", "us-east4", "us-east5",
    "us-west1", "us-west2", "us-west3", "us-west4",
    "northamerica-northeast1", "northamerica-northeast2",
    "southamerica-east1", "southamerica-west1",
    "europe-west1", "europe-west2", "europe-west3",
    "europe-west4", "europe-west6", "europe-west8", "europe-west9",
    "europe-north1", "europe-central2", "europe-southwest1",
    "asia-east1", "asia-east2",
    "asia-northeast1", "asia-northeast2", "asia-northeast3",
    "asia-south1", "asia-south2",
    "asia-southeast1", "asia-southeast2",
    "australia-southeast1", "australia-southeast2",
    "me-west1", "me-central1",
    "africa-south1",
]

GCP_SERVICES = [
    {"id": "compute_instances", "name": "Compute Engine VMs",    "description": "GCE virtual machine instances"},
    {"id": "persistent_disks",  "name": "Persistent Disks",      "description": "Zonal and regional persistent disks"},
    {"id": "static_ips",        "name": "Static IP Addresses",   "description": "Reserved global and regional static IPs"},
    {"id": "snapshots",         "name": "Disk Snapshots",         "description": "Persistent disk snapshots"},
    {"id": "gcs_buckets",       "name": "Cloud Storage Buckets", "description": "GCS object storage buckets"},
    {"id": "cloud_sql",         "name": "Cloud SQL",             "description": "Managed MySQL, PostgreSQL, SQL Server"},
    {"id": "gke_clusters",      "name": "GKE Clusters",          "description": "Managed Kubernetes Engine clusters"},
    {"id": "cloud_functions",   "name": "Cloud Functions",       "description": "Serverless function deployments"},
    {"id": "cloud_run",           "name": "Cloud Run",               "description": "Serverless container services"},
    {"id": "bigquery_datasets",   "name": "BigQuery Datasets",        "description": "BigQuery datasets and stored data"},
    {"id": "cloud_spanner",       "name": "Cloud Spanner",            "description": "Globally distributed relational database instances"},
    {"id": "pubsub_topics",       "name": "Pub/Sub Topics",           "description": "Cloud Pub/Sub message topics"},
    {"id": "dataproc_clusters",   "name": "Dataproc Clusters",        "description": "Managed Hadoop/Spark clusters"},
    {"id": "app_engine",          "name": "App Engine",               "description": "App Engine services and versions"},
    {"id": "memorystore_redis",   "name": "Memorystore (Redis)",       "description": "Managed in-memory Redis instances"},
    {"id": "artifact_registry",   "name": "Artifact Registry",        "description": "Container and artifact repositories"},
    {"id": "cloud_bigtable",      "name": "Cloud Bigtable",           "description": "Wide-column NoSQL database instances"},
    {"id": "vertex_ai_endpoints", "name": "Vertex AI Endpoints",      "description": "Deployed model serving endpoints"},
]

VALID_GCP_SERVICE_IDS = {s["id"] for s in GCP_SERVICES}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def _is_sso_expiry_error(exc: Exception) -> bool:
    """Return True if exc indicates an expired or missing AWS SSO/credential session."""
    try:
        import botocore.exceptions as _bce
        # Check specific botocore SSO exception types (botocore >= 1.29)
        _sso_exc_names = ("TokenRetrievalError", "SSOTokenLoadError", "UnauthorizedSSOTokenError")
        _sso_types = tuple(filter(None, (getattr(_bce, n, None) for n in _sso_exc_names)))
        if _sso_types and isinstance(exc, _sso_types):
            return True
        # ClientError carries a structured error code — more reliable than message scanning
        if isinstance(exc, _bce.ClientError):
            code = exc.response.get("Error", {}).get("Code", "")
            return code in {
                "ExpiredTokenException", "InvalidClientTokenId",
                "AuthFailure", "TokenExpiredException", "UnauthorizedException",
            }
    except Exception:
        pass
    # Narrow text fallback for non-botocore exceptions (e.g. third-party wrappers)
    msg = str(exc).lower()
    return ("expired" in msg or "not authorized" in msg) and ("sso" in msg or "token" in msg)


class AccountRequest(BaseModel):
    account_id: str
    name: str
    email: str = ""
    role_arn: str = ""

    @field_validator("account_id")
    @classmethod
    def validate_account_id(cls, v: str) -> str:
        if not VALID_ACCOUNT_RE.match(v.strip()):
            raise ValueError("account_id must be exactly 12 digits")
        return v.strip()


def _write_accounts_inplace(filepath: str, accounts: list):
    """Write accounts JSON in-place to preserve the file inode (required for Docker bind mounts)."""
    import json as _json
    content = _json.dumps({"accounts": accounts}, indent=2)
    if os.path.exists(filepath):
        with open(filepath, "r+") as f:
            f.seek(0)
            f.write(content)
            f.truncate()
    else:
        with open(filepath, "w") as f:
            f.write(content)


# ─── pre-scan credential validation ─────────────────────────────────────────

def _safe_cloud_error(provider: str, detail: str) -> HTTPException:
    """Return an HTTP 400 with a sanitized message — never leak raw SDK exception text."""
    return HTTPException(status_code=400, detail=detail)


def _validate_subscription_id(sub_id: str) -> str:
    sub_id = sub_id.strip()
    if not AZURE_SUB_RE.match(sub_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid Azure Subscription ID format. Expected a UUID like xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx.",
        )
    return sub_id


def _validate_project_id(proj_id: str) -> str:
    proj_id = proj_id.strip()
    if not GCP_PROJECT_RE.match(proj_id):
        raise HTTPException(
            status_code=400,
            detail="Invalid GCP Project ID format. Must be 6–30 lowercase letters, digits, or hyphens, starting with a letter.",
        )
    return proj_id


_AWS_KEY_ID_RE = re.compile(r'^(AKIA|ASIA|AROA|AIDA|ANPA|ANVA|APKA)[A-Z0-9]{16}$')


class ValidateRequest(BaseModel):
    cloud_provider: str = "aws"
    subscription_id: Optional[str] = None
    azure_tenant_id: Optional[str] = None
    azure_client_id: Optional[str] = None
    azure_client_secret: Optional[str] = None
    project_id: Optional[str] = None
    use_organizations: bool = False
    accounts: Optional[list[str]] = None
    gcp_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    ai_provider: Optional[str] = None
    ai_api_key: Optional[str] = None
    sso_credentials: Optional[list[SSOCredentialItem]] = None

    @field_validator("aws_access_key_id")
    @classmethod
    def validate_aws_key_id(cls, v: Optional[str]) -> Optional[str]:
        if v:
            v = v.strip()
            if v and not _AWS_KEY_ID_RE.match(v):
                raise ValueError(
                    "Invalid AWS Access Key ID. Expected a 20-character key starting with AKIA or ASIA."
                )
        return v





# ─── analysis progress helpers ───────────────────────────────────────────────

async def _push(analysis_id: str, message: str, status: str = "in_progress", data: dict = None):
    await _redis_client.progress_push(analysis_id, message, status, data)


# ─── analysis background task ────────────────────────────────────────────────

async def _run_analysis(analysis_id: str, user_id: int, req: AnalyzeRequest):
    loop = asyncio.get_running_loop()

    def sync_progress(msg: str):
        asyncio.run_coroutine_threadsafe(_push(analysis_id, msg), loop)

    try:
        async with _analysis_semaphore:
            provider = req.cloud_provider

            if provider == "azure":
                if not _AZURE_AVAILABLE:
                    raise RuntimeError(
                        "Azure SDK not installed. Run: pip install azure-identity azure-mgmt-compute "
                        "azure-mgmt-storage azure-mgmt-sql azure-mgmt-network azure-mgmt-web "
                        "azure-mgmt-containerservice azure-mgmt-cosmosdb azure-mgmt-redis"
                    )
                sub_id = (req.subscription_id or "").strip()
                if not sub_id:
                    raise RuntimeError(
                        "Azure Subscription ID is required. Enter it in the Azure Credentials section."
                    )
                _az_tenant = (req.azure_tenant_id or "").strip()
                _az_client = (req.azure_client_id or "").strip()
                _az_secret = (req.azure_client_secret or "").strip()
                _az_cred = _azure_scanner._get_credential(_az_tenant, _az_client, _az_secret)
                # Resolve friendly subscription name for resource labels
                sub_name = sub_id
                try:
                    from azure.mgmt.resource import SubscriptionClient as _SubClient
                    _sub_obj = _SubClient(_az_cred).subscriptions.get(sub_id)
                    sub_name = _sub_obj.display_name or sub_id
                except Exception:
                    pass
                await _push(analysis_id, f"Connecting to Azure subscription {sub_name}...")
                resources = await loop.run_in_executor(
                    None,
                    lambda: _azure_scanner.scan_resources(sub_id, req.regions, req.services, sync_progress, sub_name, _az_cred),
                )

            elif provider == "gcp":
                if not _GCP_AVAILABLE:
                    raise RuntimeError(
                        "GCP SDK not installed. Run: pip install google-auth google-auth-httplib2 google-api-python-client"
                    )
                proj_id = (req.project_id or "").strip()
                if not proj_id:
                    raise RuntimeError(
                        "GCP Project ID is required. Enter it in the GCP Credentials section."
                    )
                # Resolve friendly project name for resource labels
                proj_name = proj_id
                try:
                    from googleapiclient.discovery import build as _gcp_build
                    _proj_obj = _gcp_build("cloudresourcemanager", "v1", credentials=_gcp_scanner._get_credentials())
                    proj_name = _proj_obj.projects().get(projectId=proj_id).execute().get("name", proj_id)
                except Exception:
                    pass
                await _push(analysis_id, f"Connecting to GCP project {proj_name}...")
                _gcp_api_key = (req.gcp_api_key or "").strip()
                resources = await loop.run_in_executor(
                    None,
                    lambda: _gcp_scanner.scan_resources(proj_id, req.regions, req.services, sync_progress, proj_name, _gcp_api_key),
                )

            else:
                # AWS (default)
                await _push(analysis_id, "Resolving AWS credentials...")
                key_id  = (req.aws_access_key_id or "").strip()
                secret  = (req.aws_secret_access_key or "").strip()
                account_ids = req.accounts or []
                use_org = req.use_organizations
                from cloud_organizations import AccountCredentials
                if req.sso_credentials:
                    # Browser-authenticated SSO temporary credentials (per-user, session-scoped)
                    creds_list = [
                        AccountCredentials(
                            account_id=c.account_id,
                            account_name=c.account_name,
                            access_key=c.access_key,
                            secret_key=c.secret_key,
                            session_token=c.session_token or "",
                        )
                        for c in req.sso_credentials
                        if c.access_key
                    ]
                    if not creds_list:
                        raise RuntimeError("No valid SSO credentials. Please re-authenticate via AWS SSO in Settings.")
                    scanned_names = ", ".join(c.account_name for c in creds_list)
                    await _push(
                        analysis_id,
                        f"SSO connected — scanning {len(creds_list)} account(s): {scanned_names} across {len(req.regions)} region(s)...",
                    )
                elif key_id and secret:
                    # Use explicit static credentials — single-account mode
                    import boto3 as _b3
                    _sts = _b3.Session(
                        aws_access_key_id=key_id, aws_secret_access_key=secret
                    ).client("sts", region_name="us-east-1")
                    _identity = _sts.get_caller_identity()
                    _acct_id = _identity.get("Account", "")
                    creds_list = [AccountCredentials(
                        account_id=_acct_id,
                        account_name=_acct_id,
                        access_key=key_id,
                        secret_key=secret,
                    )]
                elif use_org:
                    creds_list = await loop.run_in_executor(
                        None,
                        lambda: resolve_scan_credentials(account_ids, use_org),
                    )
                else:
                    raise RuntimeError(
                        "AWS credentials are required. Enter your Access Key ID and Secret Access Key in the Settings panel."
                    )
                if account_ids:
                    scanned_ids = {c.account_id for c in creds_list}
                    failed_ids = [aid for aid in account_ids if aid not in scanned_ids]
                    if failed_ids:
                        await _push(
                            analysis_id,
                            f"Warning: Could not access {len(failed_ids)} account(s): {', '.join(failed_ids)}. "
                            f"Only the remaining account(s) will be scanned.",
                        )
                scanned_names = ", ".join(c.account_name for c in creds_list)
                await _push(
                    analysis_id,
                    f"Connected — scanning {len(creds_list)} account(s): {scanned_names} across {len(req.regions)} region(s)...",
                )
                resources = await loop.run_in_executor(
                    None,
                    lambda: cloud_scanner.scan_resources(creds_list, req.regions, req.services, sync_progress),
                )

            total = sum(len(v) for v in resources.values())
            await _push(analysis_id, f"Resource scan complete — {total} resources found. Running AI analysis...")

            _ai_provider = (req.ai_provider or "").strip().lower() or None
            _ai_api_key  = (req.ai_api_key or "").strip() or None
            result = await loop.run_in_executor(
                None,
                lambda: ai_analyzer.analyze_resources(
                    resources,
                    cloud_provider=provider,
                    ai_provider=_ai_provider,
                    ai_api_key=_ai_api_key,
                ),
            )

            await _push(analysis_id, "Generating AI summary...")
            ai_summary = None
            try:
                from cloudflare_ai import chat_completion
                issues_preview = json.dumps(result.get("issues", [])[:15])
                summary_prompt = (
                    f"Summarize this cloud cost analysis in 2-3 sentences. "
                    f"Provider: {provider}. "
                    f"Resources scanned: {result.get('total_resources', 0)}. "
                    f"Issues found: {result.get('issues_found', 0)}. "
                    f"Estimated savings: ${result.get('estimated_monthly_savings', 0):.2f}/month. "
                    f"Top issues: {issues_preview}"
                )
                ai_summary = await chat_completion(
                    messages=[{"role": "user", "content": summary_prompt}],
                    context={"page": "/report", "analysis_result": result},
                )
            except Exception as e:
                logger.warning("ai_summary.failed", extra={"error": str(e)})

            # Add raw resources to result for InfraVisualizer
            raw_resources = {}
            for svc, items in resources.items():
                for r in items[:10]:  # Limit per service to avoid huge payloads
                    rid = r.get("id", r.get("name", ""))
                    if rid:
                        raw_resources[rid] = {
                            "type": r.get("type", svc),
                            "name": r.get("name", rid),
                            "region": r.get("region", ""),
                            "config": {k: v for k, v in r.items() if k not in ("Tags", "tags") and isinstance(v, (str, int, float, bool))},
                        }
            result["raw_resources"] = raw_resources

            await _push(analysis_id, "Saving results...")
            await db.update_analysis(analysis_id, result, ai_summary=ai_summary)
            await _push(analysis_id, "Analysis complete!", status="complete", data=result)

    except BaseException as e:
        if isinstance(e, asyncio.CancelledError):
            err_msg = "Analysis was cancelled"
        else:
            raw = str(e)
            # Strip internal file paths (e.g. /app/cloud_scanner.py line 123) before surfacing
            err_msg = re.sub(r'/\S+\.py(?::\d+)?', '', raw).strip() or "Analysis failed — please try again"
        await _push(analysis_id, f"Analysis failed: {err_msg}", status="error")
        await db.fail_analysis(analysis_id, err_msg)
        if isinstance(e, asyncio.CancelledError):
            raise
    finally:
        await _redis_client.scan_release()
        await asyncio.sleep(5)
        await _redis_client.progress_delete(analysis_id)





# ─── cost explorer endpoints ──────────────────────────────────────

class CostExplorerRequest(BaseModel):
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    days: int = 30





# ─── health check ────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    pool = db.pool
    db_status = "in-memory" if pool is None else "error"
    try:
        if pool:
            async with asyncio.timeout(2.0):
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")
                db_status = "connected"
    except Exception as exc:
        logger.error("health.db_check_failed", extra={"error": str(exc)})

    redis_status = "unknown"
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), socket_timeout=2)
        await r.ping()
        redis_status = "connected"
        await r.close()
    except Exception:
        redis_status = "unavailable"

    cf_url = os.getenv("CLOUDFLARE_WORKER_URL", "")
    cf_account = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
    cf_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
    has_cf_direct = bool(cf_account and cf_token)
    has_cloudflare = bool(cf_url) or has_cf_direct
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    has_google = bool(os.getenv("GOOGLE_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip())
    has_openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
    has_groq = bool(os.getenv("GROQ_API_KEY", "").strip())
    has_deepseek = bool(os.getenv("DEEPSEEK_API_KEY", "").strip())
    has_xai = bool(os.getenv("XAI_API_KEY", "").strip())
    has_mistral = bool(os.getenv("MISTRAL_API_KEY", "").strip())
    has_cohere = bool(os.getenv("COHERE_API_KEY", "").strip())
    has_together = bool(os.getenv("TOGETHER_API_KEY", "").strip())
    has_perplexity = bool(os.getenv("PERPLEXITY_API_KEY", "").strip())
    has_azure = bool(os.getenv("AZURE_OPENAI_API_KEY", "").strip() and os.getenv("AZURE_OPENAI_ENDPOINT", "").strip())
    has_bedrock = bool(os.getenv("BEDROCK_REGION", "").strip())
    has_ollama = bool(os.getenv("OLLAMA_BASE_URL", "").strip())
    ai_model = os.getenv("AI_MODEL", "llama-3.2-3b")
    ai_provider = os.getenv("AI_PROVIDER", "auto").strip().lower()

    active_provider = "none"
    provider_priority = [
        ("anthropic", has_anthropic), ("google", has_google), ("openai", has_openai),
        ("groq", has_groq), ("deepseek", has_deepseek), ("xai", has_xai),
        ("mistral", has_mistral), ("cohere", has_cohere), ("together", has_together),
        ("perplexity", has_perplexity), ("azure", has_azure), ("bedrock", has_bedrock),
        ("ollama", has_ollama), ("cloudflare", has_cloudflare),
    ]
    if ai_provider and ai_provider != "auto":
        active_provider = ai_provider
    else:
        for name, available in provider_priority:
            if available:
                active_provider = name
                break

    ai_status = {
        "provider": active_provider,
        "model": ai_model,
        "available": any(v for _, v in provider_priority),
        "providers": {
            "cloudflare": {"available": has_cloudflare, "url": cf_url or "", "direct_api": has_cf_direct, "model": "@cf/meta/llama-3.1-8b-instruct-fp8"},
            "anthropic": {"available": has_anthropic, "model": os.getenv("AI_MODEL", "claude-sonnet-4-6")},
            "google": {"available": has_google, "model": os.getenv("AI_MODEL", "gemini-2.0-flash")},
            "openai": {"available": has_openai, "model": os.getenv("AI_MODEL", "gpt-4o")},
            "groq": {"available": has_groq, "model": "llama-3.3-70b-versatile"},
            "deepseek": {"available": has_deepseek, "model": "deepseek-chat"},
            "xai": {"available": has_xai, "model": "grok-2-1212"},
            "mistral": {"available": has_mistral, "model": "mistral-large-latest"},
            "cohere": {"available": has_cohere, "model": "command-r-plus"},
            "together": {"available": has_together, "model": "Mixtral-8x7B-Instruct-v0.1"},
            "perplexity": {"available": has_perplexity, "model": "sonar-pro"},
            "azure": {"available": has_azure, "model": os.getenv("AI_MODEL", "gpt-4o")},
            "bedrock": {"available": has_bedrock, "model": os.getenv("AI_MODEL", "claude-3-sonnet")},
            "ollama": {"available": has_ollama, "model": os.getenv("AI_MODEL", "llama3.2")},
        },
    }

    if db_status == "error":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": db_status, "redis": redis_status, "ai": ai_status},
        )
    return {"status": "ok", "db": db_status, "redis": redis_status, "ai": ai_status}





def _reconstruct_resources_from_analysis(analysis_result: dict, provider: str) -> dict:
    """Reconstruct resource data from analysis results."""
    resources = {}

    for issue in analysis_result.get("issues", []):
        service = issue.get("service", "").lower()
        if service not in resources:
            resources[service] = []
        resources[service].append({
            "type": issue.get("issue_type", ""),
            "name": issue.get("resource_name", ""),
            "id": issue.get("resource_id", ""),
            "region": issue.get("region", ""),
        })

    return resources


# ─── Infrastructure Visualization endpoints ───────────────────────────────────

class IaCParseRequest(BaseModel):
    content: str = Field(min_length=10, max_length=100000)
    file_type: str = Field(default="terraform", pattern="^(terraform|cloudformation)$")


class ScanProjectRequest(BaseModel):
    directory: str = Field(min_length=1, max_length=500)
    max_depth: int = Field(default=5, ge=1, le=10)


def _sanitize_git_url(url: str) -> str:
    """Strip embedded credentials from a git URL and validate the domain."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https", "git", "ssh"):
        raise ValueError(f"Unsupported git URL scheme: {parsed.scheme}")
    # Strip credentials
    sanitized = parsed._replace(netloc=parsed.hostname or parsed.netloc)
    if parsed.port:
        sanitized = sanitized._replace(netloc=f"{sanitized.hostname}:{parsed.port}")
    return urlunparse(sanitized._replace(params='', query='', fragment=''))


# ─── AWS SSO endpoints ────────────────────────────────────────────────────────

import sso_manager as _sso_manager


class SSOStartRequest(BaseModel):
    start_url: str = Field(min_length=10, max_length=500)
    region: str = "us-east-1"

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, v: str) -> str:
        v = v.strip()
        # Allowlist: only genuine AWS SSO domains — prevents SSRF to internal services
        if not re.match(r'^https://[a-zA-Z0-9][a-zA-Z0-9\-]*\.awsapps\.com/', v, re.IGNORECASE):
            raise ValueError(
                "SSO start URL must be an AWS SSO portal URL "
                "(e.g. https://my-org.awsapps.com/start)"
            )
        return v

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        if not v or len(v) > 50:
            raise ValueError("Invalid region")
        return v.strip()


class SSOCredentialsRequest(BaseModel):
    session_id: str
    selections: list = Field(min_length=1)  # [{account_id, account_name, role_name}]


@app.post("/api/sso/start")
async def sso_start(req: SSOStartRequest, user_info: dict = Depends(_verify_token)):
    """Begin the AWS SSO device authorization flow for a user."""
    await _check_rate_limit(f"sso:start:{user_info['user_id']}", max_attempts=10, window_seconds=300)
    uid = user_info["user_id"]
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(
            None,
            lambda: _sso_manager.start_sso_login(req.start_url, req.region, uid),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not start SSO login: {e}")


@app.get("/api/sso/poll/{session_id}")
async def sso_poll(session_id: str, user_info: dict = Depends(_verify_token)):
    """Poll for SSO authorization status (pending / authorized / expired / error)."""
    await _check_rate_limit(f"sso:poll:{session_id}", max_attempts=60, window_seconds=60)
    uid = user_info["user_id"]
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _sso_manager.poll_sso_token(session_id, uid),
    )
    if result.get("status") == "error":
        msg = result.get("message", "")
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        if "access denied" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
    return result


@app.get("/api/sso/accounts/{session_id}")
async def sso_list_accounts(session_id: str, user_info: dict = Depends(_verify_token)):
    """List all accounts + roles the authenticated SSO user can access."""
    uid = user_info["user_id"]
    loop = asyncio.get_running_loop()
    try:
        accounts = await loop.run_in_executor(
            None,
            lambda: _sso_manager.list_sso_accounts(session_id, uid),
        )
        return {"accounts": accounts}
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/sso/credentials")
async def sso_get_credentials(req: SSOCredentialsRequest, user_info: dict = Depends(_verify_token)):
    """Fetch temporary AWS credentials for the selected accounts + roles."""
    await _check_rate_limit(f"sso:credentials:{user_info['user_id']}", max_attempts=5, window_seconds=60)
    uid = user_info["user_id"]
    loop = asyncio.get_running_loop()
    results = []
    errors = []

    for sel in req.selections:
        account_id   = str(sel.get("account_id", "")).strip()
        role_name    = str(sel.get("role_name", "")).strip()
        account_name = str(sel.get("account_name", account_id))

        if not account_id or not role_name:
            errors.append(f"Invalid selection (missing account_id or role_name): {sel}")
            continue

        try:
            # Use default argument capture to avoid late-binding in lambda
            creds = await loop.run_in_executor(
                None,
                lambda aid=account_id, rn=role_name: _sso_manager.get_role_credentials(
                    req.session_id, aid, rn, uid
                ),
            )
            results.append({
                "account_id": account_id,
                "account_name": account_name,
                "role_name": role_name,
                **creds,
            })
        except Exception as e:
            errors.append(f"{account_id}/{role_name}: {e}")

    if not results and errors:
        raise HTTPException(
            status_code=400,
            detail=f"Could not get credentials: {'; '.join(errors)}",
        )

    # Drop stale sessions opportunistically
    loop.run_in_executor(None, _sso_manager.cleanup_expired_sessions)

    return {"credentials": results, "errors": errors}


# ─── Cost estimation endpoints ─────────────────────────────────────────────────

import iac_parser as _iac_parser
import cost_estimator as _cost_estimator

from cloudflare_ai import estimate_insights


class EstimatePasteRequest(BaseModel):
    content: str = Field(min_length=10, max_length=200000)
    format: str = Field(default="auto", pattern=r'^(auto|terraform|cloudformation|json|yaml)$')
    provider: Optional[str] = Field(default=None, pattern=r'^(aws|azure|gcp|)$')
    region: str = Field(default="us-east-1", max_length=50)


class EstimateGitRequest(BaseModel):
    repo_url: str = Field(min_length=10, max_length=1000)
    branch: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, pattern=r'^(aws|azure|gcp|)$')
    region: str = Field(default="us-east-1", max_length=50)


@app.post("/api/estimate", include_in_schema=_DEBUG)
async def estimate_template(req: EstimatePasteRequest, user_info: dict = Depends(_verify_token)):
    """Estimate cost from pasted IaC template content (Terraform, CloudFormation, JSON, YAML).

    Parses the template, estimates resource costs, and returns a full report
    with cost breakdown, alternatives, and cost-saving suggestions.
    """
    fmt = req.format
    if fmt == "auto":
        fmt = _iac_parser.detect_format(req.content)

    resources = _iac_parser.parse_content(req.content, fmt)
    if not resources:
        raise HTTPException(
            status_code=400,
            detail="Could not parse any resources from the provided content. "
                   "Check that your template is valid Terraform or CloudFormation.",
        )

    provider = req.provider or resources[0].get("provider", "aws")
    report = _cost_estimator.estimate_resources(resources, default_provider=provider)

    return {
        "format": fmt,
        "provider": provider,
        "resources_found": len(resources),
        "report": report,
    }


@app.post("/api/estimate/upload", include_in_schema=_DEBUG)
async def estimate_upload_file(
    request: Request,
    user_info: dict = Depends(_verify_token),
):
    """Estimate cost from uploaded IaC template files.

    Accepts multipart file uploads:
      - Single ZIP file containing IaC templates (.tf, .json, .yaml, .yml, .template)
      - Multiple individual template files
    """
    from fastapi import UploadFile, File as _File

    await _check_rate_limit(f"estimate:upload:{user_info['user_id']}", max_attempts=10, window_seconds=300)

    form = await request.form()
    files: list[UploadFile] = []
    for field_name in form:
        field_value = form[field_name]
        if isinstance(field_value, UploadFile):
            files.append(field_value)

    if not files:
        raise HTTPException(
            status_code=400,
            detail="No files provided. Upload a ZIP file or individual template files.",
        )

    all_resources: list[dict] = []
    upload_dir = tempfile.mkdtemp(prefix="cost_estimate_upload_")

    try:
        for upload_file in files:
            if not upload_file.filename:
                continue
            content = await upload_file.read()
            filename_lower = upload_file.filename.lower()

            if filename_lower.endswith(".zip"):
                resources = _iac_parser.parse_zip(content)
                all_resources.extend(resources)
            else:
                ext = os.path.splitext(filename_lower)[1]
                file_path = os.path.join(upload_dir, upload_file.filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(content)

        # Parse any individual files written to upload_dir
        if not all_resources:
            all_resources = _iac_parser.parse_directory(upload_dir)

        if not all_resources:
            raise HTTPException(
                status_code=400,
                detail="Could not parse any resources from the uploaded file(s). "
                       "Supported formats: Terraform (.tf), CloudFormation (.json, .yaml, .yml, .template), "
                       "or ZIP archives containing these files.",
            )

        provider = all_resources[0].get("provider", "aws")
        report = _cost_estimator.estimate_resources(all_resources, default_provider=provider)

        return {
            "format": "upload",
            "provider": provider,
            "resources_found": len(all_resources),
            "report": report,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process uploaded file(s): {str(e)}",
        )
    finally:
        import shutil
        try:
            shutil.rmtree(upload_dir, ignore_errors=True)
        except Exception:
            pass


@app.post("/api/estimate/git", include_in_schema=_DEBUG)
async def estimate_git_repo(req: EstimateGitRequest, user_info: dict = Depends(_verify_token)):
    """Estimate cost from a Git repository containing IaC templates.

    Clones the repo (shallow clone), parses all supported template files,
    and returns a combined cost estimate.
    """
    await _check_rate_limit(f"estimate:git:{user_info['user_id']}", max_attempts=5, window_seconds=300)

    if not _iac_parser._GIT_AVAILABLE:
        raise HTTPException(
            status_code=501,
            detail="Git repository parsing is not available. "
                   "GitPython or the git CLI is not installed in the backend container. "
                   "Contact the administrator to install GitPython>=3.1.0 and the git CLI.",
        )

    try:
        loop = asyncio.get_running_loop()
        resources = await loop.run_in_executor(
            None,
            lambda: _iac_parser.parse_git_repo(req.repo_url, req.branch),
        )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not process Git repository: {str(e)}",
        )

    if not resources:
        raise HTTPException(
            status_code=400,
            detail="No template files found in the repository. "
                   "The repo must contain Terraform (.tf) or CloudFormation (.json/.yaml) templates. "
                   "Note: For complex Terraform modules, paste the output of `terraform plan -json` directly.",
        )

    provider = req.provider or resources[0].get("provider", "aws")
    report = _cost_estimator.estimate_resources(resources, default_provider=provider)

    return {
        "repo_url": req.repo_url,
        "provider": provider,
        "resources_found": len(resources),
        "templates_found": len(set(r.get("source", "") for r in resources)),
        "report": report,
    }


@app.get("/api/estimate/formats", include_in_schema=_DEBUG)
async def estimate_supported_formats(_: dict = Depends(_verify_token)):
    """List supported IaC formats for cost estimation."""
    return {
        "formats": [
            {"id": "terraform", "name": "Terraform HCL", "extensions": [".tf"], "description": "Hashicorp Terraform (.tf files)"},
            {"id": "cloudformation", "name": "CloudFormation", "extensions": [".json", ".yaml", ".yml", ".template"], "description": "AWS CloudFormation templates"},
            {"id": "json", "name": "Terraform JSON / any JSON", "extensions": [".json", ".tf.json"], "description": "Terraform JSON plan output"},
        ],
        "estimation_note": "Prices are approximate and based on on-demand US East pricing. "
                           "Actual costs may vary by region, discounts, and usage patterns.",
    }


class EstimateInsightsRequest(BaseModel):
    resources_found: int = 0
    total_cost: float = 0.0
    service_breakdown: dict = Field(default_factory=dict)


@app.post("/api/estimate/insights", include_in_schema=_DEBUG)
async def estimate_insights_endpoint(req: EstimateInsightsRequest, user_info: dict = Depends(_verify_token)):
    insights = await estimate_insights(req.resources_found, req.total_cost, req.service_breakdown)
    return {"insights": insights or "AI insights unavailable"}


# ─── OAuth routes ────────────────────────────────────────────────────────────

@app.get("/api/auth/google")
async def google_login(request: Request):
    """Redirect to Google OAuth."""
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=501, detail="Google OAuth not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.")
    redirect_uri = f"{request.base_url}api/auth/google/callback"
    params = f"client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&scope=openid%20email%20profile&access_type=offline"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@app.get("/api/auth/google/callback")
async def google_callback(code: str, request: Request):
    """Handle Google OAuth callback."""
    import httpx as _httpx
    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    redirect_uri = f"{request.base_url}api/auth/google/callback"

    async with _httpx.AsyncClient() as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        user_resp = await client.get("https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"})
        user_data = user_resp.json()

    email = user_data.get("email", "")
    name = user_data.get("name", email.split("@")[0])

    if not email:
        raise HTTPException(status_code=400, detail="Could not get email from Google")

    user = await db.get_user_by_email(email)
    if not user:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(os.urandom(32).hex().encode(), _bcrypt.gensalt()).decode()
        user = await db.create_user(email, pw_hash)

    token = _create_token(user["id"], user["email"])
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url="/")
    resp.set_cookie("token", token, httponly=True, samesite="strict", secure=_COOKIE_SECURE, max_age=JWT_EXPIRY_HOURS * 3600)
    return resp


@app.get("/api/auth/linkedin")
async def linkedin_login(request: Request):
    """Redirect to LinkedIn OAuth."""
    client_id = os.getenv("LINKEDIN_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=501, detail="LinkedIn OAuth not configured. Set LINKEDIN_OAUTH_CLIENT_ID and LINKEDIN_OAUTH_CLIENT_SECRET.")
    redirect_uri = f"{request.base_url}api/auth/linkedin/callback"
    params = f"response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&scope=openid%20email%20profile"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"https://www.linkedin.com/oauth/v2/authorization?{params}")


@app.get("/api/auth/linkedin/callback")
async def linkedin_callback(code: str, request: Request):
    """Handle LinkedIn OAuth callback."""
    import httpx as _httpx
    client_id = os.getenv("LINKEDIN_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("LINKEDIN_OAUTH_CLIENT_SECRET", "")
    redirect_uri = f"{request.base_url}api/auth/linkedin/callback"

    async with _httpx.AsyncClient() as client:
        token_resp = await client.post("https://www.linkedin.com/oauth/v2/accessToken", data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri, "grant_type": "authorization_code",
        })
        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        user_resp = await client.get("https://api.linkedin.com/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"})
        user_data = user_resp.json()

    email = user_data.get("email", "")
    name = user_data.get("name", email.split("@")[0] if email else "user")

    if not email:
        raise HTTPException(status_code=400, detail="Could not get email from LinkedIn")

    user = await db.get_user_by_email(email)
    if not user:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(os.urandom(32).hex().encode(), _bcrypt.gensalt()).decode()
        user = await db.create_user(email, pw_hash)

    token = _create_token(user["id"], user["email"])
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url="/")
    resp.set_cookie("token", token, httponly=True, samesite="strict", secure=_COOKIE_SECURE, max_age=JWT_EXPIRY_HOURS * 3600)
    return resp


@app.get("/api/auth/github")
async def github_login(request: Request):
    """Redirect to GitHub OAuth."""
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise HTTPException(status_code=501, detail="GitHub OAuth not configured. Set GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET.")
    redirect_uri = f"{request.base_url}api/auth/github/callback"
    from fastapi.responses import RedirectResponse
    return RedirectResponse(f"https://github.com/login/oauth/authorize?client_id={client_id}&redirect_uri={redirect_uri}&scope=user:email")


@app.get("/api/auth/github/callback")
async def github_callback(code: str, request: Request):
    """Handle GitHub OAuth callback."""
    import httpx as _httpx
    client_id = os.getenv("GITHUB_OAUTH_CLIENT_ID", "")
    client_secret = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "")
    redirect_uri = f"{request.base_url}api/auth/github/callback"

    async with _httpx.AsyncClient() as client:
        token_resp = await client.post("https://github.com/login/oauth/access_token", data={
            "code": code, "client_id": client_id, "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }, headers={"Accept": "application/json"})
        token_data = token_resp.json()
        access_token = token_data.get("access_token")

        user_resp = await client.get("https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"})
        user_data = user_resp.json()

        email_resp = await client.get("https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}"})
        emails = email_resp.json()

    email = user_data.get("email", "")
    if not email and isinstance(emails, list):
        for e in emails:
            if e.get("primary") and e.get("verified"):
                email = e.get("email", "")
                break
        if not email and emails:
            email = emails[0].get("email", "")

    if not email:
        raise HTTPException(status_code=400, detail="Could not get email from GitHub")

    user = await db.get_user_by_email(email)
    if not user:
        import bcrypt as _bcrypt
        pw_hash = _bcrypt.hashpw(os.urandom(32).hex().encode(), _bcrypt.gensalt()).decode()
        user = await db.create_user(email, pw_hash)

    token = _create_token(user["id"], user["email"])
    from fastapi.responses import RedirectResponse
    resp = RedirectResponse(url="/")
    resp.set_cookie("token", token, httponly=True, samesite="strict", secure=_COOKIE_SECURE, max_age=JWT_EXPIRY_HOURS * 3600)
    return resp


# ─── router includes ─────────────────────────────────────────────────────────

from routers.auth import router as _auth_router
from routers.scan import router as _scan_router
from routers.cost import router as _cost_router
from routers.infra import router as _infra_router
from routers.config import router as _config_router
from routers.export import router as _export_router
from routers.free_tier import router as _free_tier_router
from routers.agent import router as _agent_router
from routers.teams import router as _teams_router
from routers.alerts import router as _alerts_router
from routers.rightsizing import router as _rightsizing_router

app.include_router(_auth_router, prefix="")
app.include_router(_scan_router, prefix="")
app.include_router(_cost_router, prefix="")
app.include_router(_infra_router, prefix="")
app.include_router(_config_router, prefix="")
app.include_router(_export_router, prefix="")
app.include_router(_free_tier_router, prefix="")
app.include_router(_agent_router, prefix="")
app.include_router(_teams_router, prefix="")
app.include_router(_alerts_router)
app.include_router(_rightsizing_router, prefix="")
