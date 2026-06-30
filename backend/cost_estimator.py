"""Cost estimation engine — calculates projected costs, suggestions, and alternatives."""

import json as _json
import logging
import uuid
from typing import Optional

# Import resource map for provider detection
from iac_parser import _AWS_RESOURCE_MAP

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════════
# AWS Pricing (us-east-1 on-demand, approximate)
# ═══════════════════════════════════════════════════════════════════════════════

_EC2 = {
    "t3.nano":      {"h": 0.0052, "m": 3.79,  "v": 2, "mem": "0.5 GiB"},
    "t3.micro":     {"h": 0.0104, "m": 7.59,  "v": 2, "mem": "1 GiB"},
    "t3.small":     {"h": 0.0208, "m": 15.18, "v": 2, "mem": "2 GiB"},
    "t3.medium":    {"h": 0.0416, "m": 30.37, "v": 2, "mem": "4 GiB"},
    "t3.large":     {"h": 0.0832, "m": 60.74, "v": 2, "mem": "8 GiB"},
    "t3.xlarge":    {"h": 0.1664, "m": 121.47, "v": 4, "mem": "16 GiB"},
    "t3.2xlarge":   {"h": 0.3328, "m": 242.94, "v": 8, "mem": "32 GiB"},
    "t4g.nano":     {"h": 0.0042, "m": 3.07,  "v": 2, "mem": "0.5 GiB"},
    "t4g.micro":    {"h": 0.0084, "m": 6.13,  "v": 2, "mem": "1 GiB"},
    "t4g.small":    {"h": 0.0168, "m": 12.26, "v": 2, "mem": "2 GiB"},
    "t4g.medium":   {"h": 0.0336, "m": 24.53, "v": 2, "mem": "4 GiB"},
    "t4g.large":    {"h": 0.0672, "m": 49.06, "v": 2, "mem": "8 GiB"},
    "t4g.xlarge":   {"h": 0.1344, "m": 98.11, "v": 4, "mem": "16 GiB"},
    "t4g.2xlarge":  {"h": 0.2688, "m": 196.22, "v": 8, "mem": "32 GiB"},
    "m5.large":     {"h": 0.096,  "m": 70.08, "v": 2, "mem": "8 GiB"},
    "m5.xlarge":    {"h": 0.192,  "m": 140.16, "v": 4, "mem": "16 GiB"},
    "m5.2xlarge":   {"h": 0.384,  "m": 280.32, "v": 8, "mem": "32 GiB"},
    "m5.4xlarge":   {"h": 0.768,  "m": 560.64, "v": 16, "mem": "64 GiB"},
    "m5.8xlarge":   {"h": 1.536,  "m": 1121.28, "v": 32, "mem": "128 GiB"},
    "m6g.large":    {"h": 0.077,  "m": 56.21, "v": 2, "mem": "8 GiB"},
    "m6g.xlarge":   {"h": 0.154,  "m": 112.42, "v": 4, "mem": "16 GiB"},
    "m6g.2xlarge":  {"h": 0.308,  "m": 224.84, "v": 8, "mem": "32 GiB"},
    "m6g.4xlarge":  {"h": 0.616,  "m": 449.68, "v": 16, "mem": "64 GiB"},
    "m6i.large":    {"h": 0.096,  "m": 70.08, "v": 2, "mem": "8 GiB"},
    "m6i.xlarge":   {"h": 0.192,  "m": 140.16, "v": 4, "mem": "16 GiB"},
    "m6i.2xlarge":  {"h": 0.384,  "m": 280.32, "v": 8, "mem": "32 GiB"},
    "m7g.large":    {"h": 0.0816, "m": 59.57, "v": 2, "mem": "8 GiB"},
    "m7g.xlarge":   {"h": 0.1632, "m": 119.14, "v": 4, "mem": "16 GiB"},
    "c5.large":     {"h": 0.085,  "m": 62.05, "v": 2, "mem": "4 GiB"},
    "c5.xlarge":    {"h": 0.17,   "m": 124.1, "v": 4, "mem": "8 GiB"},
    "c5.2xlarge":   {"h": 0.34,   "m": 248.2, "v": 8, "mem": "16 GiB"},
    "c5.4xlarge":   {"h": 0.68,   "m": 496.4, "v": 16, "mem": "32 GiB"},
    "c6g.large":    {"h": 0.068,  "m": 49.64, "v": 2, "mem": "4 GiB"},
    "c6g.xlarge":   {"h": 0.136,  "m": 99.28, "v": 4, "mem": "8 GiB"},
    "c6g.2xlarge":  {"h": 0.272,  "m": 198.56, "v": 8, "mem": "16 GiB"},
    "c7g.large":    {"h": 0.0732, "m": 53.44, "v": 2, "mem": "4 GiB"},
    "c7g.xlarge":   {"h": 0.1464, "m": 106.87, "v": 4, "mem": "8 GiB"},
    "r5.large":     {"h": 0.126,  "m": 91.98, "v": 2, "mem": "16 GiB"},
    "r5.xlarge":    {"h": 0.252,  "m": 183.96, "v": 4, "mem": "32 GiB"},
    "r5.2xlarge":   {"h": 0.504,  "m": 367.92, "v": 8, "mem": "64 GiB"},
    "r5.4xlarge":   {"h": 1.008,  "m": 735.84, "v": 16, "mem": "128 GiB"},
    "r6g.large":    {"h": 0.1008, "m": 73.58, "v": 2, "mem": "16 GiB"},
    "r6g.xlarge":   {"h": 0.2016, "m": 147.17, "v": 4, "mem": "32 GiB"},
    "r6g.2xlarge":  {"h": 0.4032, "m": 294.34, "v": 8, "mem": "64 GiB"},
    "r7g.large":    {"h": 0.1074, "m": 78.40, "v": 2, "mem": "16 GiB"},
    "r7g.xlarge":   {"h": 0.2148, "m": 156.80, "v": 4, "mem": "32 GiB"},
    # GPU
    "p3.2xlarge":   {"h": 3.06,   "m": 2233.8, "v": 8, "mem": "61 GiB"},
    "p3.8xlarge":   {"h": 12.24,  "m": 8935.2, "v": 32, "mem": "244 GiB"},
    "p4d.24xlarge": {"h": 32.77,  "m": 23922.1, "v": 96, "mem": "1152 GiB"},
    "g4dn.xlarge":  {"h": 0.526,  "m": 383.98, "v": 4, "mem": "16 GiB"},
    "g4dn.2xlarge": {"h": 0.752,  "m": 548.96, "v": 8, "mem": "32 GiB"},
    "g5.xlarge":    {"h": 1.006,  "m": 734.38, "v": 4, "mem": "16 GiB"},
    "g5.2xlarge":   {"h": 1.212,  "m": 884.76, "v": 8, "mem": "32 GiB"},
    "inf1.xlarge":  {"h": 0.368,  "m": 268.64, "v": 4, "mem": "8 GiB"},
    "inf2.xlarge":  {"h": 0.448,  "m": 327.04, "v": 4, "mem": "16 GiB"},
}

_EBS = {
    "gp3":        {"gb": 0.08, "iops": 0.005, "thrpt": 0.04},
    "gp2":        {"gb": 0.10, "iops": 0, "thrpt": 0},
    "io1":        {"gb": 0.125, "iops": 0.065, "thrpt": 0},
    "io2":        {"gb": 0.125, "iops": 0.065, "thrpt": 0},
    "st1":        {"gb": 0.045, "iops": 0, "thrpt": 0},
    "sc1":        {"gb": 0.025, "iops": 0, "thrpt": 0},
    "standard":   {"gb": 0.05, "iops": 0, "thrpt": 0},
}

_RDS = {
    "db.t3.micro":      {"h": 0.017, "m": 12.41},
    "db.t3.small":      {"h": 0.034, "m": 24.82},
    "db.t3.medium":     {"h": 0.068, "m": 49.64},
    "db.t3.large":      {"h": 0.136, "m": 99.28},
    "db.r5.large":      {"h": 0.24,  "m": 175.2},
    "db.r5.xlarge":     {"h": 0.48,  "m": 350.4},
    "db.r5.2xlarge":    {"h": 0.96,  "m": 700.8},
    "db.r5.4xlarge":    {"h": 1.92,  "m": 1401.6},
    "db.m5.large":      {"h": 0.155, "m": 113.15},
    "db.m5.xlarge":     {"h": 0.31,  "m": 226.3},
    "db.m5.2xlarge":    {"h": 0.62,  "m": 452.6},
    "db.m6g.large":     {"h": 0.134, "m": 97.82},
    "db.m6g.xlarge":    {"h": 0.268, "m": 195.64},
    "db.r6g.large":     {"h": 0.202, "m": 147.46},
    "db.r6g.xlarge":    {"h": 0.404, "m": 294.92},
}

_S3 = {
    "standard":        {"gb": 0.023, "put": 0.000005, "get": 0.0000004},
    "intelligent":     {"gb": 0.023, "put": 0.000005, "get": 0.0000004},
    "standard_ia":     {"gb": 0.0125, "put": 0.00001, "get": 0.000001},
    "onezone_ia":      {"gb": 0.01, "put": 0.00001, "get": 0.000001},
    "glacier":         {"gb": 0.0036, "put": 0.00003, "restore": 0.01},
    "glacier_deep":    {"gb": 0.00099, "put": 0.00005, "restore": 0.02},
}

_LAMBDA = {"req": 0.0000002, "gbs": 0.0000166667, "free_req": 1_000_000, "free_gbs": 400_000}

