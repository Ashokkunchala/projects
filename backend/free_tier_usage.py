"""
Real-time free tier usage tracking.
Calculates actual resource usage against free tier limits during cloud scans.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════════
#  FREE TIER LIMITS (reference values)
# ════════════════════════════════════════════════════════════════════════════════

AWS_FREE_TIER_LIMITS = {
    "ec2": {"type": "12-month", "hours": 750, "instance_types": ["t2.micro", "t3.micro"]},
    "lambda": {"type": "always-free", "requests": 1_000_000, "gb_seconds": 400_000},
    "s3": {"type": "12-month", "storage_gb": 5, "get_requests": 20_000, "put_requests": 2_000},
    "rds": {"type": "12-month", "hours": 750, "storage_gb": 20, "instance_types": ["db.t2.micro", "db.t3.micro"]},
    "dynamodb": {"type": "always-free", "storage_gb": 25, "rcu": 25, "wcu": 25},
    "cloudwatch": {"type": "always-free", "log_ingestion_gb": 5, "metrics": 10, "alarms": 10},
    "sqs": {"type": "always-free", "requests": 1_000_000},
    "sns": {"type": "always-free", "deliveries": 1_000_000},
    "cloudfront": {"type": "always-free", "transfer_tb": 1, "requests": 10_000_000},
    "elasticache": {"type": "12-month", "hours": 750, "instance_types": ["cache.t2.micro"]},
    "efs": {"type": "12-month", "storage_gb": 5},
    "ebs": {"type": "12-month", "storage_gb": 30},
    "route53": {"type": "always-free", "hosted_zones": 50},
    "kinesis": {"type": "12-month", "shard_hours": 750},
    "glue": {"type": "12-month", "objects": 1_000_000},
    "athena": {"type": "always-free", "tb_scanned": 1},
    "ecr": {"type": "always-free", "storage_gb": 0.5},
}

AZURE_FREE_TIER_LIMITS = {
    "virtual_machines": {"type": "12-month", "hours": 750, "instance_types": ["B1s", "B1ms"]},
    "functions": {"type": "always-free", "executions": 1_000_000, "gb_seconds": 400_000},
    "blob_storage": {"type": "12-month", "storage_gb": 5},
    "cosmos_db": {"type": "always-free", "ru_s": 1000, "storage_gb": 25},
    "sql_database": {"type": "12-month", "dtu_hours": 250_000},
    "redis_cache": {"type": "12-month", "hours": 750},
}

GCP_FREE_TIER_LIMITS = {
    "compute_engine": {"type": "always-free", "hours": 744, "instance_types": ["f1-micro", "g1-small"]},
    "cloud_functions": {"type": "always-free", "invocations": 2_000_000, "gb_seconds": 400_000},
    "cloud_storage": {"type": "always-free", "storage_gb": 5},
    "firestore": {"type": "always-free", "storage_gb": 1, "reads": 50_000, "writes": 20_000},
    "cloud_run": {"type": "always-free", "requests": 2_000_000, "gb_seconds": 360_000},
}


def calculate_aws_usage(resources: dict) -> dict:
    """Calculate AWS resource usage against free tier limits."""
    usage = {
        "ec2": {"used": 0, "limit": 750, "unit": "hours", "type": "12-month", "details": []},
        "lambda": {"used": 0, "limit": 1_000_000, "unit": "requests", "type": "always-free", "details": []},
        "s3": {"used": 0, "limit": 5, "unit": "GB", "type": "12-month", "details": []},
        "rds": {"used": 0, "limit": 750, "unit": "hours", "type": "12-month", "details": []},
        "dynamodb": {"used": 0, "limit": 25, "unit": "GB", "type": "always-free", "details": []},
        "ebs": {"used": 0, "limit": 30, "unit": "GB", "type": "12-month", "details": []},
        "elasticache": {"used": 0, "limit": 750, "unit": "hours", "type": "12-month", "details": []},
        "cloudfront": {"used": 0, "limit": 1024, "unit": "GB", "type": "always-free", "details": []},
        "sqs": {"used": 0, "limit": 1_000_000, "unit": "requests", "type": "always-free", "details": []},
        "sns": {"used": 0, "limit": 1_000_000, "unit": "deliveries", "type": "always-free", "details": []},
        "route53": {"used": 0, "limit": 50, "unit": "zones", "type": "always-free", "details": []},
        "kinesis": {"used": 0, "limit": 750, "unit": "shard-hours", "type": "12-month", "details": []},
        "glue": {"used": 0, "limit": 1_000_000, "unit": "objects", "type": "12-month", "details": []},
        "athena": {"used": 0, "limit": 1024, "unit": "GB scanned", "type": "always-free", "details": []},
        "ecr": {"used": 0, "limit": 0.5, "unit": "GB", "type": "always-free", "details": []},
    }

    # EC2 instances
    for r in resources.get("ec2", []):
        if r.get("type") == "EC2Instance":
            itype = r.get("instance_type", "")
            state = r.get("state", "running")
            region = r.get("region", "")
            name = r.get("name", r.get("id", ""))
            usage["ec2"]["used"] += 730 if state == "running" else 0
            usage["ec2"]["details"].append({
                "name": name,
                "type": itype,
                "state": state,
                "region": region,
                "is_free_tier": itype in ["t2.micro", "t3.micro"],
                "estimated_hours": 730 if state == "running" else 0,
            })

    # EBS volumes
    for r in resources.get("ec2", []):
        if r.get("type") == "EBSVolume":
            size = r.get("size_gb", 0)
            vtype = r.get("volume_type", "")
            usage["ebs"]["used"] += size
            usage["ebs"]["details"].append({
                "name": r.get("name", r.get("id", "")),
                "size_gb": size,
                "type": vtype,
                "is_free_tier": vtype in ["gp2", "gp3"],
            })

    # Lambda functions
    for r in resources.get("lambda", []):
        usage["lambda"]["used"] += 100_000  # estimate
        usage["lambda"]["details"].append({
            "name": r.get("name", ""),
            "runtime": r.get("runtime", ""),
            "memory": r.get("memory_size", 128),
        })

    # S3 buckets
    for r in resources.get("s3", []):
        usage["s3"]["used"] += 5  # estimate per bucket
        usage["s3"]["details"].append({
            "name": r.get("name", ""),
            "has_lifecycle": r.get("has_lifecycle_policy", False),
        })

    # RDS instances
    for r in resources.get("rds", []):
        if r.get("type") == "RDSInstance":
            usage["rds"]["used"] += 730  # estimate 1 month running
            usage["rds"]["details"].append({
                "name": r.get("name", ""),
                "instance_class": r.get("instance_class", ""),
                "engine": r.get("engine", ""),
                "is_free_tier": r.get("instance_class", "") in ["db.t2.micro", "db.t3.micro"],
            })

    # ElastiCache
    for r in resources.get("elasticache", []):
        usage["elasticache"]["used"] += 730
        usage["elasticache"]["details"].append({
            "name": r.get("name", ""),
            "node_type": r.get("cache_node_type", ""),
            "is_free_tier": r.get("cache_node_type", "") in ["cache.t2.micro"],
        })

    # DynamoDB
    for r in resources.get("dynamodb", []):
        size_bytes = r.get("size_bytes", 0)
        size_gb = size_bytes / (1024 ** 3) if size_bytes else 0
        usage["dynamodb"]["used"] += size_gb
        usage["dynamodb"]["details"].append({
            "name": r.get("name", ""),
            "size_gb": round(size_gb, 2),
            "billing_mode": r.get("billing_mode", ""),
        })

    # Route53
    for r in resources.get("route53", []):
        usage["route53"]["used"] += 1
        usage["route53"]["details"].append({
            "name": r.get("name", ""),
            "record_count": r.get("record_count", 0),
        })

    # Calculate percentages and status
    for service, data in usage.items():
        if data["limit"] > 0:
            data["percentage"] = round((data["used"] / data["limit"]) * 100, 1)
            data["remaining"] = max(0, data["limit"] - data["used"])
            data["status"] = "ok" if data["percentage"] < 80 else "warning" if data["percentage"] < 100 else "exceeded"
        else:
            data["percentage"] = 0
            data["remaining"] = 0
            data["status"] = "ok"

    return usage


def calculate_azure_usage(resources: dict) -> dict:
    """Calculate Azure resource usage against free tier limits."""
    usage = {
        "virtual_machines": {"used": 0, "limit": 750, "unit": "hours", "type": "12-month", "details": []},
        "functions": {"used": 0, "limit": 1_000_000, "unit": "executions", "type": "always-free", "details": []},
        "blob_storage": {"used": 0, "limit": 5, "unit": "GB", "type": "12-month", "details": []},
        "cosmos_db": {"used": 0, "limit": 1000, "unit": "RU/s", "type": "always-free", "details": []},
        "redis_cache": {"used": 0, "limit": 750, "unit": "hours", "type": "12-month", "details": []},
    }

    for r in resources.get("virtual_machines", []):
        state = r.get("power_state", "")
        usage["virtual_machines"]["used"] += 730 if state == "running" else 0
        usage["virtual_machines"]["details"].append({
            "name": r.get("name", ""),
            "size": r.get("vm_size", ""),
            "state": state,
        })

    for r in resources.get("storage_accounts", []):
        usage["blob_storage"]["used"] += 2  # estimate
        usage["blob_storage"]["details"].append({
            "name": r.get("name", ""),
        })

    for r in resources.get("cosmos_db", []):
        usage["cosmos_db"]["used"] += 400
        usage["cosmos_db"]["details"].append({
            "name": r.get("name", ""),
        })

    for r in resources.get("azure_redis", []):
        usage["redis_cache"]["used"] += 730
        usage["redis_cache"]["details"].append({
            "name": r.get("name", ""),
            "sku": r.get("sku", ""),
        })

    for service, data in usage.items():
        if data["limit"] > 0:
            data["percentage"] = round((data["used"] / data["limit"]) * 100, 1)
            data["remaining"] = max(0, data["limit"] - data["used"])
            data["status"] = "ok" if data["percentage"] < 80 else "warning" if data["percentage"] < 100 else "exceeded"
        else:
            data["percentage"] = 0
            data["remaining"] = 0
            data["status"] = "ok"

    return usage


def calculate_gcp_usage(resources: dict) -> dict:
    """Calculate GCP resource usage against free tier limits."""
    usage = {
        "compute_engine": {"used": 0, "limit": 744, "unit": "hours", "type": "always-free", "details": []},
        "cloud_functions": {"used": 0, "limit": 2_000_000, "unit": "invocations", "type": "always-free", "details": []},
        "cloud_storage": {"used": 0, "limit": 5, "unit": "GB", "type": "always-free", "details": []},
        "firestore": {"used": 0, "limit": 1, "unit": "GB", "type": "always-free", "details": []},
        "cloud_run": {"used": 0, "limit": 2_000_000, "unit": "requests", "type": "always-free", "details": []},
    }

    for r in resources.get("compute_engine", []):
        state = r.get("status", "")
        usage["compute_engine"]["used"] += 730 if state == "RUNNING" else 0
        usage["compute_engine"]["details"].append({
            "name": r.get("name", ""),
            "machine_type": r.get("machine_type", ""),
            "status": state,
            "is_free_tier": "f1-micro" in r.get("machine_type", "") or "g1-small" in r.get("machine_type", ""),
        })

    for r in resources.get("storage_buckets", []):
        usage["cloud_storage"]["used"] += 2
        usage["cloud_storage"]["details"].append({
            "name": r.get("name", ""),
        })

    for r in resources.get("cloud_sql", []):
        usage["firestore"]["used"] += 0.5
        usage["firestore"]["details"].append({
            "name": r.get("name", ""),
        })

    for service, data in usage.items():
        if data["limit"] > 0:
            data["percentage"] = round((data["used"] / data["limit"]) * 100, 1)
            data["remaining"] = max(0, data["limit"] - data["used"])
            data["status"] = "ok" if data["percentage"] < 80 else "warning" if data["percentage"] < 100 else "exceeded"
        else:
            data["percentage"] = 0
            data["remaining"] = 0
            data["status"] = "ok"

    return usage


def get_free_tier_usage(provider: str, resources: dict) -> dict:
    """Get free tier usage for a provider based on scanned resources."""
    if provider == "aws":
        usage = calculate_aws_usage(resources)
    elif provider == "azure":
        usage = calculate_azure_usage(resources)
    elif provider == "gcp":
        usage = calculate_gcp_usage(resources)
    else:
        return {"error": f"Unsupported provider: {provider}"}

    # Calculate summary
    total_services = len(usage)
    within_limit = sum(1 for v in usage.values() if v["status"] == "ok")
    warning = sum(1 for v in usage.values() if v["status"] == "warning")
    exceeded = sum(1 for v in usage.values() if v["status"] == "exceeded")

    return {
        "provider": provider,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_services": total_services,
            "within_limit": within_limit,
            "warning": warning,
            "exceeded": exceeded,
            "health_score": round((within_limit / total_services * 100) if total_services > 0 else 100, 1),
        },
        "services": usage,
    }
