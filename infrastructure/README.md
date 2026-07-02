# AI Cloud Cost Detective - Infrastructure

## Overview

This directory contains infrastructure-as-code for deploying AI Cloud Cost Detective:
- **Terraform**: AWS infrastructure (VPC, RDS, ElastiCache, ALB, ECS)
- **Cloudflare Workers**: AI-powered infrastructure analysis agent
- **Docker Compose**: Local development and containerized deployment

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Cloudflare Edge                          │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                  AI Agent (Workers)                      │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐    │  │
│  │  │ Analyze │  │Validate │  │ Explain │  │ Optimize│    │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘    │  │
│  │       └─────────────┼───────────┼─────────────┘         │  │
│  │                     ▼           ▼                       │  │
│  │              ┌─────────────────────┐                    │  │
│  │              │  Cloudflare AI      │                    │  │
│  │              │  (Llama 3.1 8B)    │                    │  │
│  │              └─────────────────────┘                    │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐          │
│  │   D1    │  │   KV    │  │   R2    │  │  Queue  │          │
│  │Database │  │  Cache  │  │ Storage │  │ Workers │          │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          AWS Cloud                              │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                     VPC (10.0.0.0/16)                    │  │
│  │  ┌────────────────┐  ┌────────────────┐                 │  │
│  │  │   Public Sub   │  │  Private Sub   │                 │  │
│  │  │  ┌──────────┐  │  │  ┌──────────┐  │                 │  │
│  │  │  │   ALB    │  │  │  │ Backend  │  │                 │  │
│  │  │  └──────────┘  │  │  │(ECS/Fargate)│                 │  │
│  │  │  ┌──────────┐  │  │  └──────────┘  │                 │  │
│  │  │  │CloudFront│  │  │  ┌──────────┐  │                 │  │
│  │  │  └──────────┘  │  │  │ RDS      │  │                 │  │
│  │  └────────────────┘  │  │(Aurora)  │  │                 │  │
│  │                      │  └──────────┘  │                 │  │
│  │                      │  ┌──────────┐  │                 │  │
│  │                      │  │ ElastiCache│                 │  │
│  │                      │  │ (Redis)  │  │                 │  │
│  │                      │  └──────────┘  │                 │  │
│  │                      └────────────────┘                 │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- AWS CLI configured with credentials
- Cloudflare account with Workers enabled
- Terraform >= 1.0
- Wrangler CLI (`npm install -g wrangler`)
- Docker and Docker Compose

### 1. Deploy AWS Infrastructure

```bash
cd infrastructure/terraform

# Initialize
terraform init

# Plan changes
terraform plan

# Apply (requires confirmation)
terraform apply
```

### 2. Deploy Cloudflare AI Agent

```bash
cd infrastructure/cloudflare

# Install dependencies
npm install

# Login to Cloudflare
npx wrangler login

# Initialize D1 database
npm run db:init

# Deploy to staging
npm run deploy:staging

# Deploy to production (after testing)
npm run deploy:prod
```

### 3. Start Local Development

```bash
# From project root
docker compose up --build
```

Access:
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs (when DEBUG=true)

## Configuration

### Environment Variables

#### Terraform (terraform.tfvars)

```hcl
aws_region     = "us-east-1"
environment    = "prod"
db_password    = "your-secure-password"
allowed_origins = "https://yourdomain.com"
```

#### Cloudflare (wrangler.toml)

Update these values before deployment:
- `KV_NAMESPACES`: Create via `npx wrangler kv:namespace create`
- `D1_DATABASE`: Create via `npx wrangler d1 create`
- `R2_BUCKET`: Create via `npx wrangler r2 bucket create`

### AI Model Selection

The Cloudflare AI Agent uses Llama 3.1 8B by default. For enhanced analysis, you can switch to:

- `@cf/meta/llama-3.1-8b-instruct` (default, fast)
- `@cf/meta/llama-3.1-70b-instruct` (better quality, slower)
- `@cf/mistral/mistral-7b-instruct-v0.2` (alternative)

## Cost Estimation

### AWS Monthly Costs (us-east-1)

| Component | Dev | Prod |
|-----------|-----|------|
| RDS Aurora | ~$50 | ~$300 |
| ElastiCache | ~$15 | ~$60 |
| ALB | ~$20 | ~$40 |
| NAT Gateway | ~$35 | ~$35 |
| ECS Fargate | ~$30 | ~$150 |
| **Total** | **~$150** | **~$585** |

### Cloudflare Costs

| Service | Free Tier | Paid |
|---------|-----------|------|
| Workers | 100K req/day | $5/mo + $0.50/million |
| D1 | 5GB storage | $0.75/GB |
| KV | 100K reads/day | $0.50/million |
| R2 | 10GB storage | $0.015/GB |
| AI | 10K neurons/day | $0.011/1000 neurons |

## Security

- All data encrypted at rest (RDS, ElastiCache, S3)
- TLS everywhere (ALB, Cloudflare)
- IAM roles with least privilege
- VPC with private subnets for databases
- Security groups restrict access
- Cloudflare WAF protection

## Monitoring

- AWS CloudWatch for infrastructure metrics
- Cloudflare Analytics for edge metrics
- Application logs to CloudWatch Logs
- Custom dashboards for cost tracking

## Troubleshooting

### Terraform Issues

```bash
# Refresh state
terraform refresh

# Import existing resources
terraform import aws_vpc.main vpc-xxx

# Destroy and recreate
terraform destroy
terraform apply
```

### Cloudflare Worker Issues

```bash
# View logs
npx wrangler tail

# Test locally
npx wrangler dev

# Check D1 data
npx wrangler d1 execute cost-detective --command "SELECT * FROM analyses LIMIT 10"
```

### Docker Issues

```bash
# Rebuild containers
docker compose build --no-cache

# View logs
docker compose logs -f backend

# Reset database
docker compose down -v
docker compose up --build
```

## Contributing

1. Create a feature branch
2. Make changes
3. Test locally with Docker
4. Submit PR with infrastructure changes documented

## License

MIT License - see LICENSE file
