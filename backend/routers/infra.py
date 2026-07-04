"""Infrastructure routes — IaC parse, validate, scan-project, scan-git, AI insights."""

import asyncio
import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from main import (
    IaCParseRequest,
    ScanProjectRequest,
    _DEBUG,
    _sanitize_git_url,
    _verify_token,
    db,
)
from cloudflare_ai import (
    infra_diagram_summary,
    infra_validation_analysis,
)

router = APIRouter(prefix="")


class InfraAnalyzeRequest(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)


class InfraValidateRequest(BaseModel):
    raw_resources: dict = Field(default_factory=dict)


@router.post("/api/infra/parse")
async def parse_infrastructure(req: IaCParseRequest, user_info: dict = Depends(_verify_token)):
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    result = _infra_viz.analyze_iac(req.content, req.file_type)
    return result


@router.post("/api/infra/scan-project")
async def scan_project_directory(req: ScanProjectRequest, user_info: dict = Depends(_verify_token)):
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    directory = os.path.expanduser(req.directory)

    if not os.path.exists(directory):
        return {"error": f"Directory not found: {directory}"}
    if not os.path.isdir(directory):
        return {"error": f"Not a directory: {directory}"}

    result = _infra_viz.scan_project_directory(directory, req.max_depth)
    return result


@router.get("/api/infra/scan-git")
async def scan_git_repo(
    repo_url: str = Query(..., description="Git repository URL"),
    user_info: dict = Depends(_verify_token),
):
    try:
        import infra_visualizer as _infra_viz
        import git
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    sanitized_url = _sanitize_git_url(repo_url)

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "repo")
            git.Repo.clone_from(sanitized_url, repo_path, depth=1)
            result = _infra_viz.scan_project_directory(repo_path)
            result['repo_url'] = sanitized_url
            return result
    except git.exc.GitCommandError as e:
        return {"error": f"Failed to clone repository: {str(e)}"}
    except Exception as e:
        return {"error": f"Error scanning repository: {str(e)}"}


@router.post("/api/infra/validate")
async def validate_infrastructure(req: IaCParseRequest, user_info: dict = Depends(_verify_token)):
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    result = _infra_viz.analyze_iac(req.content, req.file_type)

    recommendations = []
    for resource in result.get("raw_resources", {}).values():
        rtype = resource.get("type", "")

        if rtype in ["aws_security_group", "azurerm_network_security_group"]:
            config = resource.get("config", {})
            if any("0.0.0.0/0" in str(v) for v in config.values()):
                recommendations.append({
                    "type": "security",
                    "severity": "high",
                    "resource": resource.get("name", ""),
                    "message": "Security group allows traffic from 0.0.0.0/0. Restrict to specific IPs.",
                })

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

        if resource.get("free_tier_eligible"):
            recommendations.append({
                "type": "free_tier",
                "severity": "info",
                "resource": resource.get("name", ""),
                "message": f"Resource is free tier eligible.",
            })

    result["recommendations"] = recommendations
    return result


@router.post("/api/infra/summarize", include_in_schema=_DEBUG)
async def infra_summarize(req: InfraAnalyzeRequest, user_info: dict = Depends(_verify_token)):
    summary = await infra_diagram_summary(req.nodes, req.edges)
    return {"summary": summary or "AI summary unavailable"}


@router.post("/api/infra/validate/ai", include_in_schema=_DEBUG)
async def infra_validate_ai(req: InfraValidateRequest, user_info: dict = Depends(_verify_token)):
    analysis = await infra_validation_analysis(req.raw_resources)
    return {"issues": analysis or []}


