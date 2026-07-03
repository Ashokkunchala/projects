# AI Cloud Cost Detective — Complete Setup Guide

> **Everything you need to run this project from absolute scratch — no prior configuration assumed.**

---

## Table of Contents

1. [What This Tool Does](#1-what-this-tool-does)
2. [System Architecture](#2-system-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Local Setup (Docker)](#4-local-setup-docker)
5. [Local Setup (Manual / Development)](#5-local-setup-manual--development)
6. [Cloudflare AI Agent Setup](#6-cloudflare-ai-agent-setup)
7. [Cloud Deployment (AWS via Terraform)](#7-cloud-deployment-aws-via-terraform)
8. [Configuration Reference](#8-configuration-reference)
9. [Running the Application](#9-running-the-application)
10. [Testing](#10-testing)
11. [Usage Walkthrough](#11-usage-walkthrough)
12. [API Reference](#12-api-reference)
13. [Troubleshooting](#13-troubleshooting)
14. [Security Considerations](#14-security-considerations)
15. [Contributing & Pushing to Repo](#15-contributing--pushing-to-repo)

---

## 1. What This Tool Does

**AI Cloud Cost Detective** is a multi-cloud cost optimization platform that scans your AWS, Azure, or GCP infrastructure, detects waste, and generates AI-powered recommendations to reduce your cloud bill.

### Key Capabilities

| Capability | Details |
|---|---|
| Multi-cloud scanning | AWS (87+ services), Azure (20+), GCP (18+) |
| AI-powered analysis | 14+ AI providers (Claude, GPT-4o, Gemini, Llama, etc.) |
| Rule-based engine | Free built-in analysis when no AI key is set |
| Real-time progress | WebSocket-based live scan updates |
| Cost estimation | Monthly cost calculations with breakdowns |
| Fix commands | Ready-to-run CLI commands for each recommendation |
| Historical tracking | Monitor savings over time |
| Infrastructure visualizer | Interactive architecture diagrams (Terraform, CloudFormation) |
| Free tier monitoring | Track usage against free tier limits |

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        USER BROWSER                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │              React Frontend (Vite + Tailwind)              │ │
│  │  Dashboard │ Scanner │ Reports │ Infra Viz │ Free Tier     │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Python)                       │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │  Auth   │ │Scanning │ │Analysis │ │  Infra  │ │Free Tier │ │
│  │ Service │ │ Service │ │ Service │ │  Viz    │ │ Tracker  │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘ │
│                                                                  │
│  Scanner Layer:                                                  │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌──────────┐ │
│  │AWS Scan │ │Azure Scan│ │GCP Scan│ │AI Engine│ │Rule Engine│ │
│  │(boto3)  │ │(azure-mg)│ │(google)│ │(14 prov)│ │(built-in) │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘ │
└──────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   PostgreSQL    │ │     Redis       │ │ Cloudflare AI   │
│  (Data Store)   │ │   (Caching)     │ │ (Edge Analysis) │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, TypeScript |
| Backend | Python 3.11, FastAPI, Uvicorn |
| Database | PostgreSQL 16 (Alpine) |
| Caching | Redis (with in-memory fallback) |
| Auth | JWT (httpOnly cookies), bcrypt |
| AI | 14+ providers (Anthropic, OpenAI, Google, Groq, etc.) |
| Cloud SDKs | boto3 (AWS), azure-identity/mgmt (Azure), google-auth (GCP) |
| Cloudflare Agent | Cloudflare Workers, D1, KV, R2, AI (Llama 3.1 8B) |
| Containers | Docker, Docker Compose |
| IaC | Terraform (AWS), Wrangler (Cloudflare) |

---

## 3. Prerequisites

### For Docker Setup (Recommended)

| Tool | Minimum Version | Install Command | Verify |
|---|---|---|---|
| Docker | 24+ | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) | `docker --version` |
| Docker Compose | 2.20+ | Included with Docker Desktop | `docker compose version` |
| Git | any | [git-scm.com](https://git-scm.com/) | `git --version` |

### For Local Development

| Tool | Minimum Version | Install Command | Verify |
|---|---|---|---|
| Python | 3.11+ | `sudo apt install python3 python3-venv` | `python3 --version` |
| Node.js | 20+ | `sudo apt install nodejs npm` or use nvm | `node --version` |
| PostgreSQL | 16+ | `sudo apt install postgresql` | `psql --version` |
| Git | any | `sudo apt install git` | `git --version` |

### For Cloudflare AI Agent

| Tool | Minimum Version | Install Command | Verify |
|---|---|---|---|
| Node.js | 20+ | (same as above) | `node --version` |
| Wrangler | 3+ | `npm install -g wrangler` | `wrangler --version` |

### For AWS Cloud Deployment

| Tool | Minimum Version | Install Command | Verify |
|---|---|---|---|
| AWS CLI | 2+ | `sudo apt install awscli` | `aws --version` |
| Terraform | 1.0+ | [developer.hashicorp.com/terraform/install](https://developer.hashicorp.com/terraform/install) | `terraform --version` |

---

## 4. Local Setup (Docker)

This is the fastest and recommended way to run the project.

### Step 1: Clone the Repository

```bash
git clone https://github.com/Ashokkunchala/projects.git
cd projects
```

### Step 2: Generate a Secure Database Password

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env
```

This creates a `.env` file at the project root with a random password. Example output in `.env`:

```
POSTGRES_PASSWORD=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4
```

> **Note:** The `JWT_SECRET` is auto-generated on first run and persisted in a Docker volume — no manual setup needed.

### Step 3: Build and Start Everything

```bash
docker compose up --build -d
```

This builds and starts 4 containers:
- `cost-detective-backend` — FastAPI server (port 8000)
- `cost-detective-frontend` — React app served via Nginx (port 3000)
- `cost-detective-db` — PostgreSQL (port 5432, localhost only)
- `cost-detective-tunnel` — Cloudflare Tunnel (optional, for public access)

### Step 4: Verify It's Running

```bash
# Check all containers are healthy
docker compose ps

# Check backend health
curl http://localhost:8000/health

# Expected output:
# {"status":"ok","db":"connected","redis":"unavailable"}
```

### Step 5: Access the Application

| URL | Description |
|---|---|
| `http://localhost:3000` | Frontend (create account, run scans) |
| `http://localhost:8000` | Backend API |
| `http://localhost:8000/docs` | Swagger API docs (requires `DEBUG=true`) |

### Common Docker Commands

```bash
# View logs (all services)
docker compose logs -f

# View logs (backend only)
docker compose logs -f backend

# Restart after code changes
docker compose build backend && docker compose up -d backend

# Full rebuild (no cache)
docker compose build --no-cache && docker compose up -d

# Stop everything
docker compose down

# Stop and remove all data (fresh start)
docker compose down -v

# Reset a user password
docker compose exec backend python3 create_user.py <email> <new-password>
```

---

## 5. Local Setup (Manual / Development)

For active development without Docker.

### Step 5.1: Set Up PostgreSQL

```bash
# Start PostgreSQL (Ubuntu/Debian)
sudo systemctl start postgresql

# Create database and user
sudo -u postgres psql -c "CREATE USER costdetective WITH PASSWORD 'your-secure-password';"
sudo -u postgres psql -c "CREATE DATABASE costdetective OWNER costdetective;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE costdetective TO costdetective;"
```

### Step 5.2: Set Up Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL="postgresql://costdetective:your-secure-password@localhost:5432/costdetective"
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export DEBUG=true

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 5.3: Set Up Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Step 5.4: Access

| URL | Description |
|---|---|
| `http://localhost:5173` | Frontend (Vite dev server with HMR) |
| `http://localhost:8000` | Backend API |
| `http://localhost:8000/docs` | Swagger API docs |

---

## 6. Cloudflare AI Agent Setup

The Cloudflare AI Agent provides enhanced infrastructure analysis using Llama 3.1 8B on Cloudflare's edge network.

### Step 6.1: Create a Cloudflare Account

1. Go to [dash.cloudflare.com/sign-up](https://dash.cloudflare.com/sign-up)
2. Create a free account
3. Enable Workers (free tier: 100K requests/day)

### Step 6.2: Install Wrangler CLI

```bash
npm install -g wrangler

# Login to Cloudflare (opens browser)
npx wrangler login
```

### Step 6.3: Navigate to the Cloudflare Directory

```bash
cd infrastructure/cloudflare
```

### Step 6.4: Install Dependencies

```bash
npm install
```

### Step 6.5: Create Cloudflare Resources

Run each command and **note the ID from the output**:

```bash
# Create D1 database
npx wrangler d1 create cost-detective
# Output: database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# Create KV namespace for caching
npx wrangler kv:namespace create CACHE
# Output: id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Create KV namespace for rate limiting
npx wrangler kv:namespace create RATE_LIMIT
# Output: id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# Create R2 bucket for storage
npx wrangler r2 bucket create cost-detective-storage
```

### Step 6.6: Update wrangler.toml

Edit `wrangler.toml` and replace the placeholder IDs with your actual resource IDs:

```toml
[[kv_namespaces]]
binding = "CACHE"
id = "your-cache-kv-id"           # from Step 6.5
# preview_id = "your-cache-preview-id"  # optional

[[kv_namespaces]]
binding = "RATE_LIMIT"
id = "your-rate-limit-kv-id"      # from Step 6.5

[[d1_databases]]
binding = "DB"
database_name = "cost-detective"
database_id = "your-d1-database-id" # from Step 6.5

[[r2_buckets]]
binding = "STORAGE"
bucket_name = "cost-detective-storage"
```

Also update the environment-specific sections:

```toml
[env.production.kv_namespaces]
CACHE = { id = "your-cache-kv-id", preview_id = "your-cache-preview-id" }
RATE_LIMIT = { id = "your-rate-limit-kv-id", preview_id = "your-rate-limit-preview-id" }

[env.production.d1_databases]
DB = { database_name = "cost-detective-prod", database_id = "your-d1-database-id" }
```

### Step 6.7: Initialize the D1 Database

```bash
npm run db:init
```

This runs `schema.sql` against your D1 database, creating tables for analyses, users, scan history, free tier usage, infrastructure diagrams, cost estimates, and agent cache.

### Step 6.8: Deploy

```bash
# Deploy to staging (test first)
npm run deploy:staging

# Deploy to production
npm run deploy:prod
```

### Step 6.9: Verify Deployment

```bash
# Check deployment status
npx wrangler deployments list

# View live logs
npx wrangler tail

# Test the health endpoint
curl https://cost-detective-agent.<your-subdomain>.workers.dev/api/agent/health
```

### Step 6.10: Connect to the Backend

Set the Cloudflare Worker URL in `backend/.env`:

```bash
echo "CLOUDFLARE_WORKER_URL=https://cost-detective-agent.<your-subdomain>.workers.dev" >> backend/.env
```

Then restart the backend:

```bash
docker compose restart backend
```

### Cloudflare Cost Estimate

| Service | Free Tier | Paid |
|---|---|---|
| Workers | 100K requests/day | $5/mo + $0.50/million |
| D1 | 5GB storage, 5M reads/day | $0.75/GB stored |
| KV | 100K reads/day | $0.50/million reads |
| R2 | 10GB storage | $0.015/GB stored |
| AI (Llama 3.1 8B) | 10K neurons/day | $0.011/1000 neurons |

**Typical monthly cost: $5–20 for most usage patterns.**

---

## 7. Cloud Deployment (AWS via Terraform)

### Step 7.1: Configure AWS CLI

```bash
aws configure
# Enter: AWS Access Key ID, Secret Access Key, Region (e.g., us-east-1), Output format (json)
```

Verify:

```bash
aws sts get-caller-identity
```

### Step 7.2: Create terraform.tfvars

```bash
cd infrastructure/terraform
```

Create `terraform.tfvars`:

```hcl
aws_region      = "us-east-1"
environment     = "prod"
db_password     = "your-secure-password"
allowed_origins = "https://yourdomain.com"
```

### Step 7.3: Deploy

```bash
terraform init
terraform plan      # Review what will be created
terraform apply     # Type "yes" to confirm
```

### Step 7.4: Estimated AWS Costs (us-east-1)

| Component | Dev | Prod |
|---|---|---|
| RDS Aurora | ~$50/mo | ~$300/mo |
| ElastiCache | ~$15/mo | ~$60/mo |
| ALB | ~$20/mo | ~$40/mo |
| NAT Gateway | ~$35/mo | ~$35/mo |
| ECS Fargate | ~$30/mo | ~$150/mo |
| **Total** | **~$150/mo** | **~$585/mo** |

### Step 7.5: Destroy (When Done)

```bash
terraform destroy
```

---

## 8. Configuration Reference

### Environment Variables

#### Root `.env` (used by docker-compose.yml)

| Variable | Required | Default | Description |
|---|---|---|---|
| `POSTGRES_PASSWORD` | Yes | — | Database password (generate with `secrets.token_hex(24)`) |
| `POSTGRES_USER` | No | `costdetective` | Database username |
| `POSTGRES_DB` | No | `costdetective` | Database name |
| `ALLOWED_ORIGINS` | No | `http://localhost:3000,http://127.0.0.1:3000` | CORS origins (comma-separated, or `*`) |
| `CLOUDFLARE_WORKER_URL` | No | — | Cloudflare Worker URL for enhanced AI |

#### Backend `.env` (backend/.env)

| Variable | Required | Default | Description |
|---|---|---|---|
| `JWT_SECRET` | No | Auto-generated | JWT signing secret (32+ chars) |
| `DATABASE_URL` | No | Auto-built from root .env | PostgreSQL connection string |
| `DEBUG` | No | `false` | Enable Swagger UI at /docs |
| `ENABLE_METRICS` | No | `false` | Enable Prometheus /metrics endpoint |
| `MAX_CONCURRENT_SCANS` | No | `5` | Platform-wide scan limit |
| `ANALYSIS_RETENTION_DAYS` | No | `2` | Auto-delete analyses older than N days |
| `UVICORN_WORKERS` | No | `1` | Must stay at 1 unless Redis is configured |
| `LOG_FORMAT` | No | `json` | `json` or `text` |

#### AI Provider Keys (all optional — set ONE for AI analysis)

| Variable | Provider | Model | Cost |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | claude-sonnet-4-6 | $$ |
| `OPENAI_API_KEY` | GPT-4o | gpt-4o | $$ |
| `GOOGLE_API_KEY` | Gemini | gemini-2.0-flash | $ |
| `GROQ_API_KEY` | Llama 3.3 | llama-3.3-70b-versatile | $ (free tier) |
| `DEEPSEEK_API_KEY` | DeepSeek | deepseek-chat | $ |
| `XAI_API_KEY` | Grok | grok-3 | $$ |
| `MISTRAL_API_KEY` | Mistral | mistral-large-latest | $ |
| `COHERE_API_KEY` | Cohere | — | $ |
| `TOGETHER_API_KEY` | Together AI | — | $ |
| `PERPLEXITY_API_KEY` | Perplexity | — | $ |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI | — | $$ |
| `BEDROCK_REGION` | AWS Bedrock | — | $$ (uses boto3 creds) |
| `OLLAMA_BASE_URL` | Ollama (local) | — | Free |

**Force a specific provider:** `AI_PROVIDER=anthropic`

**Override the default model:** `AI_MODEL=claude-opus-4-8`

### Cloud Credentials

Credentials are entered through the UI at scan time — **never stored in the database**. They are held in memory only during scans.

#### AWS

| Method | What You Enter |
|---|---|
| Access Keys | Access Key ID + Secret Access Key |
| SSO | Browser-based device authorization |
| Organizations | Management account credentials (multi-account) |

**Minimum IAM permission:** `ReadOnlyAccess` (or `List*` / `Describe*` / `Get*` actions)

#### Azure

| Field | Required | Description |
|---|---|---|
| Subscription ID | Yes | Azure subscription UUID to scan |
| Tenant ID | No | Azure AD tenant ID |
| Client ID | No | Service Principal App ID |
| Client Secret | No | Service Principal secret |

Create a Service Principal:

```bash
az ad sp create-for-rbac --name "CostDetective" --role Reader --scopes /subscriptions/<sub-id>
```

#### GCP

| Field | Required | Description |
|---|---|---|
| Project ID | Yes | GCP project ID (6–30 lowercase chars) |
| Service Account JSON | No | Service account key file |

Required role: `roles/viewer` on the project.

---

## 9. Running the Application

### First-Time Run

```bash
# 1. Clone
git clone https://github.com/Ashokkunchala/projects.git
cd projects

# 2. Generate password
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env

# 3. Build and start
docker compose up --build -d

# 4. Wait for health check (~15 seconds)
curl http://localhost:8000/health

# 5. Open browser
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs (if DEBUG=true)
```

### Subsequent Runs

```bash
# Start (fast — no rebuild needed)
docker compose up -d

# Stop
docker compose down

# Rebuild after code changes
docker compose build backend && docker compose up -d backend
```

### Adding an AI Provider

1. Edit `backend/.env`:
   ```bash
   echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> backend/.env
   ```

2. Restart the backend:
   ```bash
   docker compose restart backend
   ```

3. Run a scan — AI analysis is automatic.

---

## 10. Testing

### Backend Tests

```bash
cd backend

# Activate virtual environment (if running locally)
source venv/bin/activate

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

**Available test files:**

| File | What It Tests |
|---|---|
| `test_auth.py` | Signup, login, JWT tokens, password validation |
| `test_db.py` | Database operations, table creation, queries |
| `test_health.py` | Health endpoint, database/Redis status |
| `test_rate_limit.py` | Rate limiting on endpoints |
| `test_sso_isolation.py` | SSO credential isolation between users |
| `test_validate_rate_limit.py` | Validation endpoint rate limiting |

### Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run tests in watch mode
npm run test:watch

# Type checking
npm run typecheck
```

### Cloudflare Worker Tests

```bash
cd infrastructure/cloudflare

# Run all tests
npm test

# Run tests in watch mode
npm run test:watch
```

### Integration Test (Full Stack)

```bash
# Start everything
docker compose up --build -d

# Wait for health
sleep 15
curl http://localhost:8000/health

# Test signup
curl -X POST http://localhost:8000/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpassword123"}'

# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"testpassword123"}'
```

---

## 11. Usage Walkthrough

### Step 1: Create an Account

1. Open `http://localhost:3000` in your browser
2. Click "Sign Up"
3. Enter your email and password (minimum 8 characters)
4. Click "Create Account"

### Step 2: Configure Cloud Provider

1. From the Dashboard, select your cloud provider (AWS, Azure, or GCP)
2. **AWS:** Enter your Access Key ID and Secret Access Key in the AWS Credentials card
3. **Azure:** Enter your Subscription ID in the Azure Credentials card
4. **GCP:** Enter your Project ID in the GCP Credentials card
5. Select the regions you want to scan
6. Choose which services to analyze

### Step 3: Run Cost Analysis

1. Click "Run Cost Analysis"
2. Watch real-time progress via WebSocket (you'll see step-by-step updates)
3. Wait for the scan to complete (typically 2–5 minutes)

### Step 4: Review the Report

The report shows findings grouped by severity:

| Severity | Color | Action |
|---|---|---|
| HIGH | Red | Fix immediately — significant savings |
| MEDIUM | Yellow | Fix when possible — moderate savings |
| LOW | Blue | Optimize when convenient — minor improvements |

Each finding includes:
- Resource name and ID
- Issue type (Unused, Over-provisioned, Misconfigured, Non-optimized)
- Estimated monthly cost
- Recommended fix with ready-to-run CLI command

### Step 5: Apply Fixes

1. Review each finding by severity
2. Copy the fix command
3. Run the command in your terminal
4. Re-scan to verify improvements

### Step 6: Track Over Time

- View historical analyses to see savings trends
- Use Free Tier tracking to stay within limits
- Use Infrastructure Visualizer to map your architecture

---

## 12. API Reference

### Authentication

```bash
# Signup
POST /api/auth/signup
Content-Type: application/json

{"email": "user@example.com", "password": "secure-password"}

# Login
POST /api/auth/login
Content-Type: application/json

{"email": "user@example.com", "password": "secure-password"}

# Logout
POST /api/auth/logout

# Change Password
POST /api/auth/change-password
Cookie: token=<jwt>
Content-Type: application/json

{"current_password": "old-password", "new_password": "new-password"}
```

### Scanning

```bash
# Start Analysis
POST /api/analyze
Cookie: token=<jwt>
Content-Type: application/json

{
  "cloud_provider": "aws",
  "regions": ["us-east-1", "eu-west-1"],
  "services": ["ec2", "rds", "s3"],
  "aws_access_key_id": "AKIA...",
  "aws_secret_access_key": "..."
}

# WebSocket Progress
WS /ws/progress/{analysis_id}

# Get Analysis Results
GET /api/history/{analysis_id}
Cookie: token=<jwt>

# Get All Analyses
GET /api/history
Cookie: token=<jwt>
```

### Free Tier

```bash
# Get Free Tier Info
GET /api/free-tier?provider=aws

# Get Usage
GET /api/free-tier/usage/aws
Cookie: token=<jwt>
```

### Infrastructure Visualization

```bash
# Parse Terraform/CloudFormation
POST /api/infra/parse
Content-Type: application/json

{
  "content": "resource \"aws_vpc\" \"main\" { cidr_block = \"10.0.0.0/16\" }",
  "file_type": "terraform"
}

# Scan Project Directory
POST /api/infra/scan-project
Content-Type: application/json

{
  "directory": "/path/to/terraform/project",
  "max_depth": 5
}
```

### Health Check

```bash
GET /health

# Response:
{"status": "ok", "db": "connected", "redis": "unavailable"}
```

Full interactive API documentation is available at `http://localhost:8000/docs` when `DEBUG=true`.

---

## 13. Troubleshooting

### "Cannot connect to server"

```bash
# Check if containers are running
docker compose ps

# View backend logs
docker compose logs backend

# Restart all services
docker compose restart
```

### "POSTGRES_PASSWORD must be set"

You haven't created the `.env` file at the project root:

```bash
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env
```

### "Port 3000 already in use"

Change the frontend port in `docker-compose.yml`:

```yaml
frontend:
  ports:
    - "0.0.0.0:3001:80"   # Changed from 3000 to 3001
```

### "WebSocket connection failed"

1. Ensure backend is running: `docker compose ps`
2. Check port 8000 is accessible: `curl http://localhost:8000/health`
3. Verify no firewall is blocking WebSocket

### "Analysis not found"

This means the analysis failed. Check:
1. Cloud credentials are valid
2. Selected regions contain resources
3. IAM permissions are correct

### "JWT_SECRET must be set" (local dev)

```bash
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
```

### "Worker not found" (Cloudflare)

```bash
npx wrangler deployments list
npx wrangler status
```

### "D1 connection failed" (Cloudflare)

```bash
npm run db:init
npx wrangler d1 execute cost-detective --command "SELECT 1"
```

### Reset Everything

```bash
# Stop and remove all data, volumes, images
docker compose down -v --rmi local

# Start fresh
docker compose up --build -d
```

### Rotate JWT Secret (logs all users out)

```bash
docker compose down
docker volume rm projects_backend_data
docker compose up -d
```

---

## 14. Security Considerations

### What's Secure by Design

- **JWT authentication** with httpOnly cookies (not accessible via JavaScript)
- **Password hashing** with bcrypt
- **No credential storage** — cloud credentials are held in memory only during scans
- **Rate limiting** on all endpoints (per-IP and per-user)
- **Input validation** with Pydantic models
- **CORS protection** — configurable allowed origins
- **Security headers** (HSTS, CSP, X-Frame-Options)
- **SQL injection prevention** — parameterized queries via asyncpg
- **SSRF prevention** — URL allowlisting for SSO endpoints
- **Non-root containers** — both backend and frontend run as unprivileged users
- **Encrypted communication** — TLS everywhere in production

### Before Going to Production

1. **Never commit secrets** — use `.env` files (they're gitignored)
2. **Use HTTPS** — configure SSL/TLS via Cloudflare or your load balancer
3. **Rotate credentials** — change database passwords regularly
4. **Enable MFA** — for AWS/Azure/GCP accounts
5. **Least privilege** — use read-only IAM policies for scanning
6. **Set `ALLOWED_ORIGINS`** — don't use `*` in production
7. **Keep `DEBUG=false`** — disable Swagger UI in production

---

## 15. Contributing & Pushing to Repo

### Setting Up for Development

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/projects.git
cd projects

# Create a feature branch
git checkout -b feature/your-feature-name

# Set up local development (see Section 5)
cd backend && python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
cd ../frontend && npm install
```

### Making Changes

```bash
# Make your changes...

# Run tests before committing
cd backend && pytest tests/ -v
cd ../frontend && npm test

# Check types
cd ../frontend && npm run typecheck
```

### Committing

```bash
# Stage changes
git add .

# Commit with a descriptive message
git commit -m "feat: add new AWS service scanning"

# Push to your fork
git push origin feature/your-feature-name
```

### Creating a Pull Request

1. Go to the original repository on GitHub
2. Click "New Pull Request"
3. Select your feature branch
4. Write a clear description of your changes
5. Submit the PR

### Commit Message Convention

| Prefix | Usage |
|---|---|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation changes |
| `test:` | Adding or updating tests |
| `refactor:` | Code restructuring (no feature change) |
| `chore:` | Build, CI, or dependency updates |

### Important: Before Pushing

**Check that no credentials or personal data are included:**

```bash
# Check for secrets in staged files
git diff --cached | grep -i "password\|secret\|api_key\|token\|aws_access"

# Verify .env files are not staged
git status  # .env should NOT appear in "Changes to be committed"
```

The `.gitignore` already excludes:
- `.env` files
- `*.pem`, `*.key`, `*.crt` (certificates)
- `credentials.json`, `service-account*.json`
- `node_modules/`, `__pycache__/`, `venv/`
- `frontend/dist/`
- Terraform state files
- Wrangler files (`.wrangler/`)

---

## Quick Reference Card

```bash
# === FIRST TIME SETUP ===
git clone https://github.com/Ashokkunchala/projects.git && cd projects
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env
docker compose up --build -d

# === DAILY USAGE ===
docker compose up -d          # Start
docker compose down           # Stop
docker compose logs -f        # View logs
docker compose ps             # Check status

# === DEVELOPMENT ===
docker compose build backend && docker compose up -d backend  # Rebuild backend
cd frontend && npm run dev                                     # Frontend dev server

# === TESTING ===
cd backend && pytest tests/ -v    # Backend tests
cd frontend && npm test           # Frontend tests

# === CLOUDFLARE ===
cd infrastructure/cloudflare
npm install && npx wrangler login
npm run db:init
npm run deploy:prod

# === ACCESS ===
# Frontend:  http://localhost:3000
# Backend:   http://localhost:8000
# API Docs:  http://localhost:8000/docs
# Health:    http://localhost:8000/health
```

---

*This guide was created for the AI Cloud Cost Detective project. For questions or issues, visit [GitHub Issues](https://github.com/Ashokkunchala/projects/issues).*
