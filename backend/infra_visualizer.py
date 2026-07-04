"""
Infrastructure Visualizer - Parses Terraform/IaC files and generates live diagrams.
Provides resource relationships, flow charts, and configuration details.
"""

import re
import json
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class ResourceType(Enum):
    COMPUTE = "compute"
    STORAGE = "storage"
    DATABASE = "database"
    NETWORKING = "networking"
    SECURITY = "security"
    LOAD_BALANCER = "load_balancer"
    CONTAINER = "container"
    SERVERLESS = "serverless"
    DNS = "dns"
    CACHE = "cache"
    QUEUE = "queue"
    MONITORING = "monitoring"


@dataclass
class InfraResource:
    id: str
    type: str
    name: str
    provider: str
    category: ResourceType
    config: Dict[str, Any] = field(default_factory=dict)
    connections: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    estimated_cost: float = 0.0
    free_tier_eligible: bool = False

    def to_dict(self):
        return asdict(self)


# Terraform resource type mapping
TERRAFORM_TYPE_MAP = {
    # AWS Compute
    "aws_instance": ("EC2 Instance", ResourceType.COMPUTE),
    "aws_launch_template": ("Launch Template", ResourceType.COMPUTE),
    "aws_autoscaling_group": ("Auto Scaling Group", ResourceType.COMPUTE),
    "aws_spot_instance_request": ("Spot Instance", ResourceType.COMPUTE),

    # AWS Storage
    "aws_ebs_volume": ("EBS Volume", ResourceType.STORAGE),
    "aws_s3_bucket": ("S3 Bucket", ResourceType.STORAGE),
    "aws_efs_file_system": ("EFS File System", ResourceType.STORAGE),
    "aws_fsx_windows_file_system": ("FSx File System", ResourceType.STORAGE),

    # AWS Database
    "aws_db_instance": ("RDS Instance", ResourceType.DATABASE),
    "aws_rds_cluster": ("Aurora Cluster", ResourceType.DATABASE),
    "aws_elasticache_cluster": ("ElastiCache Cluster", ResourceType.CACHE),
    "aws_dynamodb_table": ("DynamoDB Table", ResourceType.DATABASE),
    "aws_redshift_cluster": ("Redshift Cluster", ResourceType.DATABASE),

    # AWS Networking
    "aws_vpc": ("VPC", ResourceType.NETWORKING),
    "aws_subnet": ("Subnet", ResourceType.NETWORKING),
    "aws_internet_gateway": ("Internet Gateway", ResourceType.NETWORKING),
    "aws_nat_gateway": ("NAT Gateway", ResourceType.NETWORKING),
    "aws_route_table": ("Route Table", ResourceType.NETWORKING),
    "aws_security_group": ("Security Group", ResourceType.SECURITY),
    "aws_network_acl": ("Network ACL", ResourceType.SECURITY),
    "aws_eip": ("Elastic IP", ResourceType.NETWORKING),
    "aws_vpc_endpoint": ("VPC Endpoint", ResourceType.NETWORKING),
    "aws_transit_gateway": ("Transit Gateway", ResourceType.NETWORKING),

    # AWS Load Balancer
    "aws_lb": ("Load Balancer", ResourceType.LOAD_BALANCER),
    "aws_alb": ("Application Load Balancer", ResourceType.LOAD_BALANCER),
    "aws_elb": ("Classic Load Balancer", ResourceType.LOAD_BALANCER),
    "aws_lb_target_group": ("Target Group", ResourceType.LOAD_BALANCER),

    # AWS Container
    "aws_ecs_cluster": ("ECS Cluster", ResourceType.CONTAINER),
    "aws_ecs_service": ("ECS Service", ResourceType.CONTAINER),
    "aws_ecs_task_definition": ("Task Definition", ResourceType.CONTAINER),
    "aws_eks_cluster": ("EKS Cluster", ResourceType.CONTAINER),
    "aws_eks_node_group": ("EKS Node Group", ResourceType.CONTAINER),
    "aws_ecr_repository": ("ECR Repository", ResourceType.CONTAINER),

    # AWS Serverless
    "aws_lambda_function": ("Lambda Function", ResourceType.SERVERLESS),
    "aws_api_gateway_rest_api": ("API Gateway", ResourceType.SERVERLESS),
    "aws_apigatewayv2_api": ("API Gateway v2", ResourceType.SERVERLESS),

    # AWS DNS
    "aws_route53_zone": ("Route 53 Zone", ResourceType.DNS),
    "aws_route53_record": ("Route 53 Record", ResourceType.DNS),
    "aws_cloudfront_distribution": ("CloudFront Distribution", ResourceType.DNS),

    # AWS Queue
    "aws_sqs_queue": ("SQS Queue", ResourceType.QUEUE),
    "aws_sns_topic": ("SNS Topic", ResourceType.QUEUE),

    # AWS Monitoring
    "aws_cloudwatch_log_group": ("CloudWatch Log Group", ResourceType.MONITORING),
    "aws_cloudwatch_metric_alarm": ("CloudWatch Alarm", ResourceType.MONITORING),

    # Azure
    "azurerm_virtual_machine": ("Virtual Machine", ResourceType.COMPUTE),
    "azurerm_linux_virtual_machine": ("Linux VM", ResourceType.COMPUTE),
    "azurerm_windows_virtual_machine": ("Windows VM", ResourceType.COMPUTE),
    "azurerm_managed_disk": ("Managed Disk", ResourceType.STORAGE),
    "azurerm_storage_account": ("Storage Account", ResourceType.STORAGE),
    "azurerm_sql_database": ("SQL Database", ResourceType.DATABASE),
    "azurerm_cosmosdb_account": ("Cosmos DB", ResourceType.DATABASE),
    "azurerm_virtual_network": ("Virtual Network", ResourceType.NETWORKING),
    "azurerm_subnet": ("Subnet", ResourceType.NETWORKING),
    "azurerm_network_security_group": ("NSG", ResourceType.SECURITY),
    "azurerm_public_ip": ("Public IP", ResourceType.NETWORKING),
    "azurerm_lb": ("Load Balancer", ResourceType.LOAD_BALANCER),
    "azurerm_kubernetes_cluster": ("AKS Cluster", ResourceType.CONTAINER),
    "azurerm_app_service": ("App Service", ResourceType.COMPUTE),
    "azurerm_function_app": ("Function App", ResourceType.SERVERLESS),

    # GCP
    "google_compute_instance": ("Compute Instance", ResourceType.COMPUTE),
    "google_compute_disk": ("Persistent Disk", ResourceType.STORAGE),
    "google_storage_bucket": ("Storage Bucket", ResourceType.STORAGE),
    "google_sql_database_instance": ("Cloud SQL", ResourceType.DATABASE),
    "google_compute_network": ("VPC Network", ResourceType.NETWORKING),
    "google_compute_subnetwork": ("Subnet", ResourceType.NETWORKING),
    "google_compute_firewall": ("Firewall Rule", ResourceType.SECURITY),
    "google_compute_global_address": ("Global IP", ResourceType.NETWORKING),
    "google_container_cluster": ("GKE Cluster", ResourceType.CONTAINER),
    "google_cloudfunctions_function": ("Cloud Function", ResourceType.SERVERLESS),
    "google_cloud_run_service": ("Cloud Run", ResourceType.SERVERLESS),
    "google_dns_managed_zone": ("Cloud DNS", ResourceType.DNS),
    "google_redis_instance": ("Memorystore", ResourceType.CACHE),
    "google_pubsub_topic": ("Pub/Sub", ResourceType.QUEUE),

    # CloudFormation
    "AWS::EC2::Instance": ("EC2 Instance", ResourceType.COMPUTE),
    "AWS::EC2::Volume": ("EBS Volume", ResourceType.STORAGE),
    "AWS::S3::Bucket": ("S3 Bucket", ResourceType.STORAGE),
    "AWS::RDS::DBInstance": ("RDS Instance", ResourceType.DATABASE),
    "AWS::EC2::VPC": ("VPC", ResourceType.NETWORKING),
    "AWS::EC2::Subnet": ("Subnet", ResourceType.NETWORKING),
    "AWS::EC2::SecurityGroup": ("Security Group", ResourceType.SECURITY),
    "AWS::EC2::NatGateway": ("NAT Gateway", ResourceType.NETWORKING),
    "AWS::ElasticLoadBalancingV2::LoadBalancer": ("Load Balancer", ResourceType.LOAD_BALANCER),
    "AWS::ECS::Cluster": ("ECS Cluster", ResourceType.CONTAINER),
    "AWS::ECS::Service": ("ECS Service", ResourceType.CONTAINER),
    "AWS::Lambda::Function": ("Lambda Function", ResourceType.SERVERLESS),
    "AWS::Route53::HostedZone": ("Route 53 Zone", ResourceType.DNS),
}