@router.post("/api/infra/from-scan")
async def infra_from_scan(user_info: dict = Depends(_verify_token)):
    """Convert AWS scan results to InfraVisualizer format with service connections."""
    analyses = await db.get_analyses_by_user(user_info["user_id"], limit=1)
    if not analyses:
        return {"error": "No scan results found. Run a scan first."}

    latest = analyses[0]
    result = latest.get("analysis_result")
    if not result:
        return {"error": "No analysis result available."}

    nodes = []
    edges = []
    issues = result.get("issues", [])
    raw_resources = result.get("raw_resources", {})

    # Build nodes from raw resources (preferred) or from issues
    if raw_resources:
        for rid, res in raw_resources.items():
            rtype = res.get("type", "unknown")
            cat = _service_to_category(rtype)
            nodes.append({
                "id": rid,
                "label": res.get("name", rid),
                "type": rtype,
                "category": cat,
                "color": _service_to_color(rtype),
                "config": res.get("config", {}),
                "estimated_cost": 0,
                "free_tier_eligible": False,
            })
    else:
        # Fallback: build from issues
        service_resources = {}
        for issue in issues:
            service = issue.get("service", "unknown")
            resource_name = issue.get("resource_name", issue.get("resource_id", "unknown"))
            resource_id = issue.get("resource_id", resource_name)
            if resource_id not in service_resources:
                service_resources[resource_id] = {
                    "id": resource_id,
                    "label": resource_name,
                    "type": service,
                    "category": _service_to_category(service),
                    "color": _service_to_color(service),
                    "config": {"issue_type": issue.get("issue_type", ""), "severity": issue.get("severity", ""), "explanation": issue.get("explanation", ""), "fix_command": issue.get("fix_command", ""), "region": issue.get("region", "")},
                    "estimated_cost": issue.get("potential_monthly_savings", 0),
                    "free_tier_eligible": False,
                }
        nodes = list(service_resources.values())

    # Generate edges based on common AWS relationships
    edges = _generate_aws_edges(nodes)

    # Generate suggestions from issues
    suggestions = []
    for issue in issues:
        suggestions.append({
            "type": issue.get("issue_type", "unknown"),
            "severity": issue.get("severity", "medium"),
            "resource": issue.get("resource_name", ""),
            "resource_id": issue.get("resource_id", ""),
            "message": issue.get("explanation", issue.get("message", "")),
            "explanation": issue.get("explanation", ""),
            "fix": issue.get("fix_command", ""),
        })

    # Build summary
    summary = {
        "total_resources": len(nodes),
        "total_edges": len(edges),
        "broken_connections": 0,
        "suggestions": len(suggestions),
        "high_severity": sum(1 for s in suggestions if s.get("severity") == "high"),
        "estimated_monthly_cost": sum(n.get("estimated_cost", 0) for n in nodes),
        "free_tier_eligible": sum(1 for n in nodes if n.get("free_tier_eligible")),
        "categories": {},
    }
    for node in nodes:
        cat = node.get("category", "unknown")
        summary["categories"][cat] = summary["categories"].get(cat, 0) + 1

    return {
        "nodes": nodes,
        "edges": edges,
        "broken_connections": [],
        "suggestions": suggestions,
        "summary": summary,
    }


def _service_to_category(service: str) -> str:
    """Map AWS service name to InfraVisualizer category."""
    service_lower = service.lower()
    if any(x in service_lower for x in ["ec2", "instance", "compute", "lambda", "ecs", "eks"]):
        return "compute"
    if any(x in service_lower for x in ["s3", "ebs", "volume", "storage", "efs"]):
        return "storage"
    if any(x in service_lower for x in ["rds", "dynamodb", "database", "elasticache", "redis"]):
        return "database"
    if any(x in service_lower for x in ["vpc", "subnet", "network", "elb", "alb", "load", "nat", "gateway"]):
        return "networking"
    if any(x in service_lower for x in ["security", "iam", "kms", "waf"]):
        return "security"
    if any(x in service_lower for x in ["cloudwatch", "monitoring", "logs"]):
        return "monitoring"
    return "compute"


def _service_to_color(service: str) -> str:
    """Map AWS service to color."""
    cat = _service_to_category(service)
    colors = {
        "compute": "#6366f1", "storage": "#8b5cf6", "database": "#06b6d4",
        "networking": "#10b981", "security": "#ef4444", "monitoring": "#64748b",
    }
    return colors.get(cat, "#64748b")


