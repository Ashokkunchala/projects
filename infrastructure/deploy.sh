#!/bin/bash
# AI Cloud Cost Detective - Deployment Script

set -e

echo "=== AI Cloud Cost Detective - Deployment ==="

# ─── Prerequisites Check ─────────────────────────────────────────────────────

check_prerequisites() {
    echo "Checking prerequisites..."

    if ! command -v terraform &> /dev/null; then
        echo "❌ Terraform not found. Install from https://terraform.io"
        exit 1
    fi

    if ! command -v wrangler &> /dev/null; then
        echo "❌ Wrangler not found. Install with: npm install -g wrangler"
        exit 1
    fi

    if ! command -v docker &> /dev/null; then
        echo "❌ Docker not found. Install from https://docker.com"
        exit 1
    fi

    echo "✅ All prerequisites found"
}

# ─── Terraform Deployment ─────────────────────────────────────────────────────

deploy_terraform() {
    echo ""
    echo "=== Deploying AWS Infrastructure ==="

    cd infrastructure/terraform

    # Initialize Terraform
    terraform init

    # Plan
    terraform plan -out=tfplan

    # Ask for confirmation
    read -p "Apply Terraform changes? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        terraform apply tfplan
        echo "✅ AWS infrastructure deployed"
    else
        echo "⏭️  Skipping Terraform apply"
    fi

    cd ../..
}

# ─── Cloudflare Worker Deployment ─────────────────────────────────────────────

deploy_cloudflare() {
    echo ""
    echo "=== Deploying Cloudflare AI Agent ==="

    cd infrastructure/cloudflare

    # Install dependencies
    npm install

    # Initialize D1 database
    echo "Initializing D1 database..."
    npm run db:init

    # Deploy to staging first
    echo "Deploying to staging..."
    npm run deploy:staging

    # Ask for production deployment
    read -p "Deploy to production? (yes/no): " confirm
    if [ "$confirm" = "yes" ]; then
        npm run deploy:prod
        echo "✅ Cloudflare AI Agent deployed to production"
    else
        echo "✅ Cloudflare AI Agent deployed to staging only"
    fi

    cd ../..
}

# ─── Docker Deployment ────────────────────────────────────────────────────────

deploy_docker() {
    echo ""
    echo "=== Building and Deploying Docker Containers ==="

    # Build and start containers
    docker compose build
    docker compose up -d

    echo "✅ Docker containers started"
    echo "   Frontend: http://localhost:3000"
    echo "   Backend: http://localhost:8000"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
    check_prerequisites

    echo ""
    echo "Select deployment target:"
    echo "1. Full deployment (AWS + Cloudflare + Docker)"
    echo "2. AWS infrastructure only"
    echo "3. Cloudflare AI Agent only"
    echo "4. Local Docker only"
    echo "5. Exit"

    read -p "Enter choice (1-5): " choice

    case $choice in
        1)
            deploy_terraform
            deploy_cloudflare
            deploy_docker
            ;;
        2)
            deploy_terraform
            ;;
        3)
            deploy_cloudflare
            ;;
        4)
            deploy_docker
            ;;
        5)
            echo "Exiting..."
            exit 0
            ;;
        *)
            echo "Invalid choice"
            exit 1
            ;;
    esac

    echo ""
    echo "=== Deployment Complete ==="
    echo ""
    echo "Next steps:"
    echo "1. Update .env files with your credentials"
    echo "2. Configure DNS for your domain"
    echo "3. Set up SSL certificates"
    echo "4. Configure monitoring and alerts"
}

main "$@"