# Category colors for visualization
CATEGORY_COLORS = {
    ResourceType.COMPUTE: "#6366f1",
    ResourceType.STORAGE: "#8b5cf6",
    ResourceType.DATABASE: "#06b6d4",
    ResourceType.NETWORKING: "#10b981",
    ResourceType.SECURITY: "#ef4444",
    ResourceType.LOAD_BALANCER: "#f59e0b",
    ResourceType.CONTAINER: "#3b82f6",
    ResourceType.SERVERLESS: "#ec4899",
    ResourceType.DNS: "#14b8a6",
    ResourceType.CACHE: "#f97316",
    ResourceType.QUEUE: "#a855f7",
    ResourceType.MONITORING: "#64748b",
}


def parse_terraform_hcl(content: str) -> Dict[str, InfraResource]:
    """Parse Terraform HCL content and extract resources."""
    resources = {}
    current_resource = None
    current_block = []
    brace_count = 0

    for line in content.split('\n'):
        stripped = line.strip()

        # Detect resource block start
        resource_match = re.match(r'^resource\s+"([^"]+)"\s+"([^"]+)"\s*\{', stripped)
        if resource_match:
            if current_resource and current_block:
                _process_block(current_resource, current_block, resources)
            current_resource = {
                "type": resource_match.group(1),
                "name": resource_match.group(2),
            }
            # Extract content after the opening brace on the same line
            after_brace = stripped[stripped.index('{') + 1:].strip().rstrip('}').strip()
            current_block = [after_brace] if after_brace else []
            # Count braces on this line (after the resource line opening)
            brace_count = 1 + stripped.count('{') - 1 - stripped.count('}')
            if brace_count <= 0:
                # Single-line block like: resource "x" "y" { key = "val" }
                _process_block(current_resource, current_block, resources)
                current_resource = None
                current_block = []
                brace_count = 0
            continue

        if current_resource:
            brace_count += stripped.count('{') - stripped.count('}')
            if brace_count <= 0:
                _process_block(current_resource, current_block, resources)
                current_resource = None
                current_block = []
                brace_count = 0
            else:
                current_block.append(stripped)

    # Process last block
    if current_resource and current_block:
        _process_block(current_resource, current_block, resources)

    return resources


