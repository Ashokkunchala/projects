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
    # Run an immediate purge on startup, then every 12 hours
    asyncio.create_task(_history_purge_loop())
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


# ─── auth endpoints ───────────────────────────────────────────────────────────

@app.post("/api/auth/signup", status_code=201)
async def signup(req: AuthRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    await _check_rate_limit(f"signup:ip:{ip}", max_attempts=10, window_seconds=300)
    await _check_rate_limit(f"signup:email:{req.email}", max_attempts=5, window_seconds=300)

    existing = await db.get_user_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="This email is already signed up. Please try with a new email ID or reach out to the admin.")

    pw_hash = bcrypt.hashpw(req.password.encode(), bcrypt.gensalt()).decode()
    user = await db.create_user(req.email, pw_hash)
    if not user:
        raise HTTPException(status_code=500, detail="Could not create user")

    token = _create_token(user["id"], user["email"])
    response.set_cookie(
        "token", token,
        httponly=True, samesite="strict", secure=_COOKIE_SECURE,
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    return {"user": {"id": user["id"], "email": user["email"]}}


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    # Rate limit by IP first (catches credential stuffing), then by email
    await _check_rate_limit(f"login:ip:{ip}", max_attempts=20, window_seconds=60)
    await _check_rate_limit(f"login:email:{req.email}", max_attempts=10, window_seconds=60)

    user = await db.get_user_by_email(req.email)

    # Always run bcrypt even when user is absent — prevents timing-based enumeration
    stored_hash = user["password_hash"].encode() if user else _DUMMY_HASH.encode()
    password_ok = bcrypt.checkpw(req.password.encode(), stored_hash)

    if not user:
        raise HTTPException(status_code=404, detail="No account found for this email address.")
    if not password_ok:
        raise HTTPException(status_code=401, detail="Incorrect password.")

    token = _create_token(user["id"], user["email"])
    response.set_cookie(
        "token", token,
        httponly=True, samesite="strict", secure=_COOKIE_SECURE,
        max_age=JWT_EXPIRY_HOURS * 3600,
    )
    return {"user": {"id": user["id"], "email": user["email"]}}


@app.post("/api/auth/logout")
async def logout(response: Response, user_info: dict = Depends(_verify_token)):
    jti = user_info.get("jti")
    if jti:
        from datetime import datetime, timezone
        exp = user_info.get("exp")
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc) if exp else None
        await db.revoke_token(jti, expires_at)
    response.delete_cookie("token", samesite="strict")
    return {"status": "logged out"}


@app.get("/api/auth/me")
async def get_me(user_info: dict = Depends(_verify_token)):
    user = await db.get_user_by_id(user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "email": user["email"]}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


