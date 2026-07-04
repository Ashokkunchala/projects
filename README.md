# AI Cloud Cost Detective

**Intelligent Multi-Cloud Cost Optimization Platform with AI Agent**

> Scan your AWS, Azure, or GCP infrastructure, detect waste, and get AI-powered recommendations to reduce your cloud bill by up to 60%.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Pages & Features](#pages--features)
- [AI Agent Integration](#ai-agent-integration)
- [Infrastructure & AI Visualizer](#infrastructure--ai-visualizer)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Security](#security)
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
| **AI-Powered Analysis** | Cloudflare Workers AI (Llama 3.1 8B) + 14 paid providers |
| **Real-time Progress** | WebSocket-based live updates during scans |
| **Cost Estimation** | Parse Terraform/CloudFormation, estimate monthly costs |
| **Fix Commands** | Ready-to-run CLI commands for each recommendation |
| **Infrastructure Visualization** | Interactive architecture diagrams with flow arrows |
| **Pre-Apply Analysis** | See resource hierarchy and connections before applying IaC |
| **Free Tier Monitoring** | Track usage against free tier limits in real-time |
| **AI Chat Assistant** | Ask questions about your infrastructure via floating chat widget |

### Security Features

| Feature | Implementation |
|---------|----------------|
| Authentication | JWT with httpOnly cookies, bcrypt password hashing |
| Social Login | GitHub, LinkedIn, Google OAuth support |
| Rate Limiting | Per-IP and per-user limits on all endpoints |
| Credential Handling | Cloud credentials never stored — memory only during scans |
| SSRF Prevention | URL allowlisting for SSO endpoints |
| Data Encryption | TLS everywhere, encrypted at rest |

---

## Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE                              │
│  React + TypeScript + Vite + Tailwind CSS                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │Dashboard │ │Estimator │ │Reports   │ │Infra & AI│ │Free Tier │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FASTAPI BACKEND                               │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Auth │ Scanning │ Analysis │ IaC Parsing │ Cost Estimation │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              │                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Cloudflare AI Worker  ◄──►  PostgreSQL  ◄──►  Redis         │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Cloudflare AI Agent

The platform uses Cloudflare Workers AI as its primary intelligence layer:

- **Model**: Llama 3.1 8B (FP8) for chat, Llama 3.2 3B for fast analysis
- **Free Tier**: 10K neurons/day on Cloudflare's free plan
- **Endpoints**: `/api/agent/analyze`, `/api/agent/validate`, `/api/agent/explain`, `/api/agent/chat`
- **Features**: SSE streaming, conversation history, context injection

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker | 24+ | Container runtime |
| Docker Compose | 2.24+ | Multi-container orchestration |

### 3-Step Setup

```bash
# 1. Clone the repository
git clone https://github.com/Ashokkunchala/projects.git
cd projects

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

## Pages & Features

### Dashboard (`/`)
- Enter cloud credentials (AWS/Azure/GCP)
- Select regions and services to scan
- Launch cost analysis with real-time progress
- View AI-generated insights from latest scan

### Cost Estimator (`/estimate`)
- Paste Terraform/CloudFormation code
- Clone Git repos for analysis
- Upload IaC files from local machine
- Get monthly cost breakdown with suggestions

### Cost Reports (`/cost-reports`)
- AWS Cost Explorer integration
- Cost forecasting and trend analysis
- EC2 rightsizing recommendations
- Personalized cost-saving tips

### Free Tier (`/free-tier`)
- Unified page with two tabs:
  - **My Usage** — Health score, service usage bars, resource details
  - **All Services** — Searchable reference for AWS/Azure/GCP free tier
- Provider selector (AWS/Azure/GCP)

### Infrastructure & AI Agent (`/infra-visualizer`)
- **Unified page** combining infrastructure visualization and AI analysis
- Input modes: Paste Code, Clone Repo, Upload Files
- Actions: Analyze, Validate, Explain, Pre-Apply
- **Pre-Apply Analysis**: See resource hierarchy, connections, and cost before applying
- **Hierarchical Architecture Diagram**: Visual tree + ASCII export
- Interactive canvas with flow arrows, zoom, pan, drag

### History (`/history`)
- View all past scans
- Compare results across scans
- Delete old analyses

---

## AI Agent Integration

### How It Works

The AI Agent is the central intelligence layer powering the entire platform:

```
User Input → Backend Proxy → Cloudflare Worker → Llama 3.1 8B → Response
     │                                                    │
     │              Model Router (simple/complex)          │
     │                    │                                │
     │              ┌─────┴─────┐                          │
     │              ▼           ▼                          │
     │         Cloudflare    Claude/GPT-4o               │
     │         (free)        (paid)                       │
     │              │           │                          │
     │              └─────┬─────┘                          │
     │                    ▼                                │
     └──────────────── Response ──────────────────────────┘
```

### Chat Widget
- Floating blue button on every authenticated page
- Context-aware (knows which page you're on)
- Conversation history saved to D1
- Quick actions: Analyze scan, Suggest fixes, Explain costs

### Model Router
- **Simple queries**: Routed to Cloudflare (free, fast)
- **Complex queries**: Routed to Claude/GPT-4o (better reasoning)
- Automatic classification based on query complexity

### Supported AI Providers

| Provider | Model | Cost |
|----------|-------|------|
| Cloudflare | Llama 3.1 8B / 3.2 3B | Free |
| Anthropic | Claude Sonnet | Paid |
| OpenAI | GPT-4o | Paid |
| Google | Gemini Flash | Paid |
| Groq | Llama 3.3 70B | Paid |
| DeepSeek | DeepSeek Chat | Paid |

---

## Infrastructure & AI Visualizer

### Pre-Apply Analysis

Before applying your Terraform/CloudFormation, see exactly how everything connects:

1. Paste code or clone a repo
2. Click **Pre-Apply** button
3. View hierarchical architecture diagram
4. See resource connections and flow
5. Get cost estimate and issue detection

### Architecture Diagram

Two visualization modes:
- **Visual**: Expandable tree with colored icons and resource details
- **ASCII**: Copy-pasteable text diagram for documentation

Example output:
```
AWS Account
└── Terraform Resources
    ├── VPC (10.0.0.0/16)
    │   ├── Subnet-A (10.0.1.0/24)
    │   │   └── EC2 Instance (t3.micro)
    │   ├── Subnet-B (10.0.2.0/24)
    │   │   └── EKS Node Group
    │   └── Security Group
    └── EKS Cluster
        └── Kubernetes
```

---

## Configuration

### Environment Variables

#### Required
| Variable | Description |
|----------|-------------|
| `POSTGRES_PASSWORD` | Database password |

#### Optional — AI Providers
Set ONE API key for paid AI analysis:

| Variable | Provider |
|----------|----------|
| `ANTHROPIC_API_KEY` | Claude |
| `OPENAI_API_KEY` | GPT-4o |
| `GOOGLE_API_KEY` | Gemini |
| `GROQ_API_KEY` | Llama 3 |

#### Optional — Runtime
| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Enable Swagger UI |
| `MAX_CONCURRENT_SCANS` | `5` | Platform-wide scan limit |
| `CLOUDFLARE_WORKER_URL` | Worker URL | AI Agent endpoint |

---

## Deployment

### Docker Compose (Local Development)

```bash
docker compose up --build -d
```

### Cloudflare Worker

```bash
cd infrastructure/cloudflare
npm install
npx wrangler login
npm run deploy:prod
```

### AWS Production

```bash
cd infrastructure/terraform
terraform init && terraform apply
```

---

## Security

- JWT with httpOnly cookies, token revocation
- GitHub/LinkedIn/Google social login
- Rate limiting on all endpoints
- Cloud credentials never stored — memory only during scans
- SSRF prevention with URL allowlisting
- TLS everywhere

---

## License

Custom MIT License with Restrictions — see [LICENSE](LICENSE) for details.

- Free for personal, non-commercial use
- Educational and research use permitted
- Commercial use requires explicit permission

---

## Author

**Ashok Kunchala**
- GitHub: [@Ashokkunchala](https://github.com/Ashokkunchala)
- Repository: [AI Cloud Cost Detective](https://github.com/Ashokkunchala/projects)