def parse_terraform_content(content: str) -> Dict[str, InfraResource]:
    """Parse Terraform content and return dict of InfraResource objects."""
    return parse_terraform_hcl(content)


def _process_block(resource: dict, lines: list, resources: dict):
    """Process a Terraform resource block."""
    rtype = resource["type"]
    rname = resource["name"]

    # Get resource info from mapping
    type_info = TERRAFORM_TYPE_MAP.get(rtype)
    if not type_info:
        return

    display_name, category = type_info

    # Parse attributes
    config = {}
    connections = []
    tags = {}

    for line in lines:
        # Simple key = value parsing
        kv_match = re.match(r'^(\w+)\s*=\s*(.+)$', line)
        if kv_match:
            key = kv_match.group(1)
            value = kv_match.group(2).strip().strip('"').strip("'")
            config[key] = value

            # Detect references to other resources
            ref_match = re.search(r'(\w+)\.(\w+)\.(\w+)', value)
            if ref_match:
                connections.append(f"{ref_match.group(1)}.{ref_match.group(2)}.{ref_match.group(3)}")

        # Parse tags block
        if line.startswith('tags') and '{' in line:
            in_tags = True
        elif line == '}':
            in_tags = False
        elif 'in_tags' in locals() and in_tags:
            tag_match = re.match(r'^(\w+)\s*=\s*"(.+)"', line)
            if tag_match:
                tags[tag_match.group(1)] = tag_match.group(2)

    # Check for VPC/Subnet references in connection detection
    for key, value in config.items():
        if 'vpc_id' in key or 'subnet_id' in key:
            ref = re.search(r'(\w+\.\w+\.\w+)', str(value))
            if ref:
                connections.append(ref.group(1))

    # Determine if free tier eligible
    free_tier_eligible = _check_free_tier_eligible(rtype, config)

    # Estimate cost
    estimated_cost = _estimate_cost(rtype, config)

    resource_id = f"{rtype}.{rname}"
    resources[resource_id] = InfraResource(
        id=resource_id,
        type=rtype,
        name=config.get("tags", {}).get("Name", rname) if isinstance(config.get("tags"), dict) else rname,
        provider=_get_provider(rtype),
        category=category,
        config=config,
        connections=connections,
        tags=tags,
        estimated_cost=estimated_cost,
        free_tier_eligible=free_tier_eligible,
    )