_ELB = {"alb": 22.76, "nlb": 20.27, "clb": 19.38}

_EKS = {"standard": 73.0, "enterprise": 146.0}

_ECS_FARGATE = {"vcpu_h": 0.04048, "gb_h": 0.004445}

_NAT = {"gw_h": 0.045, "gw_m": 32.4, "data_gb": 0.045}

_NAT_INSTANCE = {"m": 15.0, "note": "NAT instances (e.g. t3.medium) cost ~$15-30/mo for compute, cheaper than NAT Gateway at $32.40/mo + data processing"}

_ELASTICACHE = {
    "cache.t3.micro": {"h": 0.017, "m": 12.41},
    "cache.t3.small": {"h": 0.034, "m": 24.82},
    "cache.t3.medium": {"h": 0.068, "m": 49.64},
    "cache.r5.large": {"h": 0.145, "m": 105.85},
    "cache.r5.xlarge": {"h": 0.29, "m": 211.7},
    "cache.r6g.large": {"h": 0.116, "m": 84.68},
    "cache.r6g.xlarge": {"h": 0.232, "m": 169.36},
}

_KMS = {"key_m": 1.0, "req_per_10k": 0.03}

_CW_LOGS = {"ingest_gb": 0.50, "storage_gb": 0.03, "data_scanned_gb": 0.005}

_ECR = {"storage_gb": 0.10}

_DYNAMODB = {
    "on_demand_read_per_million": 1.25,
    "on_demand_write_per_million": 1.25,
    "provisioned_read_hour": 0.00013,
    "provisioned_write_hour": 0.00065,
    "storage_gb": 0.25,
}

_OPENSEARCH = {
    "t3.small.search": {"h": 0.036, "m": 26.28},
    "t3.medium.search": {"h": 0.073, "m": 53.29},
    "m5.large.search": {"h": 0.125, "m": 91.25},
    "m5.xlarge.search": {"h": 0.25, "m": 182.5},
    "m5.2xlarge.search": {"h": 0.50, "m": 365.0},
}

_MSK = {
    "kafka.t3.small": {"h": 0.072, "m": 52.56, "storage": 0.08},
    "kafka.m5.large": {"h": 0.21, "m": 153.3, "storage": 0.08},
    "kafka.m5.xlarge": {"h": 0.42, "m": 306.6, "storage": 0.08},
}

_ELASTIC_IP = {"m": 3.60}

_VPC_ENDPOINT = {"h": 0.01, "m": 7.30, "data_gb": 0.01}

_TGW = {"attachment_h": 0.05, "attachment_m": 36.50, "data_gb": 0.02}

_DX = {"1gbps_m": 162.0, "10gbps_m": 1620.0}

_GLOBAL_ACCELERATOR = {"h": 0.025, "m": 18.25, "data_gb": 0.0225}

_WAF = {"acl_m": 5.0, "rule_m": 1.0, "req_per_million": 0.60}

_NETWORK_FIREWALL = {"h": 0.395, "m": 288.35, "data_gb": 0.065}

_SHIELD = {"m": 3000.0}

_ACM_PCA = {"ca_m": 400.0}

_CFRONT = {"data_transfer_gb": 0.085}

_AZURE_VM = {
    "Standard_B1s": {"h": 0.0076, "m": 5.55, "v": 1, "mem": "1 GiB"},
    "Standard_B1ms": {"h": 0.0152, "m": 11.10, "v": 1, "mem": "2 GiB"},
    "Standard_B2s": {"h": 0.0304, "m": 22.19, "v": 2, "mem": "4 GiB"},
    "Standard_B2ms": {"h": 0.0608, "m": 44.38, "v": 2, "mem": "8 GiB"},
    "Standard_D2s_v3": {"h": 0.096, "m": 70.08, "v": 2, "mem": "8 GiB"},
    "Standard_D4s_v3": {"h": 0.192, "m": 140.16, "v": 4, "mem": "16 GiB"},
    "Standard_D8s_v3": {"h": 0.384, "m": 280.32, "v": 8, "mem": "32 GiB"},
    "Standard_E2s_v3": {"h": 0.126, "m": 91.98, "v": 2, "mem": "16 GiB"},
    "Standard_E4s_v3": {"h": 0.252, "m": 183.96, "v": 4, "mem": "32 GiB"},
    "Standard_E8s_v3": {"h": 0.504, "m": 367.92, "v": 8, "mem": "64 GiB"},
}

_AZURE_DISK = {"Standard_LRS": 0.05, "StandardSSD_LRS": 0.08, "Premium_LRS": 0.125, "UltraSSD_LRS": 0.16}

_GCE = {
    "n1-standard-1": {"h": 0.0475, "m": 34.68},
    "n1-standard-2": {"h": 0.095, "m": 69.35},
    "n1-standard-4": {"h": 0.19, "m": 138.7},
    "n1-standard-8": {"h": 0.38, "m": 277.4},
    "n2-standard-2": {"h": 0.085, "m": 62.05},
    "n2-standard-4": {"h": 0.17, "m": 124.1},
    "n2-standard-8": {"h": 0.34, "m": 248.2},
    "e2-micro": {"h": 0.0076, "m": 5.55},
    "e2-small": {"h": 0.0151, "m": 11.02},
    "e2-medium": {"h": 0.0302, "m": 22.05},
    "e2-standard-2": {"h": 0.067, "m": 48.91},
    "e2-standard-4": {"h": 0.134, "m": 97.82},
    "c2-standard-4": {"h": 0.148, "m": 108.04},
    "g2-standard-4": {"h": 0.526, "m": 383.98},
}

_GCE_DISK = {"pd-standard": 0.04, "pd-balanced": 0.065, "pd-ssd": 0.17}

_GKE = {"cluster_fee_h": 0.10, "cluster_m": 73.0}

# ─── Helper functions ───────────────────────────────────────────────────────

def _get_cfg(config: dict, key: str, default=None):
    val = config.get(key, default)
    if isinstance(val, str):
        val = val.strip('"').strip("'")
    return val


def _int_cfg(config: dict, key: str, default: int = 0) -> int:
    val = _get_cfg(config, key, default)
    try:
        return int(float(str(val)))
    except (ValueError, TypeError):
        return default


def _float_cfg(config: dict, key: str, default: float = 0) -> float:
    val = _get_cfg(config, key, default)
    try:
        return float(str(val))
    except (ValueError, TypeError):
        return default


def _find_instance_type(config: dict, key: str = "instance_type") -> Optional[str]:
    raw = _get_cfg(config, key, "")
    if not raw:
        return None
    return str(raw).lower()


def _find_inst_type_rds(config: dict) -> Optional[str]:
    for key in ("instance_class", "instance_type", "db_instance_class"):
        val = _get_cfg(config, key)
        if val:
            return val.lower()
    return None


# ─── AWS Estimators ─────────────────────────────────────────────────────────

