# AI Cloud Cost Detective

**Intelligent Multi-Cloud Cost Optimization Platform**

> Scan your AWS, Azure, or GCP infrastructure, detect waste, and get AI-powered recommendations to reduce your cloud bill by up to 60%.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage Guide](#usage-guide)
- [AI Engine](#ai-engine)
- [Infrastructure Visualizer](#infrastructure-visualizer)
- [Free Tier Tracking](#free-tier-tracking)
- [API Reference](#api-reference)
- [Deployment](#deployment)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Overview

AI Cloud Cost Detective is a production-grade, open-source platform that helps organizations and individuals identify and eliminate cloud waste. Using advanced AI analysis and rule-based engines, it scans your cloud infrastructure to find:

- **Idle Resources**: Stopped instances, unused volumes, orphaned snapshots
- **Over-provisioned Resources**: VMs with low CPU utilization, oversized databases
- **Misconfigurations**: Public databases, open security groups, missing encryption
- **Hidden Costs**: Unattached Elastic IPs, unused NAT Gateways, old generation instances

### Key Metrics

| Metric | Value |
|--------|-------|
| AWS Services Scanned | 87+ |
| Azure Services Scanned | 20+ |
| GCP Services Scanned | 18+ |
| AI Providers Supported | 14+ |
| Average Savings Found | $500-2,000/month |
| Scan Time | 2-5 minutes |

---

## Features

### Core Capabilities

| Feature | Description |
|---------|-------------|
| **Multi-Cloud Support** | Scan AWS, Azure, and GCP from a single interface |
| **AI-Powered Analysis** | Use Claude, GPT-4o, Gemini, or 11+ other AI providers |
| **Real-time Progress** | WebSocket-based live updates during scans |
| **Cost Estimation** | Accurate monthly cost calculations with breakdown |
| **Fix Commands** | Ready-to-run CLI commands for each recommendation |
| **Historical Tracking** | Monitor savings over time with trend analysis |
| **Infrastructure Visualization** | Interactive architecture diagrams with connection validation |
| **Free Tier Monitoring** | Track usage against free tier limits in real-time |

### Security Features

| Feature | Implementation |
|---------|----------------|
| Authentication | JWT with httpOnly cookies, bcrypt password hashing |
| Rate Limiting | Per-IP and per-user limits on all endpoints |
| Credential Handling | Cloud credentials never stored - memory only during scans |
| SSRF Prevention | URL allowlisting for SSO endpoints |
| Data Encryption | TLS everywhere, encrypted at rest |

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    React Frontend (Vite + Tailwind)                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │Dashboard │ │ Scanner  │ │ Reports  │ │ Infra Viz│ │ Free Tier│ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            FASTAPI BACKEND                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        API Layer (REST + WebSocket)                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │  Auth    │ │ Scanning │ │Analysis  │ │  Infra   │ │ Free Tier│ │   │
│  │  │ Service  │ │ Service  │ │ Service  │ │  Viz     │ │ Tracker  │ │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                      │                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        Scanner Layer                                 │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │   │
│  │  │AWS Scan  │ │Azure Scan│ │GCP Scan  │ │AI Engine │ │Rule Engine│  │   │
│  │  │(boto3)   │ │(azure-mg)│ │(google)  │ │(14 prov) │ │(built-in) │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
              ┌───────────────────────┼───────────────────────┐
              ▼                       ▼                       ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│     PostgreSQL      │ │       Redis         │ │   Cloudflare AI     │
│   (Data Storage)    │ │    (Caching)        │ │   (Enhanced Analysis)│
└─────────────────────┘ └─────────────────────┘ └─────────────────────┘
```

### Data Flow

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  User    │───▶│ Validate │───▶│  Scan    │───▶│ Analyze  │───▶│ Report   │
│  Request │    │ Creds    │    │ Resources│    │ Findings │    │ Results  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                    │               │               │               │
                    ▼               ▼               ▼               ▼
              ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
              │ Rate     │    │ WebSocket│    │ AI/Rules │    │ Save to  │
              │ Limiter  │    │ Progress │    │ Engine   │    │ Database │
              └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24+ | Container runtime |
| Docker Compose | 2.24+ | Multi-container orchestration |
| Git | any | Version control |

### 3-Step Setup

```bash
# 1. Clone the repository
git clone https://github.com/ashokkumar-cse/AI-Cloud-Cost-Detective.git
cd AI-Cloud-Cost-Detective

# 2. Set up environment
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env

# 3. Start the application
docker compose up --build -d
```

### Access the Application

```
Frontend:  http://localhost:3000
Backend:   http://localhost:8000
API Docs:  http://localhost:8000/docs (when DEBUG=true)
```

---

## Installation

### Option 1: Docker (Recommended)

```bash
# Clone and setup
git clone https://github.com/ashokkumar-cse/AI-Cloud-Cost-Detective.git
cd AI-Cloud-Cost-Detective

# Generate secure password
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_hex(24))" > .env

# Build and start
docker compose up --build -d

# View logs
docker compose logs -f
```

### Option 2: Local Development

#### Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=postgresql://costdetective:password@localhost:5432/costdetective
export JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")

# Start the server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev
```

### Option 3: Cloud Deployment

See [Deployment Guide](#deployment) for AWS, Cloudflare, and Kubernetes instructions.

---

## Configuration

### Environment Variables

#### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | Database password | `your-secure-password` |

#### Optional - AI Providers

Set **one** API key to enable AI-powered analysis:

| Variable | Provider | Default Model |
|----------|----------|---------------|
| `ANTHROPIC_API_KEY` | Claude | claude-sonnet-4-6 |
| `OPENAI_API_KEY` | GPT-4o | gpt-4o |
| `GOOGLE_API_KEY` | Gemini | gemini-2.0-flash |
| `GROQ_API_KEY` | Llama 3 | llama-3.3-70b-versatile |
| `DEEPSEEK_API_KEY` | DeepSeek | deepseek-chat |
| `XAI_API_KEY` | Grok | grok-3 |
| `MISTRAL_API_KEY` | Mistral | mistral-large-latest |

#### Optional - Runtime

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable Swagger UI and debug mode |
| `ENABLE_METRICS` | `false` | Enable Prometheus metrics |
| `MAX_CONCURRENT_SCANS` | `5` | Platform-wide scan limit |
| `ANALYSIS_RETENTION_DAYS` | `2` | Auto-delete old analyses |

### Cloud Credentials

Credentials are entered through the UI and **never stored in the database**. They are held in memory only during scans.

#### AWS

1. **Access Keys** (Recommended for single accounts)
   - Enter Access Key ID and Secret Access Key in the dashboard

2. **AWS SSO**
   - Click "AWS SSO" tab and follow the device authorization flow

3. **Organizations** (Multi-account)
   - Enable Organizations tab and enter management account credentials

#### Azure

| Field | Required | Description |
|-------|----------|-------------|
| Subscription ID | Yes | Azure subscription to scan |
| Tenant ID | Optional | Azure AD tenant ID |
| Client ID | Optional | Service Principal App ID |
| Client Secret | Optional | Service Principal secret |

#### GCP

| Field | Required | Description |
|-------|----------|-------------|
| Project ID | Yes | GCP project to scan |
| Service Account JSON | Optional | Service account key |

---

## Usage Guide

### Step 1: Create Account

1. Navigate to `http://localhost:3000/signup`
2. Enter your email and password
3. Click "Create Account"

### Step 2: Configure Cloud Provider

1. Select your cloud provider (AWS/Azure/GCP)
2. Enter your credentials
3. Select regions to scan
4. Choose services to analyze

### Step 3: Run Analysis

1. Click "Run Cost Analysis"
2. Watch real-time progress via WebSocket
3. Review the comprehensive report

### Step 4: Apply Fixes

1. Review each finding by severity
2. Copy the fix command
3. Run the command in your terminal
4. Re-scan to verify improvements

### Understanding the Report

#### Severity Levels

| Level | Color | Action |
|-------|-------|--------|
| HIGH | Red | Fix immediately - significant savings |
| MEDIUM | Yellow | Fix when possible - moderate savings |
| LOW | Blue | Optimize when convenient - minor improvements |

#### Issue Types

| Type | Description | Example |
|------|-------------|---------|
| Unused | Resource not being used | Stopped EC2 instance |
| Over-provisioned | Resource larger than needed | m5.xlarge running at 5% CPU |
| Misconfigured | Security or cost risk | Public database |
| Non-optimized | Could be cheaper | gp2 EBS volume |

---

## AI Engine

### Supported Providers

| Provider | Model | Speed | Quality | Cost |
|----------|-------|-------|---------|------|
| Anthropic | Claude Sonnet | Fast | Excellent | $$ |
| OpenAI | GPT-4o | Fast | Excellent | $$ |
| Google | Gemini Flash | Fast | Very Good | $ |
| Groq | Llama 3.3 70B | Very Fast | Good | $ |
| DeepSeek | DeepSeek Chat | Fast | Good | $ |
| AWS Bedrock | Nova Pro | Fast | Very Good | $$ |
| Local | Ollama | Variable | Good | Free |

### Using AI Analysis

1. Set one API key in `backend/.env`
2. Restart the backend: `docker compose restart backend`
3. Run a scan - AI analysis is automatic

### Rule-Based Engine (Free)

If no AI key is set, the built-in rule engine provides analysis at no cost. It covers:
- EC2 right-sizing
- EBS volume optimization
- RDS configuration
- S3 lifecycle policies
- Lambda memory optimization
- Security group auditing

---

## Infrastructure Visualizer

### Features

- **Interactive Canvas**: Drag-and-drop nodes, zoom, pan
- **Connection Lines**: Visual resource dependencies
- **Error Detection**: Broken references highlighted in red
- **Cost Overlay**: Monthly cost displayed on each resource
- **Configuration Panel**: Full resource details on click

### Usage

1. Navigate to `/infra-visualizer`
2. Enter a local project path or Git URL
3. Click "Scan Project"
4. Interact with the diagram

### Supported Formats

| Format | Extension | Status |
|--------|-----------|--------|
| Terraform | `.tf` | Full support |
| CloudFormation | `.yaml`, `.json` | Full support |
| Kubernetes | `.yaml` | Partial support |

### Connection Validation

The visualizer detects:
- **Broken References**: Resources referencing non-existent items
- **Security Issues**: Open security groups, public databases
- **Cost Problems**: Unattached volumes, idle resources
- **Best Practice Violations**: Missing encryption, no lifecycle policies

---

## Free Tier Tracking

### AWS Free Tier

| Service | Type | Monthly Limit |
|---------|------|---------------|
| EC2 | 12-month | 750 hours (t2/t3.micro) |
| Lambda | Always Free | 1M requests + 400K GB-seconds |
| S3 | 12-month | 5 GB storage |
| RDS | 12-month | 750 hours + 20 GB |
| DynamoDB | Always Free | 25 GB + 25 RCU/WCU |
| CloudFront | Always Free | 1 TB transfer |

### Azure Free Tier

| Service | Type | Monthly Limit |
|---------|------|---------------|
| Virtual Machines | 12-month | 750 hours (B1s/B1ms) |
| Functions | Always Free | 1M executions |
| Cosmos DB | Always Free | 1000 RU/s + 25 GB |
| Storage | 12-month | 5 GB Blob |

### GCP Free Tier

| Service | Type | Monthly Limit |
|---------|------|---------------|
| Compute Engine | Always Free | 744 hours (f1-micro) |
| Cloud Functions | Always Free | 2M invocations |
| Cloud Storage | Always Free | 5 GB |
| Firestore | Always Free | 1 GB storage |

### Real-Time Usage

Navigate to `/free-tier/usage` to see:
- Current usage vs limits
- Remaining capacity
- Health score
- Warnings when approaching limits

---

## API Reference

### Authentication

```bash
# Signup
POST /api/auth/signup
{
  "email": "user@example.com",
  "password": "secure-password"
}

# Login
POST /api/auth/login
{
  "email": "user@example.com",
  "password": "secure-password"
}
```

### Scanning

```bash
# Start Analysis
POST /api/analyze
{
  "cloud_provider": "aws",
  "regions": ["us-east-1", "eu-west-1"],
  "services": ["ec2", "rds", "s3"],
  "aws_access_key_id": "AKIA...",
  "aws_secret_access_key": "..."
}

# WebSocket Progress
WS /ws/progress/{analysis_id}

# Get Results
GET /api/history/{analysis_id}
```

### Free Tier

```bash
# Get Free Tier Info
GET /api/free-tier?provider=aws

# Get Usage
GET /api/free-tier/usage/aws
```

### Infrastructure Visualization

```bash
# Parse Code
POST /api/infra/parse
{
  "content": "resource \"aws_vpc\" \"main\" {...}",
  "file_type": "terraform"
}

# Scan Project
POST /api/infra/scan-project
{
  "directory": "/path/to/terraform/project",
  "max_depth": 5
}
```

Full API documentation available at `http://localhost:8000/docs` when DEBUG=true.

---

## Deployment

### Docker Compose (Development)

```bash
docker compose up --build -d
```

### AWS (Production)

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

### Cloudflare AI Agent

```bash
cd infrastructure/cloudflare
npm install
npx wrangler login
npm run deploy:prod
```

### Environment-Specific Configs

| Environment | Database | Cache | AI |
|-------------|----------|-------|-----|
| Development | SQLite/In-Memory | None | Rule Engine |
| Staging | PostgreSQL | Redis | Groq (Free) |
| Production | Aurora PostgreSQL | ElastiCache | Claude/GPT-4o |

---

## Security

### Best Practices

1. **Never commit secrets** - Use `.env` files (gitignored)
2. **Use HTTPS in production** - Configure SSL/TLS
3. **Rotate credentials** - Change passwords regularly
4. **Enable MFA** - For AWS/Azure/GCP accounts
5. **Least privilege** - Use read-only IAM policies

### Security Features

- JWT authentication with httpOnly cookies
- Rate limiting on all endpoints
- Input validation with Pydantic
- CORS protection
- Security headers (HSTS, CSP, X-Frame-Options)
- No credential storage - memory only during scans

### Reporting Security Issues

If you discover a security vulnerability, please report it responsibly:
- Email: [security@yourdomain.com]
- Do NOT open public GitHub issues for security bugs

---

## Troubleshooting

### Common Issues

#### "Cannot connect to server"

```bash
# Check if containers are running
docker compose ps

# View logs
docker compose logs backend

# Restart services
docker compose restart
```

#### "Analysis not found"

This typically means the analysis failed. Check:
1. Cloud credentials are valid
2. Selected regions contain resources
3. IAM permissions are correct

#### "WebSocket connection failed"

1. Ensure backend is running
2. Check if port 8000 is accessible
3. Verify no firewall blocking WebSocket

### Resetting the Application

```bash
# Stop and remove all data
docker compose down -v

# Rebuild and start fresh
docker compose up --build -d
```

### Viewing Logs

```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Database only
docker compose logs -f postgres
```

---

## Contributing

### Development Setup

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest tests/` (backend), `npm test` (frontend)
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

### Code Style

- **Python**: Follow PEP 8, use type hints
- **TypeScript**: Use strict mode, prefer interfaces
- **Commits**: Use conventional commits (feat:, fix:, docs:)

### Testing

```bash
# Backend tests
cd backend
pytest tests/ -v

# Frontend tests
cd frontend
npm test
```

---

## License

This project is licensed under a **Custom MIT License with Restrictions** - see the [LICENSE](LICENSE) file for details.

### Key Points

- ✅ Free for personal, non-commercial use
- ✅ Educational and research use permitted
- ❌ Commercial use requires explicit permission
- ❌ Cannot remove author attribution
- ❌ Cannot distribute proprietary components

For commercial licensing inquiries, contact the author.

---

## Author

**Ashok Kumar**
- GitHub: [@ashokkumar-cse](https://github.com/ashokkumar-cse)
- Email: [Your Email]

### Acknowledgments

This project was developed as a comprehensive cloud cost optimization platform. The AI-powered analysis, cost estimation algorithms, and cloud scanning logic represent significant intellectual property.

---

## Support

- 📖 Documentation: [README.md](README.md)
- 🐛 Issues: [GitHub Issues](https://github.com/ashokkumar-cse/AI-Cloud-Cost-Detective/issues)
- 💬 Discussions: [GitHub Discussions](https://github.com/ashokkumar-cse/AI-Cloud-Cost-Detective/discussions)

---

**Built with ❤️ by Ashok Kumar**