def _get_provider(rtype: str) -> str:
    """Determine cloud provider from resource type."""
    if rtype.startswith("aws_") or rtype.startswith("AWS::"):
        return "aws"
    elif rtype.startswith("azurerm_"):
        return "azure"
    elif rtype.startswith("google_"):
        return "gcp"
    return "unknown"


def _check_free_tier_eligible(rtype: str, config: dict) -> bool:
    """Check if resource is free tier eligible."""
    if rtype == "aws_instance":
        itype = config.get("instance_type", "")
        return itype in ["t2.micro", "t3.micro"]
    elif rtype == "aws_db_instance":
        itype = config.get("instance_class", "")
        return itype in ["db.t2.micro", "db.t3.micro"]
    elif rtype == "aws_s3_bucket":
        return True  # S3 has free tier
    elif rtype == "aws_lambda_function":
        return True  # Lambda has free tier
    elif rtype == "aws_ebs_volume":
        return config.get("type", "") in ["gp2", "gp3"]
    return False


def _estimate_cost(rtype: str, config: dict) -> float:
    """Estimate monthly cost for a resource."""
    # Simplified cost estimation
    if rtype == "aws_instance":
        itype = config.get("instance_type", "t3.micro")
        costs = {
            "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37,
            "t3.large": 60.74, "m5.large": 70.08, "m5.xlarge": 140.16,
        }
        return costs.get(itype, 50.0)
    elif rtype == "aws_ebs_volume":
        size = int(config.get("size", 100))
        return size * 0.08
    elif rtype == "aws_db_instance":
        itype = config.get("instance_class", "db.t3.micro")
        costs = {"db.t3.micro": 12.41, "db.t3.small": 24.82, "db.r5.large": 175.2}
        return costs.get(itype, 50.0)
    elif rtype == "aws_nat_gateway":
        return 32.40
    elif rtype in ["aws_lb", "aws_alb"]:
        return 22.0
    elif rtype == "aws_s3_bucket":
        return 1.0
    elif rtype == "aws_lambda_function":
        return 5.0
    return 0.0


def parse_cloudformation(content: str) -> Dict[str, List[Dict]]:
    """Parse CloudFormation YAML/JSON and extract resources."""
    import yaml
    resources = {}

    try:
        # Try JSON first
        template = json.loads(content)
    except json.JSONDecodeError:
        try:
            template = yaml.safe_load(content)
        except yaml.YAMLError:
            return resources

    if "Resources" not in template:
        return resources

    for logical_id, resource in template["Resources"].items():
        rtype = resource.get("Type", "")
        props = resource.get("Properties", {})

        type_info = TERRAFORM_TYPE_MAP.get(rtype)
        if not type_info:
            continue

        display_name, category = type_info

        # Extract connections from Ref and GetAtt
        connections = []
        for key, value in props.items():
            if isinstance(value, dict):
                if "Ref" in value:
                    connections.append(value["Ref"])
                elif "Fn::GetAtt" in value:
                    connections.append(f"{value['Fn::GetAtt'][0]}.{value['Fn::GetAtt'][1]}")

        resource_id = f"{rtype}.{logical_id}"
        resources[resource_id] = InfraResource(
            id=resource_id,
            type=rtype,
            name=props.get("Tags", [{}])[0].get("Value", logical_id) if props.get("Tags") else logical_id,
            provider=_get_provider(rtype),
            category=category,
            config=props,
            connections=connections,
            tags={t["Key"]: t["Value"] for t in props.get("Tags", [])},
            estimated_cost=_estimate_cost(rtype, props),
            free_tier_eligible=_check_free_tier_eligible(rtype, props),
        )

    return resources


