variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name for resource tagging"
  type        = string
  default     = "cost-detective"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_count" {
  description = "Number of public subnets to create"
  type        = number
  default     = 2
}

variable "private_subnet_count" {
  description = "Number of private subnets to create"
  type        = number
  default     = 2
}

variable "enable_nat_gateway" {
  description = "Enable NAT gateway for private subnets"
  type        = bool
  default     = true
}

variable "nat_gateway_allowed_cidrs" {
  description = "CIDR blocks allowed to send traffic through the NAT gateway"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "enable_flow_logs" {
  description = "Enable VPC flow logs to CloudWatch"
  type        = bool
  default     = false
}

variable "flow_log_retention_days" {
  description = "CloudWatch log retention in days for flow logs"
  type        = number
  default     = 30
}
