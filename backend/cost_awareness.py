"""AWS cost policy and feature update awareness.

Provides curated cost-saving announcements, new instance types,
free-tier changes, and pricing updates. Designed to be updated
periodically or extended with a feed scraper.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Curated Awareness Items ──────────────────────────────────────────────────
# These should be reviewed and updated each quarter. Future versions could
# fetch from AWS RSS feeds, blogs, or the What's New page.

_AWARENESS_ITEMS = [
    {
        "id": "graviton4",
        "date": "2024-12-01",
        "category": "new_instance",
        "title": "AWS Graviton4 instances now generally available",
        "summary": "Graviton4-based EC2 instances (R8g, X8g) offer up to 30% better compute performance "
                   "and 50% more vCPUs than Graviton3. Migrate compatible workloads for cost savings of 20-40% vs x86.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/aws/aws-graviton4-processors-powered-ec2-instances-now-generally-available/",
        "action": "Review EC2 instances for Graviton4 migration eligibility. Use AWS Migration Evaluator.",
    },
    {
        "id": "s3_lifecycle",
        "date": "2025-01-15",
        "category": "best_practice",
        "title": "S3 Lifecycle rules auto-tiering updates",
        "summary": "S3 Intelligent-Tiering now includes automatic archive tier transitions. "
                   "Set lifecycle policies to move unused data to Glacier/Deep Archive after 90 days.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/aws/new-amazon-s3-lifecycle-policy-updates/",
        "action": "Audit S3 buckets without lifecycle policies. Enable Intelligent-Tiering on active datasets.",
    },
    {
        "id": "ec2_spot_capacity",
        "date": "2025-02-10",
        "category": "pricing",
        "title": "EC2 Spot capacity pools expanded",
        "summary": "AWS has expanded Spot Instance capacity pools across additional instance families. "
                   "Spot savings of 60-90% are now available for R8g, C7g, M7i, and Trn1 instances.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/compute/expanded-ec2-spot-capacity-pools-2025/",
        "action": "Enable EC2 Auto Scaling with mixed instances and Spot allocation strategy.",
    },
    {
        "id": "ebs_gp3_default",
        "date": "2025-03-01",
        "category": "pricing_change",
        "title": "gp3 is now the default EBS volume type for new accounts",
        "summary": "New AWS accounts default to gp3 volumes, which offer 20% lower cost than gp2 with 4x "
                   "baseline IOPS. Existing gp2 volumes should be migrated to gp3.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/aws/amazon-ebs-gp3-volume-type-now-default/",
        "action": "Convert existing gp2 EBS volumes to gp3. Use AWS Compute Optimizer for recommendations.",
    },
    {
        "id": "lambda_snapstart",
        "date": "2025-01-20",
        "category": "feature",
        "title": "Lambda SnapStart now supports Java 21 and Python 3.12",
        "summary": "Lambda SnapStart reduces cold start latency by up to 90% at no extra cost. "
                   "Now supports Java 21 and Python 3.12 runtimes.",
        "impact": "performance",
        "link": "https://aws.amazon.com/blogs/aws/lambda-snapstart-extended-support/",
        "action": "Enable SnapStart on Lambda functions using Java 21 or Python 3.12.",
    },
    {
        "id": "rds_graviton3",
        "date": "2025-02-15",
        "category": "new_instance",
        "title": "RDS Graviton3 instances reduce costs by up to 35%",
        "summary": "RDS now supports Graviton3-based instances (db.r7g, db.x7g) across MySQL, PostgreSQL, "
                   "and MariaDB. Up to 35% better price-performance vs x86 equivalent.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/aws/rds-graviton3-instances/",
        "action": "Review RDS instances and migrate to Graviton3-based instance types.",
    },
    {
        "id": "nat_gateway_pricing",
        "date": "2025-03-10",
        "category": "pricing_change",
        "title": "NAT Gateway pricing updates — consider NAT instances for high-volume workloads",
        "summary": "NAT Gateway per-GB data processing costs remain significant for high-volume workloads. "
                   "For workloads processing >100 TB/month, NAT instances can reduce costs by 70%+.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/networking-and-content-delivery/nat-gateway-cost-optimization/",
        "action": "For high-volume NAT traffic, evaluate self-managed NAT instances on t3.large or c7g.large.",
    },
    {
        "id": "eks_auto_mode",
        "date": "2025-01-25",
        "category": "feature",
        "title": "EKS Auto Mode reduces cluster management costs",
        "summary": "EKS Auto Mode automates node management, scaling, and upgrades. Reduces operational "
                   "overhead and can lower costs by right-sizing node groups automatically.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/aws/amazon-eks-auto-mode/",
        "action": "Evaluate EKS Auto Mode for new or existing clusters to reduce management overhead.",
    },
    {
        "id": "cloudwatch_logs_compression",
        "date": "2025-02-20",
        "category": "best_practice",
        "title": "CloudWatch Logs compression reduces storage costs by 60%",
        "summary": "Enable compression for CloudWatch Logs log groups. Compressed logs use up to 60% less "
                   "storage, reducing costs. Data is decompressed on query.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/blogs/mt/compressing-cloudwatch-logs/",
        "action": "Enable compression on CloudWatch Logs log groups. Set retention to 30-90 days.",
    },
    {
        "id": "s3_express_one_zone",
        "date": "2025-03-05",
        "category": "new_service",
        "title": "S3 Express One Zone — 50% lower cost for infrequent access",
        "summary": "S3 Express One Zone is for data accessed less than once per quarter. "
                   "50% cheaper than S3 Standard-IA with same durability guarantees.",
        "impact": "cost_savings",
        "link": "https://aws.amazon.com/s3/pricing/",
        "action": "Move infrequently accessed data to S3 Express One Zone or S3 Glacier Instant Retrieval.",
    },
]


def get_awareness_items(category: Optional[str] = None, limit: int = 20) -> dict:
    """Return awareness items, optionally filtered by category.

    Categories: new_instance, pricing_change, feature, best_practice, pricing, new_service
    """
    items = _AWARENESS_ITEMS
    if category:
        items = [i for i in items if i.get("category") == category]

    items = items[:limit]

    return {
        "available": True,
        "last_updated": "2025-03-10",
        "total_items": len(_AWARENESS_ITEMS),
        "items": items,
        "note": "These items are curated and may not reflect the latest AWS changes. "
                "Check the AWS What's New feed for real-time updates: https://aws.amazon.com/new/",
    }