def generate_infra_diagram(resources: Dict[str, InfraResource]) -> dict:
    """Generate a diagram structure from parsed resources."""
    nodes = []
    edges = []
    suggestions = []
    broken_connections = []

    # Group resources by category
    category_groups = {}
    for resource in resources.values():
        cat = resource.category.value
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(resource)

    # Create nodes
    for resource in resources.values():
        node = {
            "id": resource.id,
            "label": resource.name,
            "type": resource.type,
            "category": resource.category.value,
            "color": CATEGORY_COLORS.get(resource.category, "#64748b"),
            "config": resource.config,
            "estimated_cost": resource.estimated_cost,
            "free_tier_eligible": resource.free_tier_eligible,
        }
        nodes.append(node)

    # Create edges from connections — validate each one
    for resource in resources.values():
        for conn in resource.connections:
            # Skip empty or internal refs
            if not conn or conn.startswith("var.") or conn.startswith("local.") or conn.startswith("module.") or conn.startswith("data."):
                continue

            # Try to find matching resource
            target_id = None
            for r in resources.values():
                if r.id.endswith(f".{conn}") or r.name == conn:
                    target_id = r.id
                    break

            if target_id and target_id != resource.id:
                edge = {
                    "source": resource.id,
                    "target": target_id,
                    "type": "depends_on",
                    "valid": True,
                }
                edges.append(edge)
            else:
                # Broken connection — reference points to non-existent resource
                broken_connections.append({
                    "source": resource.id,
                    "source_name": resource.name,
                    "reference": conn,
                    "message": f"'{resource.name}' references '{conn}' but no matching resource exists in the configuration",
                })

    # ─── Connection validation rules ──────────────────────────────────────
    node_ids = {n["id"] for n in nodes}

    # Check: security groups with 0.0.0.0/0 ingress
    for resource in resources.values():
        if "security_group" in resource.type.lower():
            config = resource.config
            ingress_raw = str(config.get("ingress", ""))
            if "0.0.0.0/0" in ingress_raw or "0.0.0.0/0" in str(config):
                suggestions.append({
                    "type": "security",
                    "severity": "high",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Security group '{resource.name}' allows traffic from 0.0.0.0/0 (the entire internet).",
                    "explanation": "This is a critical security risk. Any IP address can reach your resource. Only open ports to known IPs or use a VPN/bastion host.",
                    "fix": "Restrict cidr_blocks to specific trusted IP ranges (e.g., your office IP: '203.0.113.0/24'). For SSH, use a bastion host instead of opening port 22 to the world.",
                    "fix_example": 'cidr_blocks = ["203.0.113.0/24"]  # Your office IP only',
                })

    # Check: EC2 without security group
    for resource in resources.values():
        if resource.type in ("aws_instance", "azurerm_virtual_machine", "google_compute_instance"):
            has_sg = any("security_group" in c.lower() or "vpc_security_group" in c.lower() for c in resource.connections)
            if not has_sg:
                config_str = str(resource.config)
                if "security_group" not in config_str.lower() and "vpc_security_group" not in config_str.lower():
                    suggestions.append({
                        "type": "security",
                        "severity": "medium",
                        "resource": resource.name,
                        "resource_id": resource.id,
                        "message": f"Instance '{resource.name}' has no security group attached.",
                        "explanation": "Without a security group, the instance may have no firewall rules or may use the default VPC security group which often allows all inbound traffic.",
                        "fix": "Attach a security group with explicit ingress/egress rules.",
                    })

    # Check: RDS publicly accessible
    for resource in resources.values():
        if "db_instance" in resource.type.lower() or "rds" in resource.type.lower():
            config = resource.config
            if config.get("publicly_accessible") is True or str(config.get("publicly_accessible", "")).lower() == "true":
                suggestions.append({
                    "type": "security",
                    "severity": "high",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Database '{resource.name}' is publicly accessible.",
                    "explanation": "A publicly accessible database can be reached from the internet if the security group allows it. This dramatically increases your attack surface.",
                    "fix": "Set publicly_accessible = false and connect through a private subnet or VPC.",
                    "fix_example": 'publicly_accessible = false',
                })

    # Check: old instance types (t2 → t3, m4 → m5, etc.)
    upgrade_map = {
        "t2.nano": "t3.nano", "t2.micro": "t3.micro", "t2.small": "t3.small",
        "t2.medium": "t3.medium", "t2.large": "t3.large",
        "m4.large": "m5.large", "m4.xlarge": "m5.xlarge",
        "m4.2xlarge": "m5.2xlarge", "m4.4xlarge": "m5.4xlarge",
    }
    for resource in resources.values():
        if resource.type == "aws_instance":
            itype = resource.config.get("instance_type", "")
            if itype in upgrade_map:
                new_type = upgrade_map[itype]
                savings_pct = 10
                suggestions.append({
                    "type": "cost",
                    "severity": "low",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Instance '{resource.name}' uses older generation {itype}.",
                    "explanation": f"Upgrading from {itype} to {new_type} gives ~{savings_pct}% better price-performance with newer hardware.",
                    "fix": f"Change instance_type from '{itype}' to '{new_type}'.",
                    "fix_example": f'instance_type = "{new_type}"',
                    "estimated_savings": f"~{savings_pct}% monthly compute cost",
                })

    # Check: EBS gp2 → gp3
    for resource in resources.values():
        if resource.type == "aws_ebs_volume":
            vol_type = resource.config.get("type", "")
            if vol_type == "gp2":
                suggestions.append({
                    "type": "cost",
                    "severity": "low",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"EBS volume '{resource.name}' uses gp2. gp3 is cheaper and faster.",
                    "explanation": "gp3 provides 3,000 baseline IOPS and 125 MB/s throughput for $0.08/GB — same baseline as gp2 at $0.10/GB, but gp3 lets you provision up to 16,000 IOPS without paying for IOPS separately.",
                    "fix": "Migrate from gp2 to gp3 for 20% storage cost savings.",
                    "fix_example": 'type = "gp3"',
                    "estimated_savings": "~20% on EBS storage costs",
                })

    # Check: unattached EBS volumes
    for resource in resources.values():
        if resource.type == "aws_ebs_volume":
            attachments = resource.config.get("attachments", [])
            if not attachments and not any("instance" in c for c in resource.connections):
                suggestions.append({
                    "type": "cost",
                    "severity": "medium",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"EBS volume '{resource.name}' appears unattached.",
                    "explanation": "Unattached EBS volumes continue to incur storage costs ($0.08-0.125/GB/month) even though nothing is using them. This is one of the most common sources of cloud waste.",
                    "fix": "Attach the volume to an instance or delete it if no longer needed.",
                    "fix_example": "# Delete: aws ec2 delete-volume --volume-id <id>",
                })

    # Check: unassociated Elastic IPs
    for resource in resources.values():
        if resource.type == "aws_eip":
            if not any("instance" in c or "nat" in c for c in resource.connections):
                suggestions.append({
                    "type": "cost",
                    "severity": "medium",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Elastic IP '{resource.name}' is not associated with any resource.",
                    "explanation": "Unassociated Elastic IPs cost $3.60/month while sitting idle. AWS charges for unused public IPs to encourage efficient use.",
                    "fix": "Associate the IP with an instance or NAT gateway, or release it.",
                    "fix_example": "# Release: aws ec2 release-address --allocation-id <id>",
                })

    # Check: NAT Gateway (always expensive)
    for resource in resources.values():
        if resource.type == "aws_nat_gateway":
            suggestions.append({
                "type": "cost",
                "severity": "info",
                "resource": resource.name,
                "resource_id": resource.id,
                "message": f"NAT Gateway '{resource.name}' costs ~$32/month plus data processing fees.",
                "explanation": "NAT Gateways have a fixed hourly cost of $0.045/hr ($32.40/mo) plus $0.045/GB processed. For dev/test environments, consider a NAT instance (t3.medium ~$15/mo) or VPC endpoints to avoid NAT entirely.",
                "fix": "For non-production: use a NAT instance. For production: keep the NAT Gateway but add VPC endpoints for S3/DynamoDB to reduce data processing costs.",
            })

    # Check: Lambda over-provisioned memory
    for resource in resources.values():
        if resource.type == "aws_lambda_function":
            memory = resource.config.get("memory_size", 128)
            if isinstance(memory, (int, float)) and memory >= 1024:
                suggestions.append({
                    "type": "cost",
                    "severity": "low",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Lambda '{resource.name}' has {memory}MB memory allocated.",
                    "explanation": "Most Lambda functions don't need 1GB+ memory. Memory also controls CPU allocation, so reducing memory reduces both memory cost and CPU cost proportionally.",
                    "fix": "Start with 256MB and increase only if the function times out or runs slowly.",
                    "fix_example": 'memory_size = 256',
                })

    # Check: S3 without lifecycle policy
    for resource in resources.values():
        if resource.type == "aws_s3_bucket":
            has_lifecycle = "lifecycle" in str(resource.config).lower()
            if not has_lifecycle:
                suggestions.append({
                    "type": "cost",
                    "severity": "low",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"S3 bucket '{resource.name}' has no lifecycle policy configured.",
                    "explanation": "Without lifecycle rules, old objects stay in Standard storage forever. Moving old data to Infrequent Access (40% cheaper) or Glacier (80% cheaper) after 30-90 days dramatically reduces storage costs.",
                    "fix": "Add a lifecycle configuration to transition old objects to cheaper storage tiers.",
                })

    # Check: Load balancer with no targets
    for resource in resources.values():
        if resource.type in ("aws_lb", "aws_alb", "aws_elb"):
            has_targets = any("target" in c.lower() or "instance" in c.lower() for c in resource.connections)
            if not has_targets:
                suggestions.append({
                    "type": "cost",
                    "severity": "medium",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"Load balancer '{resource.name}' may have no registered targets.",
                    "explanation": "An idle ALB costs ~$22/month, an NLB costs ~$20/month. If nothing is registered behind it, you're paying for nothing.",
                    "fix": "Register target instances or delete the load balancer if unused.",
                })

    # Check: ElastiCache over-provisioned
    for resource in resources.values():
        if resource.type == "aws_elasticache_cluster":
            node_type = resource.config.get("cache_node_type", "")
            if node_type.startswith("cache.r"):
                suggestions.append({
                    "type": "cost",
                    "severity": "medium",
                    "resource": resource.name,
                    "resource_id": resource.id,
                    "message": f"ElastiCache '{resource.name}' uses memory-optimized node type '{node_type}'.",
                    "explanation": "Memory-optimized nodes (cache.r5/r6g) cost $75-150+/month each. If your workload doesn't require high memory, cache.t3.medium ($30/mo) or serverless ElastiCache may be cheaper.",
                    "fix": "Right-size to a smaller node type or evaluate ElastiCache Serverless.",
                })

    # Calculate layout positions
    _calculate_layout(nodes, edges)

    # Calculate totals
    total_cost = sum(n["estimated_cost"] for n in nodes)
    free_tier_count = sum(1 for n in nodes if n["free_tier_eligible"])

    return {
        "nodes": nodes,
        "edges": edges,
        "broken_connections": broken_connections,
        "suggestions": suggestions,
        "summary": {
            "total_resources": len(nodes),
            "total_edges": len(edges),
            "broken_connections": len(broken_connections),
            "suggestions": len(suggestions),
            "high_severity": sum(1 for s in suggestions if s.get("severity") == "high"),
            "estimated_monthly_cost": round(total_cost, 2),
            "free_tier_eligible": free_tier_count,
            "categories": {cat: len(resources) for cat, resources in category_groups.items()},
        },
    }


