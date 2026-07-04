terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

# ─── VPC ──────────────────────────────────────────────────────────────────────

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name = "${var.environment}-vpc"
  }
}

# ─── Internet Gateway ────────────────────────────────────────────────────────

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.environment}-igw"
  }
}

# ─── Public Subnets ──────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  count                   = var.public_subnet_count
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone       = data.aws_availability_zones.available.names[count.index % length(data.aws_availability_zones.available.names)]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.environment}-public-${count.index + 1}"
    Tier = "public"
  }
}

# ─── Private Subnets ─────────────────────────────────────────────────────────

resource "aws_subnet" "private" {
  count             = var.private_subnet_count
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index + 10)
  availability_zone = data.aws_availability_zones.available.names[count.index % length(data.aws_availability_zones.available.names)]

  tags = {
    Name = "${var.environment}-private-${count.index + 1}"
    Tier = "private"
  }
}

# ─── NAT Gateway Security Group ──────────────────────────────────────────────

resource "aws_security_group" "nat" {
  count       = var.enable_nat_gateway ? 1 : 0
  name_prefix = "${var.environment}-nat-"
  description = "Security group for NAT gateway - restricts inbound traffic"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = var.nat_gateway_allowed_cidrs
    description = "Allow inbound from specified CIDRs only"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound traffic"
  }

  tags = {
    Name = "${var.environment}-nat-sg"
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ─── NAT Gateway ─────────────────────────────────────────────────────────────

resource "aws_eip" "nat" {
  count  = var.enable_nat_gateway ? 1 : 0
  domain = "vpc"

  tags = {
    Name = "${var.environment}-nat-eip"
  }
}

resource "aws_nat_gateway" "main" {
  count              = var.enable_nat_gateway ? 1 : 0
  allocation_id      = aws_eip.nat[0].id
  subnet_id          = aws_subnet.public[0].id
  security_groups    = [aws_security_group.nat[0].id]

  tags = {
    Name = "${var.environment}-nat"
  }

  depends_on = [aws_internet_gateway.main]
}

# ─── Public Route Table ──────────────────────────────────────────────────────

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = {
    Name = "${var.environment}-public-rt"
  }
}

resource "aws_route_table_association" "public" {
  count          = var.public_subnet_count
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# ─── Private Route Table ─────────────────────────────────────────────────────

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  dynamic "route" {
    for_each = var.enable_nat_gateway ? [1] : []
    content {
      cidr_block     = "0.0.0.0/0"
      nat_gateway_id = aws_nat_gateway.main[0].id
    }
  }

  tags = {
    Name = "${var.environment}-private-rt"
  }
}

resource "aws_route_table_association" "private" {
  count          = var.private_subnet_count
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

# ─── VPC Flow Logs ───────────────────────────────────────────────────────────

resource "aws_flow_log" "main" {
  count                = var.enable_flow_logs ? 1 : 0
  iam_role_arn         = aws_iam_role.flow_log[0].arn
  log_destination      = aws_cloudwatch_log_group.flow_log[0].arn
  traffic_type         = "ALL"
  vpc_id               = aws_vpc.main.id
  max_aggregation_interval = 60

  tags = {
    Name = "${var.environment}-flow-log"
  }
}

resource "aws_cloudwatch_log_group" "flow_log" {
  count             = var.enable_flow_logs ? 1 : 0
  name              = "/aws/vpc/flow-log/${var.environment}"
  retention_in_days = var.flow_log_retention_days

  tags = {
    Name = "${var.environment}-flow-log-group"
  }
}

resource "aws_iam_role" "flow_log" {
  count = var.enable_flow_logs ? 1 : 0
  name  = "${var.environment}-vpc-flow-log-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "vpc-flow-logs.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "flow_log" {
  count = var.enable_flow_logs ? 1 : 0
  name  = "${var.environment}-vpc-flow-log-policy"
  role  = aws_iam_role.flow_log[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogGroups",
        "logs:DescribeLogStreams"
      ]
      Effect   = "Allow"
      Resource = "*"
    }]
  })
}

# ─── Default Security Group ──────────────────────────────────────────────────

resource "aws_default_security_group" "default" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "${var.environment}-default-sg"
  }
}