def _est_aws_instance(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    rtype = res.get("type", "")
    inst_type = _find_instance_type(config)
    count = _int_cfg(config, "desired_count", 1) or 1

    # For launch template / autoscaling — free resource, cost is in the ASG instances
    if rtype in ("aws_launch_template", "aws_launch_configuration"):
        return _free_resource(name, rtype)
    if rtype == "aws_autoscaling_group":
        min_size = _int_cfg(config, "min_size", 1)
        max_size = _int_cfg(config, "max_size", min_size)
        desired = _int_cfg(config, "desired_capacity", min_size)
        return {"resource_name": name, "resource_type": rtype, "monthly_cost": 0, "hourly_cost": 0,
                "details": f"Auto Scaling Group ({desired}-{max_size} instances)", "breakdown": {},
                "note": "Cost depends on EC2 instances in the ASG. Each instance is estimated separately."}

    if rtype == "aws_spot_instance_request":
        inst_type = _find_instance_type(config, "instance_type") or inst_type
        if inst_type and inst_type in _EC2:
            p = _EC2[inst_type]
            # Spot is typically 60-90% cheaper
            spot_m = p["m"] * 0.3
            return {"resource_name": name, "resource_type": rtype, "instance_type": inst_type,
                    "monthly_cost": round(spot_m, 2), "hourly_cost": p["h"] * 0.3,
                    "details": f"{inst_type} (spot, ~70% off)", "breakdown": {f"EC2 Spot {inst_type}": spot_m},
                    "is_spot": True}

    if not inst_type or inst_type not in _EC2:
        return {"resource_name": name, "resource_type": rtype, "instance_type": inst_type or "unknown",
                "monthly_cost": 50.0, "hourly_cost": 50 / 730,
                "details": f"{inst_type or 'Unknown type'} (estimated at $50/mo)", "breakdown": {"EC2 (estimated)": 50},
                "estimate_note": True}
    p = _EC2[inst_type]
    monthly = p["m"] * count
    return {"resource_name": name, "resource_type": rtype, "instance_type": inst_type,
            "count": count if count > 1 else None,
            "monthly_cost": round(monthly, 2), "hourly_cost": p["h"] * count,
            "details": f"{inst_type} ({p['v']} vCPU, {p['mem']})" + (f" x{count}" if count > 1 else ""),
            "breakdown": {f"EC2 {inst_type}" + (f" x{count}" if count > 1 else ""): monthly}}


def _est_ebs(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    vol_type = _get_cfg(config, "type", "gp3").lower()
    size = _int_cfg(config, "size", 100) or 100
    p = _EBS.get(vol_type, _EBS["gp3"])
    monthly = size * p["gb"]
    return {"resource_name": name, "resource_type": "aws_ebs_volume", "volume_type": vol_type,
            "size_gb": size, "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{vol_type} {size}GB", "breakdown": {f"EBS {vol_type} ({size}GB)": monthly}}


def _est_nat_gw(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    data_gb = _int_cfg(config, "data_processing_gb", 100)
    monthly = _NAT["gw_m"] + data_gb * _NAT["data_gb"]
    return {"resource_name": name, "resource_type": "aws_nat_gateway",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"NAT Gateway + ~{data_gb}GB/mo data", "breakdown": {"NAT Gateway": _NAT["gw_m"],
                         "NAT data": data_gb * _NAT["data_gb"]}}


def _est_rds(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    inst_type = _find_inst_type_rds(config)
    storage = _int_cfg(config, "allocated_storage", 100) or 100
    multi_az = str(_get_cfg(config, "multi_az", "false")).lower() == "true"
    if inst_type and inst_type in _RDS:
        p = _RDS[inst_type]
        storage_cost = storage * _EBS["gp3"]["gb"]
        monthly = p["m"] + storage_cost
        if multi_az:
            monthly *= 2
        details = f"{inst_type} + {storage}GB" + (" (Multi-AZ)" if multi_az else "")
        return {"resource_name": name, "resource_type": "aws_db_instance",
                "instance_type": inst_type, "storage_gb": storage, "multi_az": multi_az,
                "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
                "details": details, "breakdown": {f"RDS {inst_type}": p["m"] if not multi_az else p["m"] * 2,
                                                   f"Storage": storage_cost}}
    monthly = 100.0
    return {"resource_name": name, "resource_type": "aws_db_instance",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "RDS (estimated)", "breakdown": {"RDS (estimated)": monthly}, "estimate_note": True}


def _est_s3(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    storage = _int_cfg(config, "storage_gb", 50) or 50
    monthly = storage * _S3["standard"]["gb"]
    return {"resource_name": name, "resource_type": "aws_s3_bucket",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"S3 ~{storage}GB", "breakdown": {f"S3 Standard ({storage}GB)": monthly},
            "estimate_note": True}


def _est_lambda(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    memory = _int_cfg(config, "memory_size", 128) or 128
    memory_gb = memory / 1024
    timeout = _int_cfg(config, "timeout", 3) or 3
    requests = _int_cfg(config.get("_estimated", {}), "monthly_requests", 100000)
    avg_duration = _int_cfg(config.get("_estimated", {}), "avg_duration_ms", timeout * 1000 / 2)
    gb_seconds = (requests * avg_duration / 1000) * memory_gb
    compute = max(0, gb_seconds - _LAMBDA["free_gbs"]) * _LAMBDA["gbs"]
    req_cost = max(0, requests - _LAMBDA["free_req"]) * _LAMBDA["req"]
    monthly = compute + req_cost
    return {"resource_name": name, "resource_type": "aws_lambda_function",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{memory}MB, ~{requests:,} req/mo", "breakdown": {"Lambda compute": compute, "Lambda req": req_cost},
            "estimate_note": True}


def _est_eks_cluster(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    tier = str(_get_cfg(config, "tier", "standard")).lower()
    monthly = _EKS.get(tier, _EKS["standard"])
    return {"resource_name": name, "resource_type": "aws_eks_cluster",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"EKS {tier} tier control plane", "breakdown": {f"EKS {tier.title()}": monthly}}


def _est_eks_node_group(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    inst_type = _find_instance_type(config) or _get_cfg(config, "instance_types", "t3.medium").strip('"[]" ')
    scaling = _int_cfg(config, "desired_size", _int_cfg(config, "scaling_config.0.desired_size", 2))
    count = max(scaling, 1)

    if inst_type in _EC2:
        p = _EC2[inst_type]
        instance_cost = p["m"] * count
        eks_overhead = count * 2.0  # ~$2/mo per node for add-ons
        monthly = instance_cost + eks_overhead
        return {"resource_name": name, "resource_type": "aws_eks_node_group",
                "instance_type": inst_type, "count": count,
                "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
                "details": f"{count}x {inst_type} + EKS add-ons",
                "breakdown": {f"EC2 {inst_type} x{count}": instance_cost, "EKS add-on overhead": eks_overhead}}
    monthly = count * 50.0
    return {"resource_name": name, "resource_type": "aws_eks_node_group",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{count}x node (estimated)", "breakdown": {"EKS nodes (est.)": monthly}, "estimate_note": True}


def _est_ecs_service(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    tasks = _int_cfg(config, "desired_count", 1) or 1
    cpu = _float_cfg(config, "cpu", 0.25) or 0.25
    mem_mb = _int_cfg(config, "memory", 512) or 512
    mem_gb = mem_mb / 1024
    vcpu_cost = cpu * _ECS_FARGATE["vcpu_h"] * 730 * tasks
    mem_cost = mem_gb * _ECS_FARGATE["gb_h"] * 730 * tasks
    monthly = vcpu_cost + mem_cost
    return {"resource_name": name, "resource_type": "aws_ecs_service",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"Fargate {cpu}vCPU {mem_gb}GB x{tasks}", "breakdown": {"Fargate vCPU": vcpu_cost, "Fargate mem": mem_cost}}


def _est_elasticache(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    for key in ("node_type", "instance_type", "cache_node_type"):
        nt = _get_cfg(config, key)
        if nt:
            break
    else:
        nt = "cache.t3.micro"
    nt = nt.lower()
    num_nodes = _int_cfg(config, "num_cache_nodes", _int_cfg(config, "num_node_groups", 1)) or 1
    if nt in _ELASTICACHE:
        p = _ELASTICACHE[nt]
        monthly = p["m"] * num_nodes
        return {"resource_name": name, "resource_type": "aws_elasticache_cluster",
                "instance_type": nt, "count": num_nodes,
                "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
                "details": f"{nt} x{num_nodes}", "breakdown": {f"ElastiCache {nt}": p["m"] * num_nodes}}
    monthly = num_nodes * 50.0
    return {"resource_name": name, "resource_type": "aws_elasticache_cluster",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"ElastiCache (est.)", "breakdown": {"ElastiCache (est.)": monthly}, "estimate_note": True}


def _est_eip(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "aws_eip",
            "monthly_cost": _ELASTIC_IP["m"], "hourly_cost": _ELASTIC_IP["m"] / 730,
            "details": "Elastic IP (unassociated = $3.60/mo)", "breakdown": {"Elastic IP": _ELASTIC_IP["m"]}}


def _est_elb(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    rtype = res.get("type", "")
    if "nlb" in rtype.lower() or "network" in rtype.lower():
        monthly = _ELB["nlb"]
        lb_type = "NLB"
    elif "classic" in rtype.lower() or rtype == "aws_elb":
        monthly = _ELB["clb"]
        lb_type = "CLB"
    else:
        monthly = _ELB["alb"]
        lb_type = "ALB"
    return {"resource_name": name, "resource_type": rtype,
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{lb_type} (~${monthly:.0f}/mo)", "breakdown": {f"{lb_type}": monthly}}


def _est_kms(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = _KMS["key_m"]
    return {"resource_name": name, "resource_type": "aws_kms_key",
            "monthly_cost": monthly, "hourly_cost": monthly / 730,
            "details": "KMS key ($1/key/mo)", "breakdown": {"KMS key": monthly}}


def _est_cw_logs(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    retention = _int_cfg(config, "retention_in_days", 0)
    ingest = _int_cfg(config.get("_estimated", {}), "monthly_ingest_gb", 5)
    storage = _int_cfg(config.get("_estimated", {}), "storage_gb", ingest * 30)
    ingest_cost = ingest * _CW_LOGS["ingest_gb"]
    storage_cost = storage * _CW_LOGS["storage_gb"]
    monthly = ingest_cost + storage_cost
    return {"resource_name": name, "resource_type": "aws_cloudwatch_log_group",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"~{ingest}GB/mo ingested" + (f", {retention}d retention" if retention else ""),
            "breakdown": {"CW Logs ingest": ingest_cost, "CW Logs storage": storage_cost}, "estimate_note": True}


def _est_ecr(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    storage = _int_cfg(config.get("_estimated", {}), "storage_gb", 5)
    monthly = storage * _ECR["storage_gb"]
    return {"resource_name": name, "resource_type": "aws_ecr_repository",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"~{storage}GB storage", "breakdown": {f"ECR storage": monthly}, "estimate_note": True}


def _est_dynamodb(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    billing = str(_get_cfg(config, "billing_mode", "PAY_PER_REQUEST")).lower()
    storage = _int_cfg(config.get("_estimated", {}), "storage_gb", 10)
    read_capacity = _int_cfg(config, "read_capacity", 5)
    write_capacity = _int_cfg(config, "write_capacity", 5)
    if "provisioned" in billing:
        read_cost = read_capacity * _DYNAMODB["provisioned_read_hour"] * 730
        write_cost = write_capacity * _DYNAMODB["provisioned_write_hour"] * 730
        monthly = read_cost + write_cost + storage * _DYNAMODB["storage_gb"]
    else:
        monthly = storage * _DYNAMODB["storage_gb"] + 5.0
    return {"resource_name": name, "resource_type": "aws_dynamodb_table",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": billing.replace("_", " ").title(), "breakdown": {"DynamoDB": monthly}, "estimate_note": True}


def _est_vpc_endpoint(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = _VPC_ENDPOINT["m"]
    return {"resource_name": name, "resource_type": "aws_vpc_endpoint",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "VPC Endpoint (~$7.30/mo)", "breakdown": {"VPC Endpoint": monthly}}


def _est_tgw(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    attachments = _int_cfg(config.get("_estimated", {}), "attachments", 2)
    monthly = _TGW["attachment_m"] * attachments
    return {"resource_name": name, "resource_type": "aws_ec2_transit_gateway",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"TGW + ~{attachments} attachments", "breakdown": {"Transit Gateway": monthly}}


def _est_waf(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = _WAF["acl_m"] + _WAF["rule_m"] * 3
    return {"resource_name": name, "resource_type": "aws_wafv2_web_acl",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"WAF ACL + 3 rules (~${_WAF['acl_m'] + _WAF['rule_m'] * 3:.0f}/mo)",
            "breakdown": {"WAF ACL": _WAF["acl_m"], "WAF rules": _WAF["rule_m"] * 3}}


def _est_network_firewall(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = _NETWORK_FIREWALL["m"]
    return {"resource_name": name, "resource_type": "aws_networkfirewall_firewall",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"Network Firewall (~${_NETWORK_FIREWALL['m']:.0f}/mo)",
            "breakdown": {"Network Firewall": monthly}}


def _est_msk(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    broker = str(_get_cfg(config, "broker_node_type", "kafka.t3.small")).lower()
    brokers = _int_cfg(config, "number_of_broker_nodes", 3) or 3
    storage = _int_cfg(config, "ebs_volume_size", 100) or 100
    if broker in _MSK:
        p = _MSK[broker]
        monthly = p["m"] * brokers + storage * _MSK["kafka.t3.small"]["storage"] * brokers
        return {"resource_name": name, "resource_type": "aws_msk_cluster",
                "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
                "details": f"{broker} x{brokers}, {storage}GB", "breakdown": {f"MSK {broker}": p["m"] * brokers, "MSK storage": storage * 0.08 * brokers}}
    monthly = brokers * 100.0
    return {"resource_name": name, "resource_type": "aws_msk_cluster",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"MSK (est.)", "breakdown": {"MSK (est.)": monthly}, "estimate_note": True}


def _est_opensearch(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    inst_type = str(_get_cfg(config, "instance_type", "t3.small.search")).lower()
    nodes = _int_cfg(config, "instance_count", 1) or 1
    storage = _int_cfg(config, "ebs_options.0.volume_size", _int_cfg(config, "volume_size", 100)) or 100
    if inst_type in _OPENSEARCH:
        p = _OPENSEARCH[inst_type]
        monthly = p["m"] * nodes + storage * 0.08
        return {"resource_name": name, "resource_type": "aws_opensearch_domain",
                "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
                "details": f"{inst_type} x{nodes}, {storage}GB", "breakdown": {f"OpenSearch {inst_type}": p["m"] * nodes, "Storage": storage * 0.08}}
    monthly = nodes * 50.0
    return {"resource_name": name, "resource_type": "aws_opensearch_domain",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "OpenSearch (est.)", "breakdown": {"OpenSearch (est.)": monthly}, "estimate_note": True}


def _est_sqs(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "aws_sqs_queue",
            "monthly_cost": 0, "hourly_cost": 0,
            "details": "SQS (free under 1M requests/mo)", "breakdown": {}}


def _est_sns(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "aws_sns_topic",
            "monthly_cost": 0, "hourly_cost": 0,
            "details": "SNS (free under 1M deliveries/mo)", "breakdown": {}}


def _est_route53(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    n_records = _int_cfg(config.get("_estimated", {}), "records", 10)
    monthly = 0.50  # first 25 hosted zones free, then $0.50/zone/mo
    return {"resource_name": name, "resource_type": "aws_route53_zone",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "Route 53 zone ($0.50/mo)", "breakdown": {"Route 53": monthly}}


def _est_shield(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "aws_shield_protection",
            "monthly_cost": _SHIELD["m"], "hourly_cost": _SHIELD["m"] / 730,
            "details": "Shield Advanced ($3,000/mo)", "breakdown": {"Shield Advanced": _SHIELD["m"]}}


def _est_dx(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    bandwidth = str(_get_cfg(config, "bandwidth", "1Gbps")).lower()
    if "10" in bandwidth:
        monthly = _DX["10gbps_m"]
    else:
        monthly = _DX["1gbps_m"]
    return {"resource_name": name, "resource_type": "aws_dx_connection",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"Direct Connect {bandwidth}", "breakdown": {f"DX {bandwidth}": monthly}}


def _est_global_accel(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = _GLOBAL_ACCELERATOR["m"]
    return {"resource_name": name, "resource_type": "aws_globalaccelerator_accelerator",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "Global Accelerator (~$18/mo)", "breakdown": {"Global Accelerator": monthly}}


def _est_acm_pca(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "aws_acmpca_certificate_authority",
            "monthly_cost": _ACM_PCA["ca_m"], "hourly_cost": _ACM_PCA["ca_m"] / 730,
            "details": "ACM Private CA ($400/mo)", "breakdown": {"ACM Private CA": _ACM_PCA["ca_m"]},
            "estimate_note": True}


_AWS_ESTIMATORS = {
    "aws_instance": _est_aws_instance,
    "aws_spot_instance_request": _est_aws_instance,
    "aws_ebs_volume": _est_ebs,
    "aws_nat_gateway": _est_nat_gw,
    "aws_eip": _est_eip,
    "aws_db_instance": _est_rds,
    "aws_rds_cluster_instance": _est_rds,
    "aws_s3_bucket": _est_s3,
    "aws_lambda_function": _est_lambda,
    "aws_eks_cluster": _est_eks_cluster,
    "aws_eks_node_group": _est_eks_node_group,
    "aws_ecs_service": _est_ecs_service,
    "aws_elasticache_cluster": _est_elasticache,
    "aws_elasticache_replication_group": _est_elasticache,
    "aws_lb": _est_elb,
    "aws_alb": _est_elb,
    "aws_elb": _est_elb,
    "aws_lb_target_group": _est_elb,
    "aws_kms_key": _est_kms,
    "aws_cloudwatch_log_group": _est_cw_logs,
    "aws_ecr_repository": _est_ecr,
    "aws_dynamodb_table": _est_dynamodb,
    "aws_vpc_endpoint": _est_vpc_endpoint,
    "aws_ec2_transit_gateway": _est_tgw,
    "aws_wafv2_web_acl": _est_waf,
    "aws_networkfirewall_firewall": _est_network_firewall,
    "aws_msk_cluster": _est_msk,
    "aws_opensearch_domain": _est_opensearch,
    "aws_elasticsearch_domain": _est_opensearch,
    "aws_sqs_queue": _est_sqs,
    "aws_sns_topic": _est_sns,
    "aws_route53_zone": _est_route53,
    "aws_shield_protection": _est_shield,
    "aws_dx_connection": _est_dx,
    "aws_globalaccelerator_accelerator": _est_global_accel,
    "aws_acmpca_certificate_authority": _est_acm_pca,
    "aws_autoscaling_group": _est_aws_instance,
    "aws_launch_template": lambda r: _free_resource(r["name"], r["type"]),
    "aws_launch_configuration": lambda r: _free_resource(r["name"], r["type"]),
}

# ─── Azure Estimators ───────────────────────────────────────────────────────

def _est_azure_vm(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    vm_size = str(_get_cfg(config, "size", "Standard_B1s")).lower()
    count = _int_cfg(config, "count", 1) or 1
    for pattern in (vm_size, f"Standard_{vm_size}", f"standard_{vm_size}"):
        for key in _AZURE_VM:
            if key.lower() == pattern.lower() or key.lower().endswith(vm_size.lower()):
                p = _AZURE_VM[key]
                monthly = p["m"] * count
                return {"resource_name": name, "resource_type": res["type"], "instance_type": key,
                        "monthly_cost": round(monthly, 2), "hourly_cost": p["h"] * count,
                        "details": f"{key} ({p['v']} vCPU, {p['mem']}) x{count}" if count > 1 else f"{key} ({p['v']} vCPU, {p['mem']})",
                        "breakdown": {f"VM {key}": monthly}}
    monthly = count * 50.0
    return {"resource_name": name, "resource_type": res["type"],
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"VM (estimated)", "breakdown": {"VM (est.)": monthly}, "estimate_note": True}


def _est_azure_disk(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    sku = str(_get_cfg(config, "storage_account_type", _get_cfg(config, "sku", "StandardSSD_LRS")))
    size = _int_cfg(config, "disk_size_gb", 128) or 128
    price = _AZURE_DISK.get(sku, _AZURE_DISK.get(f"Standard_{sku}", _AZURE_DISK["StandardSSD_LRS"]))
    monthly = size * price
    return {"resource_name": name, "resource_type": res["type"],
            "volume_type": sku, "size_gb": size,
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{sku} {size}GB", "breakdown": {f"Azure Disk {sku}": monthly}}


def _est_azure_aks(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    monthly = 73.0
    return {"resource_name": name, "resource_type": "azurerm_kubernetes_cluster",
            "monthly_cost": monthly, "hourly_cost": monthly / 730,
            "details": "AKS control plane ($73/mo)", "breakdown": {"AKS": monthly}}


def _est_azure_storage(res: dict) -> Optional[dict]:
    name = res.get("name", "unknown")
    return {"resource_name": name, "resource_type": "azurerm_storage_account",
            "monthly_cost": 5.0, "hourly_cost": 5 / 730,
            "details": "Storage account (est.)", "breakdown": {"Storage account": 5}, "estimate_note": True}


def _est_azure_lb(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    sku = str(_get_cfg(config, "sku", "Standard")).lower()
    monthly = 22.0 if "standard" in sku else 15.0
    return {"resource_name": name, "resource_type": res["type"],
            "monthly_cost": monthly, "hourly_cost": monthly / 730,
            "details": f"Azure LB ({sku})", "breakdown": {f"Azure LB ({sku})": monthly}}


_AZURE_ESTIMATORS = {
    "azurerm_virtual_machine": _est_azure_vm,
    "azurerm_linux_virtual_machine": _est_azure_vm,
    "azurerm_windows_virtual_machine": _est_azure_vm,
    "azurerm_managed_disk": _est_azure_disk,
    "azurerm_kubernetes_cluster": _est_azure_aks,
    "azurerm_kubernetes_cluster_node_pool": _est_azure_vm,
    "azurerm_storage_account": _est_azure_storage,
    "azurerm_lb": _est_azure_lb,
    "azurerm_public_ip": lambda r: {"resource_name": r["name"], "resource_type": r["type"],
                                      "monthly_cost": 3.60, "hourly_cost": 3.60 / 730,
                                      "details": "Public IP", "breakdown": {"Public IP": 3.60}},
}

# ─── GCP Estimators ─────────────────────────────────────────────────────────

def _est_gce_instance(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    mt = str(_get_cfg(config, "machine_type", "e2-medium"))
    count = _int_cfg(config, "count", 1) or 1
    for pattern in (mt, f"zones/{mt}", f"projects/.../machineTypes/{mt}"):
        mt_clean = pattern.split("/")[-1]
        if mt_clean in _GCE:
            p = _GCE[mt_clean]
            monthly = p["m"] * count
            return {"resource_name": name, "resource_type": "google_compute_instance",
                    "instance_type": mt_clean, "monthly_cost": round(monthly, 2),
                    "hourly_cost": monthly / 730, "details": f"{mt_clean} x{count}" if count > 1 else mt_clean,
                    "breakdown": {f"GCE {mt_clean}": monthly}}
    monthly = count * 50.0
    return {"resource_name": name, "resource_type": "google_compute_instance",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "GCE (est.)", "breakdown": {"GCE (est.)": monthly}, "estimate_note": True}


def _est_gce_disk(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    dt = str(_get_cfg(config, "type", "pd-standard"))
    size = _int_cfg(config, "size", 100) or 100
    price = _GCE_DISK.get(dt, 0.04)
    monthly = size * price
    return {"resource_name": name, "resource_type": "google_compute_disk",
            "volume_type": dt, "size_gb": size,
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": f"{dt} {size}GB", "breakdown": {f"GCE Disk {dt}": monthly}}


def _est_gke(res: dict) -> Optional[dict]:
    config = res.get("config", {})
    name = res.get("name", "unknown")
    monthly = _GKE["cluster_m"]
    return {"resource_name": name, "resource_type": "google_container_cluster",
            "monthly_cost": round(monthly, 2), "hourly_cost": monthly / 730,
            "details": "GKE cluster fee ($73/mo)", "breakdown": {"GKE": monthly}}


_GCP_ESTIMATORS = {
    "google_compute_instance": _est_gce_instance,
    "google_compute_disk": _est_gce_disk,
    "google_container_cluster": _est_gke,
    "google_container_node_pool": _est_gce_instance,
}

# ─── Free Tier Limits ────────────────────────────────────────────────────────
# AWS Free Tier (12-month offer + always-free services)
# These are the standard limits; actual limits may vary by account age and region.

_FREE_TIER_INFO = {
    "ec2": {
        "name": "EC2",
        "type": "12-month",
        "limits": {
            "hours": 750,
            "instance_type": "t2.micro / t3.micro (Linux)",
        },
        "description": "750 hours/month of t2.micro or t3.micro Linux instances",
        "annual_limit": "9,000 hours",
    },
    "lambda": {
        "name": "Lambda",
        "type": "always-free",
        "limits": {
            "requests": 1_000_000,
            "gb_seconds": 400_000,
        },
        "description": "1M requests + 400,000 GB-seconds/month",
        "annual_limit": "12M requests, 4.8M GB-seconds",
    },
    "s3": {
        "name": "S3",
        "type": "12-month",
        "limits": {
            "storage_gb": 5,
            "get_requests": 20000,
            "put_requests": 2000,
        },
        "description": "5 GB Standard storage, 20K GET / 2K PUT requests",
        "annual_limit": "60 GB-months, 240K GET / 24K PUT",
    },
    "dynamodb": {
        "name": "DynamoDB",
        "type": "always-free",
        "limits": {
            "storage_gb": 25,
            "rcu": 25,
            "wcu": 25,
        },
        "description": "25 GB storage + 25 RCU + 25 WCU",
        "annual_limit": "25 GB storage (no annual reset)",
    },
    "rds": {
        "name": "RDS",
        "type": "12-month",
        "limits": {
            "hours": 750,
            "instance_type": "db.t2.micro / db.t3.micro",
            "storage_gb": 20,
        },
        "description": "750 hours/month of db.t2.micro (MySQL, PostgreSQL, MariaDB) + 20 GB storage",
        "annual_limit": "9,000 hours, 240 GB-months storage",
    },
    "cloudwatch": {
        "name": "CloudWatch",
        "type": "always-free",
        "limits": {
            "log_ingestion_gb": 5,
            "metrics": 10,
            "alarms": 10,
        },
        "description": "5 GB log ingestion, 10 metrics, 10 alarms",
        "annual_limit": "60 GB log ingestion",
    },
    "sqs": {
        "name": "SQS",
        "type": "always-free",
        "limits": {
            "requests": 1_000_000,
        },
        "description": "1M requests/month",
        "annual_limit": "12M requests",
    },
    "sns": {
        "name": "SNS",
        "type": "always-free",
        "limits": {
            "deliveries": 1_000_000,
        },
        "description": "1M deliveries/month",
        "annual_limit": "12M deliveries",
    },
    "ecr": {
        "name": "ECR",
        "type": "always-free",
        "limits": {
            "storage_gb": 0.5,
        },
        "description": "500 MB storage",
        "annual_limit": "6 GB-months",
    },
    "elb": {
        "name": "Elastic Load Balancing",
        "type": "12-month",
        "limits": {
            "hours": 750,
        },
        "description": "750 hours/month of Classic/ALB/NLB",
        "annual_limit": "9,000 hours",
    },
    "api_gateway": {
        "name": "API Gateway",
        "type": "12-month",
        "limits": {
            "calls": 1_000_000,
        },
        "description": "1M API calls/month",
        "annual_limit": "12M calls",
    },
    "cloudfront": {
        "name": "CloudFront",
        "type": "always-free",
        "limits": {
            "transfer_tb": 1,
            "requests": 10_000_000,
        },
        "description": "1 TB transfer + 10M requests/month",
        "annual_limit": "12 TB, 120M requests",
    },
    "ses": {
        "name": "SES",
        "type": "always-free",
        "limits": {
            "emails": 62000,
        },
        "description": "62,000 emails/month (from EC2)",
        "annual_limit": "744,000 emails",
    },
    "step_functions": {
        "name": "Step Functions",
        "type": "12-month",
        "limits": {
            "transitions": 4000,
        },
        "description": "4,000 state transitions/month",
        "annual_limit": "48,000 transitions",
    },
    "kinesis": {
        "name": "Kinesis",
        "type": "12-month",
        "limits": {
            "shard_hours": 750,
        },
        "description": "1 shard * 750 hours/month",
        "annual_limit": "9,000 shard-hours",
    },
    "glue": {
        "name": "Glue",
        "type": "12-month",
        "limits": {
            "objects": 1_000_000,
        },
        "description": "1M objects/month",
        "annual_limit": "12M objects",
    },
    "shield": {
        "name": "Shield Advanced",
        "type": "always-free",
        "limits": {"included": "Always free (basic)"},
        "description": "AWS Shield Basic is always included at no cost",
        "annual_limit": "Always free",
    },
    "waf": {
        "name": "WAF",
        "type": "12-month",
        "limits": {"rules": 5},
        "description": "5 web ACL rules (free under free tier)",
        "annual_limit": "5 rule-months",
    },
}


def _check_free_tier_eligibility(resource_estimates: list[dict]) -> dict:
    """Analyze which resources fit within AWS free tier limits."""
    usage = {
        "ec2_instances": 0,
        "lambda_requests": 0,
        "lambda_gb_seconds": 0,
        "s3_buckets": 0,
        "s3_total_gb": 0,
        "dynamodb_tables": 0,
        "rds_instances": 0,
        "elb_count": 0,
        "ecr_repos": 0,
        "sqs_queues": 0,
        "sns_topics": 0,
        "log_groups": 0,
    }

    for r in resource_estimates:
        rt = r.get("resource_type", "")
        if rt == "aws_lambda_function":
            usage["lambda_requests"] += 1_000_000  # assume 1M requests per function
            usage["lambda_gb_seconds"] += 400_000  # assume 400K GB-s per function
        elif rt == "aws_instance":
            usage["ec2_instances"] += 1
        elif rt == "aws_s3_bucket":
            usage["s3_buckets"] += 1
            usage["s3_total_gb"] += 5  # assume 5 GB per bucket
        elif rt == "aws_dynamodb_table":
            usage["dynamodb_tables"] += 1
        elif rt in ("aws_db_instance", "aws_rds_cluster_instance"):
            usage["rds_instances"] += 1
        elif rt in ("aws_lb", "aws_alb", "aws_elb"):
            usage["elb_count"] += 1
        elif rt == "aws_ecr_repository":
            usage["ecr_repos"] += 1
        elif rt == "aws_sqs_queue":
            usage["sqs_queues"] += 1
        elif rt == "aws_sns_topic":
            usage["sns_topics"] += 1
        elif rt == "aws_cloudwatch_log_group":
            usage["log_groups"] += 1

    within_limits = True
    details = []

    if usage["ec2_instances"] > 1:
        within_limits = False
        details.append(f"EC2: {usage['ec2_instances']} instance(s) — free tier covers 1 t2.micro/t3.micro")

    if usage["rds_instances"] > 1:
        within_limits = False
        details.append(f"RDS: {usage['rds_instances']} instance(s) — free tier covers 1 db.t2.micro")

    return {
        "within_limits": within_limits,
        "usage_summary": usage,
        "details": details,
        "note": "Free tier estimates assume minimal usage. Actual costs depend on usage patterns, "
                "data transfer, and whether the account is still within the 12-month free tier period.",
    }


# ─── Free resource handler ───────────────────────────────────────────────────

_FREE_RESOURCES = {
    "aws_iam_role", "aws_iam_role_policy", "aws_iam_policy",
    "aws_iam_role_policy_attachment", "aws_iam_user", "aws_iam_group",
    "aws_iam_instance_profile", "aws_iam_openid_connect_provider",
    "aws_security_group", "aws_security_group_rule",
    "aws_network_interface", "aws_subnet", "aws_vpc",
    "aws_internet_gateway", "aws_route_table", "aws_route",
    "aws_default_vpc", "aws_default_subnet", "aws_default_security_group",
    "aws_ec2_tag", "aws_placement_group", "aws_ecs_task_definition",
    "aws_lambda_permission", "aws_lambda_layer_version",
    "aws_api_gateway_stage", "aws_apigatewayv2_stage",
    "aws_lb_listener", "aws_lb_listener_rule",
    "aws_db_subnet_group", "aws_db_parameter_group",
    "aws_elasticache_subnet_group", "aws_redshift_subnet_group",
    "aws_sns_topic_subscription", "aws_eventbridge_rule",
    "aws_kms_alias", "aws_secretsmanager_secret_version",
    "aws_acm_certificate_validation", "aws_cloudwatch_log_stream",
    "aws_cloudwatch_dashboard", "aws_guardduty_filter",
    "aws_ecr_replication_configuration",
    "aws_eks_addon", "aws_eks_identity_provider_config",
    "aws_lambda_event_source_mapping",
    "aws_transfer_user", "aws_backup_plan",
    "aws_codebuild_report_group", "aws_codedeploy_app",
    "aws_ec2_transit_gateway_vpc_attachment",
    "aws_wafv2_rule_group", "aws_networkfirewall_firewall_policy",
    "aws_msk_configuration", "aws_db_event_subscription",
    "aws_service_discovery_service", "aws_resourcegroups_group",
    "aws_s3_bucket_object",
    "time_sleep", "time_offset", "null_resource",
    "random_id", "random_password", "random_string",
    "tls_private_key", "local_file", "terraform_data",
    "aws_route53_record",
    # Azure free
    "azurerm_resource_group", "azurerm_virtual_network", "azurerm_subnet",
    "azurerm_network_security_group", "azurerm_network_interface",
    "azurerm_role_assignment", "azurerm_user_assigned_identity",
    "azurerm_storage_container", "azurerm_storage_blob",
    "azurerm_mssql_server", "azurerm_key_vault_secret",
    "azurerm_service_bus_queue", "azurerm_service_bus_topic",
    "azurerm_eventhub",
    # GCP free
    "google_compute_firewall", "google_compute_network",
    "google_compute_subnetwork", "google_compute_router",
    "google_service_account", "google_project_iam_member",
    "google_project_service", "google_kms_key_ring",
    "google_storage_bucket_object",
    "google_pubsub_subscription", "google_bigquery_table",
    "google_sql_database",
    # CloudFormation free
    "AWS::IAM::Role", "AWS::IAM::Policy", "AWS::EC2::SecurityGroup",
    "AWS::ECS::TaskDefinition", "AWS::AutoScaling::LaunchConfiguration",
}


def _free_resource(name: str, rtype: str) -> dict:
    return {"resource_name": name, "resource_type": rtype,
            "monthly_cost": 0, "hourly_cost": 0,
            "details": "Free resource — no direct cost", "breakdown": {},
            "_free": True}


# ─── Suggestions Engine ─────────────────────────────────────────────────────

def _gen_suggestions(resource: dict, estimate: dict) -> list[dict]:
    suggestions = []
    rtype = resource.get("type", "")
    config = resource.get("config", {})
    mcost = estimate.get("monthly_cost", 0)
    if mcost <= 0:
        return []

    # ── NAT Gateway → NAT Instance ─────────────────────────────────────────
    if rtype == "aws_nat_gateway":
        suggestions.append({
            "type": "nat_instance",
            "title": "Replace NAT Gateway with NAT Instance",
            "description": f"NAT Gateway costs ${_NAT['gw_m']:.2f}/mo fixed, plus data processing. A NAT instance (t3.medium ~$30/mo) can reduce costs by 50%+.",
            "potential_savings": round(mcost - _NAT_INSTANCE["m"], 2),
            "impact": "medium",
            "effort": "medium",
            "action": "Replace `aws_nat_gateway` with a NAT instance using `aws_instance` with Amazon Linux NAT AMI",
        })
        suggestions.append({
            "type": "nat_multi_az",
            "title": "Consolidate NAT Gateways",
            "description": "Each AZ has a NAT Gateway at $32.40/mo + data. Consider a single NATGW or NAT instance for dev/staging.",
            "potential_savings": round(mcost * 0.3, 2),
            "impact": "high",
            "effort": "medium",
            "action": "For dev/staging: use 1 NAT Gateway in 1 AZ instead of 1 per AZ",
        })

    # ── EIP ─────────────────────────────────────────────────────────────────
    if rtype == "aws_eip":
        suggestions.append({
            "type": "eip_unassociated",
            "title": "Release or Associate Unused Elastic IPs",
            "description": "Unassociated EIPs cost $3.60/mo each. Associate to an instance or release.",
            "potential_savings": mcost,
            "impact": "high",
            "effort": "low",
            "action": "Associate the EIP to an EC2 instance or NAT Gateway, or remove the `aws_eip` resource",
        })

    # ── EC2 Instance ────────────────────────────────────────────────────────
    inst_type = estimate.get("instance_type", "")
    if rtype in ("aws_instance",) and inst_type:
        # Graviton
        if inst_type.startswith("t3."):
            g = inst_type.replace("t3.", "t4g.")
            if g in _EC2:
                savings = _EC2[inst_type]["m"] - _EC2[g]["m"]
                if savings > 0:
                    suggestions.append({
                        "type": "graviton", "title": f"Switch to {g} (Graviton/Arm)",
                        "description": f"Graviton t4g instances are {int(savings/_EC2[inst_type]['m']*100)}% cheaper than t3.",
                        "potential_savings": round(savings, 2), "impact": "low", "effort": "low",
                        "action": f"Change `instance_type` to \"{g}\"",
                    })
        elif inst_type.startswith("m5."):
            g = inst_type.replace("m5.", "m6g.")
            if g in _EC2:
                savings = _EC2[inst_type]["m"] - _EC2[g]["m"]
                if savings > 0:
                    suggestions.append({
                        "type": "graviton", "title": f"Switch to {g} (Graviton/Arm)",
                        "description": f"M6g Graviton instances are ~{int(savings/_EC2[inst_type]['m']*100)}% cheaper.",
                        "potential_savings": round(savings, 2), "impact": "low", "effort": "low",
                        "action": f"Change `instance_type` to \"{g}\"",
                    })
        elif inst_type.startswith("c5."):
            g = inst_type.replace("c5.", "c6g.")
            if g in _EC2:
                savings = _EC2[inst_type]["m"] - _EC2[g]["m"]
                if savings > 0:
                    suggestions.append({
                        "type": "graviton", "title": f"Switch to {g} (Graviton/Arm)",
                        "description": f"C6g instances are ~{int(savings/_EC2[inst_type]['m']*100)}% cheaper than C5.",
                        "potential_savings": round(savings, 2), "impact": "low", "effort": "low",
                        "action": f"Change `instance_type` to \"{g}\"",
                    })
        elif inst_type.startswith("r5."):
            g = inst_type.replace("r5.", "r6g.")
            if g in _EC2:
                savings = _EC2[inst_type]["m"] - _EC2[g]["m"]
                if savings > 0:
                    suggestions.append({
                        "type": "graviton", "title": f"Switch to {g} (Graviton/Arm)",
                        "description": f"R6g instances are ~{int(savings/_EC2[inst_type]['m']*100)}% cheaper.",
                        "potential_savings": round(savings, 2), "impact": "low", "effort": "low",
                        "action": f"Change `instance_type` to \"{g}\"",
                    })

        # Right-size
        suggestions.append({
            "type": "rightsize", "title": "Right-size and Monitor Utilization",
            "description": "Monitor CPU/memory utilization to right-size instances. Most workloads run at <20% utilization.",
            "potential_savings": round(mcost * 0.3, 2), "impact": "medium", "effort": "medium",
            "action": "Set up CloudWatch utilization alarms, review CW metrics, downsize underutilized instances",
        })

        # Spot
        suggestions.append({
            "type": "spot", "title": "Use Spot Instances",
            "description": "Spot instances can save 60-90% for fault-tolerant, stateless, or flexible workloads.",
            "potential_savings": round(mcost * 0.6, 2), "impact": "high", "effort": "medium" if estimate.get("is_spot") else "low",
            "action": "Use `aws_spot_instance_request` or add `capacity_type = \"spot\"` in EKS/Auto Scaling mixed instances policy",
        })

        # Reserved
        suggestions.append({
            "type": "reserved", "title": "Reserved Instances (1-3yr)",
            "description": "1-year RI saves ~40%, 3-year saves ~60% for steady-state workloads.",
            "potential_savings": round(mcost * 0.4, 2), "impact": "high", "effort": "low",
            "action": "Purchase Reserved Instances in the AWS Console for this instance type in the target region",
        })

    # ── EBS ─────────────────────────────────────────────────────────────────
    if rtype == "aws_ebs_volume":
        vol_type = estimate.get("volume_type", "")
        if vol_type == "gp2":
            size = estimate.get("size_gb", 100)
            savings = size * (_EBS["gp2"]["gb"] - _EBS["gp3"]["gb"])
            suggestions.append({
                "type": "ebs_gp3", "title": "Upgrade gp2 → gp3",
                "description": f"gp3 is ~20% cheaper and offers baseline 3000 IOPS + 125 MB/s throughput free.",
                "potential_savings": round(savings, 2), "impact": "low", "effort": "low",
                "action": "Change `type` from \"gp2\" to \"gp3\" in the volume resource",
            })
        suggestions.append({
            "type": "ebs_snapshot", "title": "Clean Up Unused Snapshots",
            "description": "Orphaned EBS snapshots cost storage. Automate cleanup with lifecycle policies.",
            "potential_savings": round(mcost * 0.1, 2), "impact": "low", "effort": "low",
            "action": "Set up DLM lifecycle policy to expire old snapshots, or use `aws_ebs_snapshot_copy` with expiration",
        })

    # ── RDS ─────────────────────────────────────────────────────────────────
    if rtype == "aws_db_instance":
        if estimate.get("multi_az"):
            suggestions.append({
                "type": "rds_multi_az", "title": "Review Multi-AZ Requirement",
                "description": "Multi-AZ doubles RDS costs. Consider if standby is needed for dev/staging.",
                "potential_savings": round(mcost / 2, 2), "impact": "high", "effort": "medium",
                "action": "Set `multi_az = false` for non-production databases",
            })
        suggestions.append({
            "type": "rds_reserved", "title": "RDS Reserved Instance",
            "description": "1-year RI saves ~30%, 3-year saves ~50% for steady-state databases.",
            "potential_savings": round(mcost * 0.35, 2), "impact": "high", "effort": "low",
            "action": "Purchase RDS Reserved Instance in AWS Console",
        })
        suggestions.append({
            "type": "rds_graviton", "title": "Use Graviton (db.m6g/db.r6g)",
            "description": "Graviton-based RDS instances are ~15-20% cheaper than x86.",
            "potential_savings": round(mcost * 0.15, 2), "impact": "low", "effort": "low",
            "action": "Change `instance_class` from db.m5 to db.m6g or db.r5 to db.r6g",
        })
        suggestions.append({
            "type": "rds_storage", "title": "Review Storage Allocation",
            "description": "RDS storage is billed regardless of usage. Right-size allocated storage.",
            "potential_savings": round(mcost * 0.1, 2), "impact": "low", "effort": "low",
            "action": "Reduce `allocated_storage` to match actual usage based on CloudWatch metrics",
        })

    # ── EKS ─────────────────────────────────────────────────────────────────
    if rtype == "aws_eks_cluster":
        suggestions.append({
            "type": "eks_fargate", "title": "Use Fargate for Select Workloads",
            "description": "Fargate profiles eliminate node management and can reduce costs for burst/sporadic workloads.",
            "potential_savings": round(mcost * 0.15, 2), "impact": "medium", "effort": "medium",
            "action": "Add `fargate_profile` to EKS module and move select namespaces to Fargate",
        })
        suggestions.append({
            "type": "eks_ri", "title": "EKS Savings Plans",
            "description": "Compute Savings Plans (1/3yr) cover EC2 + Fargate + Lambda at 30-60% discount.",
            "potential_savings": round(mcost * 0.35, 2), "impact": "high", "effort": "low",
            "action": "Purchase Compute Savings Plan in AWS Console covering EKS compute",
        })

    if rtype == "aws_eks_node_group":
        suggestions.append({
            "type": "eks_spot_nodes", "title": "Use Spot Instances for Node Group",
            "description": "Spot instances for EKS node groups can save 60-90% for non-critical or flexible workloads.",
            "potential_savings": round(mcost * 0.6, 2), "impact": "high", "effort": "medium",
            "action": "Use `instance_types` with Spot allocation strategy or use Karpenter with spot node pools",
        })
        suggestions.append({
            "type": "eks_karpenter", "title": "Consider Karpenter for Node Autoscaling",
            "description": "Karpenter optimizes node provisioning with spot/on-demand mix and right-sizing, reducing waste by 30-50%.",
            "potential_savings": round(mcost * 0.3, 2), "impact": "medium", "effort": "high",
            "action": "Replace Cluster Autoscaler with Karpenter for more efficient bin-packing",
        })

    # ── S3 ──────────────────────────────────────────────────────────────────
    if rtype == "aws_s3_bucket":
        suggestions.append({
            "type": "s3_lifecycle", "title": "Configure S3 Lifecycle Policy",
            "description": "Move data to IA/Glacier after 30/90 days to reduce costs by 40-80%.",
            "potential_savings": round(mcost * 0.4, 2), "impact": "medium", "effort": "low",
            "action": "Add `lifecycle_rule` with transitions: STANDARD→STANDARD_IA (30d)→GLACIER (90d)→DEEP_ARCHIVE (365d)",
        })
        suggestions.append({
            "type": "s3_intelligent", "title": "Use S3 Intelligent-Tiering",
            "description": "Auto-tiers between frequent/infrequent access. No lifecycle management needed, monitoring fee applies.",
            "potential_savings": round(mcost * 0.15, 2), "impact": "low", "effort": "low",
            "action": "Change bucket to use S3 Intelligent-Tiering via `s3_bucket_intelligent_tiering_configuration`",
        })
        suggestions.append({
            "type": "s3_abort", "title": "Abort Incomplete Multipart Uploads",
            "description": "Abandoned multipart uploads accumulate storage costs. Set lifecycle to auto-abort.",
            "potential_savings": round(mcost * 0.05, 2), "impact": "low", "effort": "low",
            "action": "Add `abort_incomplete_multipart_upload_days = 7` in lifecycle_rule",
        })

    # ── Lambda ──────────────────────────────────────────────────────────────
    if rtype == "aws_lambda_function":
        suggestions.append({
            "type": "lambda_memory", "title": "Optimize Lambda Memory",
            "description": "42% of Lambda functions are over-provisioned. Lower memory reduces cost (linearly) and often runs faster.",
            "potential_savings": round(mcost * 0.3, 2), "impact": "low", "effort": "low",
            "action": "Use AWS Lambda Power Tuning to find optimal memory setting, update `memory_size`",
        })
        suggestions.append({
            "type": "lambda_graviton", "title": "Use Graviton (arm64) for Lambda",
            "description": "ARM64 architecture is ~20% cheaper than x86 for Lambda functions.",
            "potential_savings": round(mcost * 0.2, 2), "impact": "low", "effort": "low",
            "action": "Set `architectures = [\"arm64\"]` in Lambda function, rebuild runtime for ARM",
        })
        suggestions.append({
            "type": "lambda_provisioned", "title": "Review Provisioned Concurrency",
            "description": "Provisioned concurrency costs extra. Use only for latency-critical functions.",
            "potential_savings": round(mcost * 0.1, 2), "impact": "low", "effort": "low",
            "action": "Remove `provisioned_concurrent_executions` if not needed, or use Application Auto Scaling",
        })

    # ── ELB ─────────────────────────────────────────────────────────────────
    if rtype in ("aws_lb", "aws_alb", "aws_elb"):
        suggestions.append({
            "type": "elb_idle", "title": "Review Load Balancer Necessity",
            "description": "Idle ALBs cost ~$23/mo. Consolidate or remove LBs with no healthy targets.",
            "potential_savings": round(mcost * 0.5, 2) if mcost > 20 else 0, "impact": "high", "effort": "low",
            "action": "Check target group health, consider consolidating multiple ALBs or removing unused ones",
        })

    # ── Elasticache ─────────────────────────────────────────────────────────
    if rtype in ("aws_elasticache_cluster", "aws_elasticache_replication_group"):
        suggestions.append({
            "type": "elasticache_serverless", "title": "Consider ElastiCache Serverless",
            "description": "Serverless Redis costs only for usage, no idle capacity. Good for variable workloads.",
            "potential_savings": round(mcost * 0.3, 2), "impact": "medium", "effort": "medium",
            "action": "Use `aws_elasticache_serverless_cache` instead of provisioned cluster",
        })

    # ── KMS ─────────────────────────────────────────────────────────────────
    if rtype == "aws_kms_key":
        suggestions.append({
            "type": "kms_cleanup", "title": "Review KMS Key Usage",
            "description": "Each customer-managed KMS key costs $1/mo. Delete unused keys to save.",
            "potential_savings": mcost, "impact": "low", "effort": "low",
            "action": "Identify unused KMS keys via CloudTrail, schedule key deletion for unused ones",
        })

    # ── CloudWatch Logs ─────────────────────────────────────────────────────
    if rtype == "aws_cloudwatch_log_group":
        suggestions.append({
            "type": "cw_log_retention", "title": "Set Log Retention Policy",
            "description": "Set log retention (e.g. 30/90 days) to auto-expire old logs and reduce storage costs.",
            "potential_savings": round(mcost * 0.6, 2), "impact": "high", "effort": "low",
            "action": "Set `retention_in_days = 30` (or 90/180) — default is NEVER EXPIRE (most expensive)",
        })
        suggestions.append({
            "type": "cw_log_subscription", "title": "Filter and Route Logs to S3/Glacier",
            "description": "Use subscription filters to send logs to S3 (IA/Glacier) for cheaper long-term storage.",
            "potential_savings": round(mcost * 0.4, 2), "impact": "medium", "effort": "medium",
            "action": "Add `aws_cloudwatch_log_subscription_filter` to export logs to S3/OpenSearch",
        })

    # ── DynamoDB ────────────────────────────────────────────────────────────
    if rtype == "aws_dynamodb_table":
        suggestions.append({
            "type": "dynamodb_ondemand", "title": "Review DynamoDB Billing Mode",
            "description": "On-demand is good for variable traffic. Provisioned with auto-scaling is 30-50% cheaper for steady workloads.",
            "potential_savings": round(mcost * 0.3, 2), "impact": "medium", "effort": "low",
            "action": "Switch to `billing_mode = \"PROVISIONED\"` with auto-scaling for predictable workloads",
        })
        suggestions.append({
            "type": "dynamodb_ttl", "title": "Use TTL for Expired Data",
            "description": "DynamoDB TTL automatically deletes expired items for free, reducing storage costs.",
            "potential_savings": round(mcost * 0.1, 2), "impact": "low", "effort": "low",
            "action": "Add `ttl { attribute_name = \"expires_on\", enabled = true }` to the table",
        })
        suggestions.append({
            "type": "dynamodb_dax", "title": "Review DAX Cluster Need",
            "description": "DAX clusters cost ~$50-500/mo. Use DAX only if microsecond latency is critical.",
            "potential_savings": round(mcost * 0.2, 2) if mcost > 50 else 0, "impact": "medium", "effort": "medium",
            "action": "Remove DAX cluster for non-latency-critical workloads",
        })

    # ── OpenSearch ──────────────────────────────────────────────────────────
    if rtype in ("aws_opensearch_domain", "aws_elasticsearch_domain"):
        suggestions.append({
            "type": "opensearch_ultrawarm", "title": "Use UltraWarm for Older Indices",
            "description": "UltraWarm nodes store older indices on S3 at ~10% of hot storage cost.",
            "potential_savings": round(mcost * 0.4, 2), "impact": "medium", "effort": "medium",
            "action": "Add UltraWarm nodes and configure Index State Management policies to move data to warm storage",
        })
        suggestions.append({
            "type": "opensearch_master", "title": "Right-size Master Nodes",
            "description": "Master nodes (t3.small) are sufficient for most clusters; don't overprovision.",
            "potential_savings": round(mcost * 0.1, 2), "impact": "low", "effort": "low",
            "action": "Use `t3.small.search` for dedicated master nodes instead of larger instances",
        })

    # ── MSK ─────────────────────────────────────────────────────────────────
    if rtype == "aws_msk_cluster":
        suggestions.append({
            "type": "msk_broker_count", "title": "Review MSK Broker Count",
            "description": "3 brokers are needed for Multi-AZ. For dev, consider 1-2 brokers.",
            "potential_savings": round(mcost / 3, 2), "impact": "high", "effort": "medium",
            "action": "Reduce `number_of_broker_nodes` to 2 for dev/test (single-AZ), or use Serverless MSK",
        })

    # ── Network Firewall ────────────────────────────────────────────────────
    if rtype == "aws_networkfirewall_firewall":
        suggestions.append({
            "type": "nfw_endpoint_count", "title": "Review Number of Network Firewall Endpoints",
            "description": "Each firewall endpoint costs ~$288/mo. Consolidate to fewer endpoints.",
            "potential_savings": round(mcost * 0.4, 2), "impact": "high", "effort": "medium",
            "action": "Use single firewall endpoint with centralized inspection VPC",
        })

    # ── WAF ─────────────────────────────────────────────────────────────────
    if rtype == "aws_wafv2_web_acl":
        suggestions.append({
            "type": "waf_rules", "title": "Review WAF Rule Count",
            "description": "First 5 rules free, then $1/rule/mo. Minimize rules for cost efficiency.",
            "potential_savings": round(mcost * 0.2, 2), "impact": "low", "effort": "low",
            "action": "Review and consolidate WAF rules, remove unused managed rule groups",
        })

    return suggestions


# ─── Main estimation function ───────────────────────────────────────────────

def estimate_resources(resources: list[dict], default_provider: str = "aws") -> dict:
    """Estimate costs for a list of parsed resources.

    Returns a complete estimation report with:
    - Monthly/yearly cost totals
    - Service breakdown
    - Per-resource estimates
    - Cost-saving suggestions
    - Recommendations summary
    """
    resource_estimates = []
    unknown_resources = []
    all_suggestions = []
    total_savings = 0

    for resource in resources:
        provider = resource.get("provider", default_provider)
        rtype = resource.get("type", "")
        service = resource.get("service", "")

        # Free resource?
        if rtype in _FREE_RESOURCES or resource.get("config", {}).get("_free") == "true":
            resource_estimates.append(_free_resource(resource["name"], rtype))
            continue

        estimate = None

        if provider == "aws":
            estimator = _AWS_ESTIMATORS.get(rtype)
            if estimator:
                estimate = estimator(resource)
            elif service == "free":
                estimate = _free_resource(resource["name"], rtype)
            elif _AWS_RESOURCE_MAP.get(rtype, (None, None))[1] == "free":
                estimate = _free_resource(resource["name"], rtype)

        elif provider == "azure":
            estimator = _AZURE_ESTIMATORS.get(rtype)
            if estimator:
                estimate = estimator(resource)
            elif service == "free":
                estimate = _free_resource(resource["name"], rtype)

        elif provider == "gcp":
            estimator = _GCP_ESTIMATORS.get(rtype)
            if estimator:
                estimate = estimator(resource)
            elif service == "free":
                estimate = _free_resource(resource["name"], rtype)

        if estimate:
            estimate["provider"] = provider
            suggestions = _gen_suggestions(resource, estimate)
            estimate["suggestions"] = suggestions
            all_suggestions.extend(suggestions)
            total_savings += sum(s.get("potential_savings", 0) for s in suggestions if s.get("potential_savings", 0) > 0)
            resource_estimates.append(estimate)
        else:
            unknown_resources.append({
                "resource_name": resource.get("name", "unknown"),
                "resource_type": rtype,
                "reason": "No pricing data available for this resource type",
            })

    # Calculate summary
    total_monthly = sum(r.get("monthly_cost", 0) for r in resource_estimates)
    service_breakdown = {}
    for est in resource_estimates:
        bd = est.get("breakdown", {})
        for svc, cost in bd.items():
            if cost > 0:
                service_breakdown[svc] = service_breakdown.get(svc, 0) + cost

    service_breakdown = dict(sorted(service_breakdown.items(), key=lambda x: x[1], reverse=True))
    top_services = [
        {"service": svc, "monthly_cost": round(cost, 2),
         "percentage": round(cost / total_monthly * 100, 1) if total_monthly > 0 else 0}
        for svc, cost in service_breakdown.items()
    ][:15]

    # Deduplicate and sort suggestions
    seen = set()
    unique_suggestions = []
    for s in all_suggestions:
        key = (s.get("type", ""), s.get("title", ""))
        if key not in seen:
            seen.add(key)
            unique_suggestions.append(s)
    unique_suggestions.sort(key=lambda s: s.get("potential_savings", 0), reverse=True)

    # Free tier eligible resources (individual resource check)
    free_tier_eligible = [
        r for r in resource_estimates
        if r.get("monthly_cost", 0) <= 5 and r.get("resource_type", "") in (
            "aws_lambda_function", "aws_s3_bucket", "aws_dynamodb_table",
            "aws_sqs_queue", "aws_sns_topic", "aws_cloudwatch_log_group",
            "aws_ecr_repository",
        )
    ]

    # Free tier comprehensive analysis
    free_tier_analysis = _check_free_tier_eligibility(resource_estimates)

    # Count free resources (those with zero cost)
    free_resource_count = sum(1 for r in resource_estimates if r.get("_free") or r.get("monthly_cost", 0) == 0)

    return {
        "id": str(uuid.uuid4()),
        "total_monthly_cost": round(total_monthly, 2),
        "total_yearly_cost": round(total_monthly * 12, 2),
        "resource_count": len(resource_estimates),
        "free_resource_count": free_resource_count,
        "unknown_resource_count": len(unknown_resources),
        "service_breakdown": service_breakdown,
        "top_services_by_cost": top_services,
        "resource_estimates": resource_estimates,
        "unknown_resources": unknown_resources,
        "suggestions": unique_suggestions[:25],
        "free_tier_eligible": free_tier_eligible[:10],
        "free_tier_limits": _FREE_TIER_INFO,
        "free_tier_analysis": free_tier_analysis,
        "total_potential_savings": round(total_savings, 2),
        "provider_breakdown": {
            prov: round(sum(r.get("monthly_cost", 0) for r in resource_estimates if r.get("provider") == prov), 2)
            for prov in set(r.get("provider", default_provider) for r in resource_estimates)
        },
    }