def _calculate_layout(nodes: list, edges: list):
    """Calculate node positions for the diagram."""
    # Simple layered layout based on category
    category_order = [
        ResourceType.NETWORKING.value,
        ResourceType.SECURITY.value,
        ResourceType.COMPUTE.value,
        ResourceType.STORAGE.value,
        ResourceType.DATABASE.value,
        ResourceType.LOAD_BALANCER.value,
        ResourceType.CONTAINER.value,
        ResourceType.SERVERLESS.value,
        ResourceType.DNS.value,
        ResourceType.CACHE.value,
        ResourceType.QUEUE.value,
        ResourceType.MONITORING.value,
    ]

    category_nodes = {}
    for node in nodes:
        cat = node["category"]
        if cat not in category_nodes:
            category_nodes[cat] = []
        category_nodes[cat].append(node)

    x_offset = 100
    for cat in category_order:
        if cat in category_nodes:
            y_offset = 100
            for node in category_nodes[cat]:
                node["x"] = x_offset
                node["y"] = y_offset
                node["width"] = 180
                node["height"] = 60
                y_offset += 100
            x_offset += 250


def analyze_iac(content: str, file_type: str = "terraform") -> dict:
    """Main entry point - analyze IaC content and return visualization data."""
    if file_type == "terraform":
        resources = parse_terraform_hcl(content)
    elif file_type == "cloudformation":
        resources = parse_cloudformation(content)
    else:
        return {"error": f"Unsupported file type: {file_type}"}

    diagram = generate_infra_diagram(resources)

    # Add raw resources for detailed view
    diagram["raw_resources"] = {k: v.to_dict() for k, v in resources.items()}

    return diagram