@app.post("/api/auth/change-password")
async def change_password(req: ChangePasswordRequest, user_info: dict = Depends(_verify_token)):
    await _check_rate_limit(f"change-password:{user_info['user_id']}", max_attempts=5, window_seconds=300)

    user = await db.get_user_by_id(user_info["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not bcrypt.checkpw(req.current_password.encode(), user["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="Current password is incorrect")

    new_hash = bcrypt.hashpw(req.new_password.encode(), bcrypt.gensalt()).decode()
    await db.update_user_password(user_info["user_id"], new_hash)
    return {"message": "Password updated successfully"}


# ─── config endpoints ────────────────────────────────────────────────────────

@app.get("/api/regions")
async def get_regions(provider: str = "aws", _: dict = Depends(_verify_token)):
    if provider == "azure":
        return {"regions": AZURE_REGIONS}
    if provider == "gcp":
        return {"regions": GCP_REGIONS}
    return {"regions": AWS_REGIONS}


@app.get("/api/services")
async def get_services(provider: str = "aws", _: dict = Depends(_verify_token)):
    if provider == "azure":
        return {"services": AZURE_SERVICES}
    if provider == "gcp":
        return {"services": GCP_SERVICES}
    return {"services": AWS_SERVICES}


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


@app.get("/api/config/accounts")
async def get_org_accounts(_: dict = Depends(_verify_token)):
    """Return all accounts from ~/.aws/config SSO profiles, merged with any custom entries in cloud_accounts.json."""
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


@app.post("/api/config/accounts")
async def add_account(req: AccountRequest, _: dict = Depends(_verify_token)):
    """Add a custom account entry. SSO accounts are auto-detected and don't need to be added here."""
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


@app.delete("/api/config/accounts/{account_id}")
async def remove_account(account_id: str, _: dict = Depends(_verify_token)):
    """Remove a custom account from cloud_accounts.json."""
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


@app.post("/api/validate")
async def validate_credentials(req: ValidateRequest, user_info: dict = Depends(_verify_token)):
    """
    Lightweight pre-flight check that verifies credentials/connectivity for the
    chosen cloud provider BEFORE starting a full scan.  Returns 200 on success or
    400 with a human-readable detail string on failure.
    """
    await _check_rate_limit(f"validate:{user_info['user_id']}", max_attempts=10, window_seconds=60)
    provider = req.cloud_provider.lower()

    # ── AWS ───────────────────────────────────────────────────────────────────
    if provider == "aws":
        import boto3 as _b3
        import botocore.exceptions

        # SSO pre-authenticated credentials — validate with a quick STS call
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
        secret  = (req.aws_secret_access_key or "").strip()
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
                # Organizations mode — uses server-side SSO profiles
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

        # If Organizations mode, verify the SSO profiles for selected accounts
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

    # ── Azure ─────────────────────────────────────────────────────────────────
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

    # ── GCP ───────────────────────────────────────────────────────────────────
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
                # Raw API key (not JSON) — build with developerKey
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

            await _push(analysis_id, "Saving results...")
            await db.update_analysis(analysis_id, result)
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


# ─── analyze endpoint ────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, user_info: dict = Depends(_verify_token)):
    provider = req.cloud_provider

    # Pick the correct region and service sets for validation
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

    # Per-user concurrent analysis cap — prevents DoS flooding the queue
    _running = await db.get_running_analyses_for_user(user_id)
    _running_ids = {a["id"] for a in (_running or [])}
    if len(_running_ids) >= _MAX_ANALYSES_PER_USER:
        raise HTTPException(
            status_code=429,
            detail=f"You already have {_MAX_ANALYSES_PER_USER} analyses running. Wait for one to finish.",
        )

    # Validate cloud-specific ID formats before touching any SDK
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


# ─── WebSocket progress ──────────────────────────────────────────────────────

@app.websocket("/ws/progress/{analysis_id}")
async def ws_progress(websocket: WebSocket, analysis_id: str):
    # Read token from httpOnly cookie sent automatically by the browser
    token = websocket.cookies.get("token", "")
    user_info = _verify_token_str(token)
    if not user_info:
        await websocket.close(code=4001)
        return
    await websocket.accept()

    # Ownership check FIRST — always verify before sending any data
    # get_analysis_by_id checks user_id so cross-user access returns None
    saved = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    progress_msgs = await _redis_client.progress_get_all(analysis_id)
    in_flight = len(progress_msgs) > 0 and progress_msgs[-1].get("status") not in ("complete", "error")

    if not in_flight and not saved:
        await websocket.send_json({"message": "Analysis not found", "status": "error"})
        return

    if in_flight and saved is None:
        # Running but not owned by this user — deny immediately, no data leaked
        await websocket.send_json({"message": "Access denied", "status": "error"})
        return

    # Analysis already finished — replay final result from DB
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
            if keepalive_ticks >= 100:  # every 10 seconds
                keepalive_ticks = 0
                await websocket.send_json({"message": "", "status": "keepalive"})

            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("websocket.error", extra={"analysis_id": analysis_id, "error": str(exc)})


# ─── history endpoints ───────────────────────────────────────────────────────

@app.get("/api/history")
async def get_history(
    user_info: dict = Depends(_verify_token),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=limit, offset=offset)
    return {"analyses": analyses}


@app.get("/api/history/{analysis_id}")
async def get_analysis(analysis_id: str, user_info: dict = Depends(_verify_token)):
    analysis = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@app.delete("/api/history/{analysis_id}", status_code=200)
async def delete_analysis(analysis_id: str, user_info: dict = Depends(_verify_token)):
    deleted = await db.delete_analysis(analysis_id, user_info["user_id"])
    if not deleted:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return {"status": "deleted"}


# ─── cost explorer endpoints ──────────────────────────────────────

class CostExplorerRequest(BaseModel):
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    days: int = 30


@app.post("/api/cost/explorer", include_in_schema=_DEBUG)
async def cost_explorer(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Fetch real AWS cost data from Cost Explorer API for the last N days."""
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_data(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
            days=req.days,
        ),
    )
    return data


@app.post("/api/cost/forecast", include_in_schema=_DEBUG)
async def cost_forecast(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Get 90-day AWS cost forecast."""
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_forecast(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return data


@app.get("/api/cost/awareness", include_in_schema=_DEBUG)
async def cost_awareness(
    category: Optional[str] = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    _: dict = Depends(_verify_token),
):
    """Get AWS cost policy and feature update awareness items."""
    import cost_awareness as _ca
    return _ca.get_awareness_items(category=category, limit=limit)


@app.post("/api/cost/variation", include_in_schema=_DEBUG)
async def cost_variation(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Get cost variation across 1, 3, 6, and 9 month periods with per-service trends."""
    import cost_explorer as _ce
    data = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_cost_variation(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return data


@app.post("/api/cost/rightsizing", include_in_schema=_DEBUG)
async def cost_rightsizing(req: CostExplorerRequest, user_info: dict = Depends(_verify_token)):
    """Get EC2 rightsizing recommendations from Cost Explorer."""
    import cost_explorer as _ce
    recs = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: _ce.get_rightsizing_recommendations(
            access_key=req.aws_access_key_id or "",
            secret_key=req.aws_secret_access_key or "",
            session_token=req.aws_session_token or "",
        ),
    )
    return {"recommendations": recs}


# ─── export endpoints ──────────────────────────────────────────────

@app.get("/api/export/{analysis_id}/csv")
async def export_analysis_csv(analysis_id: str, user_info: dict = Depends(_verify_token)):
    """Export analysis report as CSV file."""
    analysis = await db.get_analysis_by_id(analysis_id, user_info["user_id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")

    csv_content = _export_utils.export_analysis_csv(analysis)
    filename = f"cost-report-{analysis_id[:8]}.csv"

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/history/csv")
async def export_history_csv(user_info: dict = Depends(_verify_token)):
    """Export all analysis history as CSV."""
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=500)
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["ID", "Cloud", "Regions", "Services", "Resources", "Issues",
                      "Savings", "Status", "Date"])
    for a in analyses:
        writer.writerow([
            a.get("id", ""),
            a.get("cloud_provider", ""),
            ", ".join(a.get("regions", [])),
            ", ".join(a.get("services", [])),
            a.get("resources_scanned", 0),
            a.get("issues_found", 0),
            a.get("estimated_savings", ""),
            a.get("status", ""),
            a.get("created_at", ""),
        ])

    return StreamingResponse(
        io.StringIO(output.getvalue()),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="cost-detective-history.csv"'},
    )


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

    if db_status == "error":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": db_status, "redis": redis_status},
        )
    return {"status": "ok", "db": db_status, "redis": redis_status}


# ─── Free Tier endpoints ─────────────────────────────────────────────────────

@app.get("/api/free-tier")
async def get_free_tier(provider: str = Query("all", pattern="^(all|aws|azure|gcp)$")):
    """Get free tier information for cloud providers."""
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    return _free_tier.get_free_tier(provider)


@app.get("/api/free-tier/summary")
async def get_free_tier_summary(provider: str = Query("all", pattern="^(all|aws|azure|gcp)$")):
    """Get a flat summary of all free tier services."""
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    return {"services": _free_tier.get_free_tier_summary(provider)}


@app.get("/api/free-tier/check")
async def check_free_tier_eligibility(
    provider: str = Query("aws", pattern="^(aws|azure|gcp)$"),
    resources: str = Query("[]", description="JSON array of resource types"),
):
    """Check free tier eligibility for scanned resources."""
    if not _FREE_TIER_AVAILABLE:
        return {"error": "Free tier module not available"}
    try:
        resource_list = _json.loads(resources)
        return _free_tier.check_free_tier_eligibility(provider, resource_list)
    except _json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid resources JSON")


@app.get("/api/free-tier/usage/{provider}")
async def get_free_tier_usage(provider: str, user_info: dict = Depends(_verify_token)):
    """Get real-time free tier usage based on last scan results."""
    try:
        import free_tier_usage as _ft_usage
    except ImportError:
        return {"error": "Free tier usage module not available"}

    # Get the user's most recent scan
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=1)
    if not analyses:
        return {"error": "No scan results found. Run a scan first."}

    latest = analyses[0]
    result = latest.get("analysis_result") or latest.get("resources_scanned", 0)

    # Try to get resources from the analysis result
    resources = {}
    if isinstance(result, dict):
        # Reconstruct resources from issues if available
        resources = _reconstruct_resources_from_analysis(result, provider)

    return _ft_usage.get_free_tier_usage(provider, resources)


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


@app.post("/api/infra/parse")
async def parse_infrastructure(req: IaCParseRequest, user_info: dict = Depends(_verify_token)):
    """Parse Terraform or CloudFormation and return infrastructure diagram."""
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    result = _infra_viz.analyze_iac(req.content, req.file_type)
    return result


class ScanProjectRequest(BaseModel):
    directory: str = Field(min_length=1, max_length=500)
    max_depth: int = Field(default=5, ge=1, le=10)


@app.post("/api/infra/scan-project")
async def scan_project_directory(req: ScanProjectRequest, user_info: dict = Depends(_verify_token)):
    """Scan a local project directory for Terraform/CloudFormation files."""
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    import os
    directory = os.path.expanduser(req.directory)

    if not os.path.exists(directory):
        return {"error": f"Directory not found: {directory}"}
    if not os.path.isdir(directory):
        return {"error": f"Not a directory: {directory}"}

    result = _infra_viz.scan_project_directory(directory, req.max_depth)
    return result


@app.get("/api/infra/scan-git")
async def scan_git_repo(
    repo_url: str = Query(..., description="Git repository URL"),
    user_info: dict = Depends(_verify_token),
):
    """Clone and scan a Git repository for IaC files."""
    try:
        import infra_visualizer as _infra_viz
        import git
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    import tempfile
    import os

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "repo")
            git.Repo.clone_from(repo_url, repo_path, depth=1)
            result = _infra_viz.scan_project_directory(repo_path)
            result['repo_url'] = repo_url
            return result
    except git.exc.GitCommandError as e:
        return {"error": f"Failed to clone repository: {str(e)}"}
    except Exception as e:
        return {"error": f"Error scanning repository: {str(e)}"}


@app.post("/api/infra/validate")
async def validate_infrastructure(req: IaCParseRequest, user_info: dict = Depends(_verify_token)):
    """Validate infrastructure configuration and return recommendations."""
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    result = _infra_viz.analyze_iac(req.content, req.file_type)

    # Add validation recommendations
    recommendations = []
    for resource in result.get("raw_resources", {}).values():
        rtype = resource.get("type", "")

        # Check for security issues
        if rtype in ["aws_security_group", "azurerm_network_security_group"]:
            config = resource.get("config", {})
            if any("0.0.0.0/0" in str(v) for v in config.values()):
                recommendations.append({
                    "type": "security",
                    "severity": "high",
                    "resource": resource.get("name", ""),
                    "message": "Security group allows traffic from 0.0.0.0/0. Restrict to specific IPs.",
                })

        # Check for cost optimization
        if rtype == "aws_instance":
            config = resource.get("config", {})
            itype = config.get("instance_type", "")
            if itype.startswith("t2."):
                recommendations.append({
                    "type": "cost",
                    "severity": "low",
                    "resource": resource.get("name", ""),
                    "message": f"Consider upgrading from {itype} to t3 for better price-performance.",
                })

        # Check for free tier eligibility
        if resource.get("free_tier_eligible"):
            recommendations.append({
                "type": "free_tier",
                "severity": "info",
                "resource": resource.get("name", ""),
                "message": f"Resource is free tier eligible.",
            })

    result["recommendations"] = recommendations
    return result


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