def _generate_aws_edges(nodes: list) -> list:
    """Generate edges between AWS resources based on common relationships."""
    edges = []
    node_ids = {n["id"] for n in nodes}
    node_types = {n["id"]: n.get("type", "").lower() for n in nodes}

    # Group by type for relationship mapping
    vpcs = [n for n in nodes if "vpc" in node_types.get(n["id"], "")]
    subnets = [n for n in nodes if "subnet" in node_types.get(n["id"], "")]
    security_groups = [n for n in nodes if "security" in node_types.get(n["id"], "")]
    instances = [n for n in nodes if any(x in node_types.get(n["id"], "") for x in ["ec2", "instance", "rds"])]
    load_balancers = [n for n in nodes if any(x in node_types.get(n["id"], "") for x in ["elb", "alb", "load"])]
    lambdas = [n for n in nodes if "lambda" in node_types.get(n["id"], "")]

    # Connect instances to VPCs (if both exist)
    for inst in instances:
        for vpc in vpcs:
            edges.append({"source": vpc["id"], "target": inst["id"], "type": "contains", "valid": True})

    # Connect instances to security groups
    for inst in instances:
        for sg in security_groups:
            edges.append({"source": sg["id"], "target": inst["id"], "type": "protects", "valid": True})

    # Connect load balancers to instances
    for lb in load_balancers:
        for inst in instances:
            edges.append({"source": lb["id"], "target": inst["id"], "type": "routes_to", "valid": True})

    # Connect lambdas to VPCs
    for lam in lambdas:
        for vpc in vpcs:
            edges.append({"source": vpc["id"], "target": lam["id"], "type": "contains", "valid": True})

    # If no specific relationships found, create a central hub pattern
    if not edges and len(nodes) > 1:
        # Use the first networking resource as hub, or first resource
        hub = None
        for n in nodes:
            if "vpc" in node_types.get(n["id"], "") or "network" in node_types.get(n["id"], ""):
                hub = n
                break
        if not hub and nodes:
            hub = nodes[0]

        if hub:
            for n in nodes:
                if n["id"] != hub["id"]:
                    edges.append({"source": hub["id"], "target": n["id"], "type": "connects_to", "valid": True})

    return edges


class PreApplyRequest(BaseModel):
    content: str = Field(..., min_length=10, max_length=200000)
    file_type: str = Field(default="terraform", pattern="^(terraform|cloudformation)$")