def scan_project_directory(directory: str, max_depth: int = 5) -> dict:
    """Scan a project directory for IaC files and analyze them."""
    import os

    terraform_files = []
    cloudformation_files = []
    all_resources = {}

    def scan_dir(path: str, depth: int = 0):
        if depth > max_depth:
            return
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and not entry.name.startswith('.') and entry.name not in ['node_modules', '.git', 'vendor', '__pycache__']:
                    scan_dir(entry.path, depth + 1)
                elif entry.is_file():
                    name = entry.name.lower()
                    if name.endswith('.tf'):
                        terraform_files.append(entry.path)
                    elif name.endswith('.tf.json'):
                        terraform_files.append(entry.path)
                    elif name.endswith(('.yaml', '.yml', '.json')) and 'template' in name.lower():
                        cloudformation_files.append(entry.path)
        except PermissionError:
            pass

    scan_dir(directory)

    # Parse Terraform files
    for tf_file in terraform_files:
        try:
            with open(tf_file, 'r') as f:
                content = f.read()
            resources = parse_terraform_hcl(content)
            for rid, resource in resources.items():
                resource.config['_source_file'] = tf_file
            all_resources.update(resources)
        except Exception as e:
            logger.error(f"Error parsing {tf_file}: {e}")

    # Parse CloudFormation files
    for cf_file in cloudformation_files:
        try:
            with open(cf_file, 'r') as f:
                content = f.read()
            resources = parse_cloudformation(content)
            for rid, resource in resources.items():
                resource.config['_source_file'] = cf_file
            all_resources.update(resources)
        except Exception as e:
            logger.error(f"Error parsing {cf_file}: {e}")

    diagram = generate_infra_diagram(all_resources)
    diagram['raw_resources'] = {k: v.to_dict() for k, v in all_resources.items()}
    diagram['scanned_files'] = {
        'terraform': terraform_files,
        'cloudformation': cloudformation_files,
        'total_resources': len(all_resources),
    }

    return diagram


def analyze_file(file_path: str) -> dict:
    """Analyze a single IaC file."""
    import os

    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}"}

    with open(file_path, 'r') as f:
        content = f.read()

    ext = os.path.splitext(file_path)[1].lower()
    if ext == '.tf':
        file_type = 'terraform'
    elif ext == '.tf.json':
        file_type = 'terraform'
    elif ext in ['.yaml', '.yml']:
        file_type = 'cloudformation'
    elif ext == '.json':
        file_type = 'cloudformation'
    else:
        return {"error": f"Unsupported file type: {ext}"}

    result = analyze_iac(content, file_type)
    result['file_path'] = file_path
    return result