@router.post("/api/infra/pre-apply")
async def pre_apply_analysis(req: PreApplyRequest, user_info: dict = Depends(_verify_token)):
    """Comprehensive pre-apply analysis: parse, map connections, explain architecture, estimate costs, find issues."""
    try:
        import infra_visualizer as _infra_viz
    except ImportError:
        return {"error": "Infrastructure visualizer module not available"}

    # 1. Parse the IaC code
    parse_result = _infra_viz.analyze_iac(req.content, req.file_type)
    raw_resources = parse_result.get("raw_resources", {})
    recommendations = parse_result.get("recommendations", [])

    # 2. Build nodes from parsed resources
    nodes = []
    edges = []
    resource_map = {}  # id -> node index

    for rid, res in raw_resources.items():
        rtype = res.get("type", "unknown")
        config = res.get("config", {})
        cat = _service_to_category(rtype)

        # Extract meaningful name from config
        name = res.get("name", rid)
        if not name or name == rid:
            # Try to extract from config
            for key in ("name", "bucket", "cluster_name", "db_instance_identifier", "function_name"):
                if key in config:
                    name = str(config[key])
                    break

        node = {
            "id": rid,
            "label": name,
            "type": rtype,
            "category": cat,
            "color": _service_to_color(rtype),
            "config": config,
            "estimated_cost": 0,
            "free_tier_eligible": False,
        }
        resource_map[rid] = len(nodes)
        nodes.append(node)

    # 3. Extract connections from Terraform references
    for rid, res in raw_resources.items():
        config = res.get("config", {})
        connections = res.get("connections", [])

        for conn in connections:
            if not conn or conn.startswith("var.") or conn.startswith("local.") or conn.startswith("module.") or conn.startswith("data."):
                continue

            # Try to find matching resource
            target_id = None
            for other_id in raw_resources:
                if other_id != rid and (other_id.endswith(f".{conn}") or other_id == conn):
                    target_id = other_id
                    break

            if target_id and target_id in resource_map:
                edges.append({
                    "source": rid,
                    "target": target_id,
                    "type": _guess_connection_type(raw_resources[rid].get("type", ""), raw_resources[target_id].get("type", "")),
                    "valid": True,
                })

    # 4. Also extract connections from config values that reference other resources
    for rid, res in raw_resources.items():
        config = res.get("config", {})
        for key, val in config.items():
            if isinstance(val, str) and val.startswith("aws_") and "." in val:
                # Looks like a Terraform reference
                parts = val.split(".")
                if len(parts) >= 2:
                    ref_type = parts[0]
                    ref_name = parts[1] if len(parts) > 1 else ""
                    for other_id, other_res in raw_resources.items():
                        if other_id != rid and other_res.get("type", "").startswith(ref_type) and ref_name in other_id:
                            edges.append({
                                "source": rid,
                                "target": other_id,
                                "type": _guess_connection_type(res.get("type", ""), other_res.get("type", "")),
                                "valid": True,
                            })

    # 5. Build suggestions from recommendations
    suggestions = []
    for rec in recommendations:
        suggestions.append({
            "type": rec.get("type", "info"),
            "severity": rec.get("severity", "medium"),
            "resource": rec.get("resource", ""),
            "resource_id": rec.get("resource", ""),
            "message": rec.get("message", ""),
            "explanation": rec.get("message", ""),
            "fix": "",
        })

    # 6. Generate architecture explanation
    categories = {}
    for node in nodes:
        cat = node.get("category", "unknown")
        categories[cat] = categories.get(cat, 0) + 1

    architecture_summary = _generate_architecture_summary(nodes, edges, categories, req.file_type)

    # 7. Build cost estimate (placeholder — real estimation needs pricing data)
    total_cost = 0
    for node in nodes:
        node["estimated_cost"] = _estimate_node_cost(node)
        total_cost += node["estimated_cost"]

    # 8. Build final result
    summary = {
        "total_resources": len(nodes),
        "total_edges": len(edges),
        "broken_connections": 0,
        "suggestions": len(suggestions),
        "high_severity": sum(1 for s in suggestions if s.get("severity") == "high"),
        "estimated_monthly_cost": round(total_cost, 2),
        "free_tier_eligible": sum(1 for n in nodes if n.get("free_tier_eligible")),
        "categories": categories,
    }

    return {
        "nodes": nodes,
        "edges": edges,
        "broken_connections": [],
        "suggestions": suggestions,
        "summary": summary,
        "architecture_summary": architecture_summary,
        "resource_count_by_type": {rtype: sum(1 for n in nodes if n["type"] == rtype) for rtype in set(n["type"] for n in nodes)},
    }


def _guess_connection_type(source_type: str, target_type: str) -> str:
    """Guess the connection type between two resources."""
    s = source_type.lower()
    t = target_type.lower()

    if "security_group" in s and ("instance" in t or "rds" in t or "lambda" in t):
        return "protects"
    if "vpc" in s and ("subnet" in t or "instance" in t or "rds" in t):
        return "contains"
    if "subnet" in s and ("instance" in t or "rds" in t or "lambda" in t):
        return "hosts"
    if "load_balancer" in s or "alb" in s or "elb" in s:
        return "routes_to"
    if "instance" in s and ("ebs" in t or "volume" in t):
        return "attaches"
    if "nat_gateway" in s or "internet_gateway" in s:
        return "connects"
    if "route_table" in s:
        return "routes"
    return "depends_on"


def _estimate_node_cost(node: dict) -> float:
    """Estimate monthly cost for a resource node."""
    rtype = node.get("type", "").lower()
    config = node.get("config", {})

    # EC2 instances
    if "instance" in rtype:
        itype = config.get("instance_type", "t3.micro")
        pricing = {
            "t3.micro": 7.59, "t3.small": 15.18, "t3.medium": 30.37,
            "t3.large": 60.74, "t3.xlarge": 121.48, "t3.2xlarge": 242.96,
            "m5.large": 69.12, "m5.xlarge": 138.24, "m5.2xlarge": 276.48,
            "m5.4xlarge": 552.96, "m5.8xlarge": 1105.92,
        }
        return pricing.get(itype, 30.0)

    # RDS instances
    if "rds" in rtype or "db_instance" in rtype:
        db_class = config.get("instance_class", "db.t3.micro")
        pricing = {
            "db.t3.micro": 12.41, "db.t3.small": 24.82, "db.t3.medium": 49.64,
            "db.t3.large": 99.28, "db.r5.large": 172.80, "db.r5.xlarge": 345.60,
        }
        return pricing.get(db_class, 50.0)

    # EKS clusters
    if "eks_cluster" in rtype:
        return 73.0  # $0.10/hr

    # NAT Gateways
    if "nat_gateway" in rtype:
        return 45.0  # $0.045/hr + data processing

    # Load Balancers
    if "load_balancer" in rtype or "alb" in rtype:
        return 22.0  # ~$16-22/month

    # S3 buckets
    if "s3" in rtype or "bucket" in rtype:
        return 5.0  # Estimate

    # Lambda
    if "lambda" in rtype:
        return 10.0  # Estimate

    # ElastiCache
    if "elasticache" in rtype or "redis" in rtype:
        return 50.0

    # DynamoDB
    if "dynamodb" in rtype:
        return 25.0

    # CloudWatch
    if "cloudwatch" in rtype:
        return 3.0

    # SQS/SNS
    if "sqs" in rtype or "sns" in rtype:
        return 1.0

    return 0


def _generate_architecture_summary(nodes: list, edges: list, categories: dict, file_type: str) -> str:
    """Generate a plain-English summary of the infrastructure architecture."""
    parts = []

    # Count by category
    compute = categories.get("compute", 0)
    storage = categories.get("storage", 0)
    database = categories.get("database", 0)
    networking = categories.get("networking", 0)
    security = categories.get("security", 0)
    container = categories.get("container", 0)
    serverless = categories.get("serverless", 0)

    if file_type == "terraform":
        parts.append("This Terraform configuration defines")
    else:
        parts.append("This CloudFormation template defines")

    resource_parts = []
    if compute: resource_parts.append(f"{compute} compute resource{'s' if compute > 1 else ''}")
    if storage: resource_parts.append(f"{storage} storage resource{'s' if storage > 1 else ''}")
    if database: resource_parts.append(f"{database} database{'s' if database > 1 else ''}")
    if networking: resource_parts.append(f"{networking} networking component{'s' if networking > 1 else ''}")
    if security: resource_parts.append(f"{security} security group{'s' if security > 1 else ''}")
    if container: resource_parts.append(f"{container} container resource{'s' if container > 1 else ''}")
    if serverless: resource_parts.append(f"{serverless} serverless function{'s' if serverless > 1 else ''}")

    if resource_parts:
        parts.append(" and ".join(resource_parts) + ".")

    if edges:
        parts.append(f"\n\nResources are connected through {len(edges)} relationship{'s' if len(edges) > 1 else ''}:")

        # Group edges by type
        edge_types = {}
        for e in edges:
            et = e.get("type", "depends_on")
            edge_types[et] = edge_types.get(et, 0) + 1

        for et, count in edge_types.items():
            parts.append(f"  - {et.replace('_', ' ').title()}: {count} connection{'s' if count > 1 else ''}")

    if not edges:
        parts.append("\n\nResources are independent — no explicit connections between them.")

    return "\n".join(parts)
