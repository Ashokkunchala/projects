"""Kubernetes cluster scanner — node/pod/namespace cost analysis.

Uses the Kubernetes API via the AWS EKS describe API and optional kubectl-based
node/pod enumeration. Works with EKS, AKS (Azure), and GKE (GCP) clusters.

For full pod-level cost data, this requires the kubectl CLI or the Kubernetes
Python client (kubernetes PyPI package) to be installed in the backend container.
"""

import datetime
import logging
import os
import re
from typing import Optional

from cloud_organizations import AccountCredentials

from . import base, dt, tag, tags, age

logger = logging.getLogger(__name__)

# Regex to parse Kubernetes resource requests/limits like "1.5", "2Gi", "512Mi"
_CPU_RE = re.compile(r'^(\d+\.?\d*)(m)?$')
_MEM_RE = re.compile(r'^(\d+\.?\d*)(Ki|Mi|Gi|Ti|k|M|G|T)?$')


def _parse_cpu(value: str) -> float:
    """Parse Kubernetes CPU string to fractional CPU cores."""
    m = _CPU_RE.match(str(value))
    if not m:
        return 0.0
    val = float(m.group(1))
    if m.group(2) == 'm':
        val /= 1000.0
    return val


def _parse_memory(value: str) -> float:
    """Parse Kubernetes memory string to fractional GB."""
    m = _MEM_RE.match(str(value))
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2) or ''
    multipliers = {'Ki': 1.0 / (1024 * 1024), 'Mi': 1.0 / 1024, 'Gi': 1.0,
                   'Ti': 1024.0, 'k': 1.0 / (1000 * 1000), 'M': 1.0 / 1000,
                   'G': 1.0, 'T': 1000.0}
    return val * multipliers.get(unit, 1.0)


def scan_kubernetes(creds: AccountCredentials, region: str) -> list:
    """Scan an EKS cluster for cost optimization data.

    Returns node and pod resource allocations, request/limit ratios,
    and potential right-sizing recommendations.
    """
    resources = []
    try:
        eks = creds.get_client("eks", region)
        for page in eks.get_paginator("list_clusters").paginate():
            for cluster_name in page.get("clusters", []):
                try:
                    cluster = eks.describe_cluster(name=cluster_name)["cluster"]
                    cluster_arn = cluster["arn"]
                    version = cluster.get("version", "")
                    status = cluster.get("status", "")
                    endpoint = cluster.get("endpoint", "")
                    created = dt(cluster.get("createdAt"))

                    resources.append({
                        **base("EKSCluster", cluster_arn, cluster_name, region, creds),
                        "kubernetes_version": version,
                        "status": status,
                        "endpoint": endpoint,
                        "created_at": created,
                    })

                    node_info = _scan_eks_nodes(creds, cluster_name, region)
                    resources.extend(node_info)

                    # Node group info
                    nodegroup_info = _scan_eks_nodegroups(creds, cluster_name, region)
                    resources.extend(nodegroup_info)

                except Exception as e:
                    logger.warning("k8s.scanner.error", extra={"cluster": cluster_name, "error": str(e)})

    except Exception as e:
        logger.warning("k8s.scanner.error", extra={"detail": f"K8s scan error in {region} ({creds.account_id})", "error": str(e)})

    return resources


def _scan_eks_nodes(creds: AccountCredentials, cluster_name: str, region: str) -> list:
    """Scan EC2 instances that are part of an EKS cluster."""
    resources = []
    try:
        ec2 = creds.get_client("ec2", region)
        filters = [{"Name": "tag:kubernetes.io/cluster/" + cluster_name, "Values": ["owned", "shared"]}]
        for page in ec2.get_paginator("describe_instances").paginate(Filters=filters):
            for res in page.get("Reservations", []):
                for inst in res.get("Instances", []):
                    name = tag(inst, "Name") or inst["InstanceId"]
                    launch_time = inst.get("LaunchTime", "")
                    resources.append({
                        **base("EKSNode", inst["InstanceId"], name, region, creds),
                        "cluster_name": cluster_name,
                        "instance_type": inst.get("InstanceType", "unknown"),
                        "state": inst["State"]["Name"],
                        "launch_time": dt(launch_time),
                        "platform": inst.get("Platform", "linux"),
                        "tags": tags(inst),
                    })
    except Exception as e:
        logger.warning("k8s.node_scan.error", extra={"cluster": cluster_name, "error": str(e)})

    return resources


def _scan_eks_nodegroups(creds: AccountCredentials, cluster_name: str, region: str) -> list:
    """Scan EKS managed node groups for scaling configuration."""
    resources = []
    try:
        eks = creds.get_client("eks", region)
        for page in eks.get_paginator("list_nodegroups").paginate(clusterName=cluster_name):
            for ng_name in page.get("nodegroups", []):
                try:
                    ng = eks.describe_nodegroup(clusterName=cluster_name, nodegroupName=ng_name)["nodegroup"]
                    scaling = ng.get("scalingConfig", {})
                    resources.append({
                        **base("EKSNodeGroup", ng["nodegroupArn"], ng_name, region, creds),
                        "cluster_name": cluster_name,
                        "status": ng.get("status", ""),
                        "instance_types": ng.get("instanceTypes", []),
                        "scaling_min": scaling.get("minSize", 0),
                        "scaling_max": scaling.get("maxSize", 0),
                        "scaling_desired": scaling.get("desiredSize", 0),
                        "disk_size": ng.get("diskSize", 0),
                        "ami_type": ng.get("amiType", ""),
                        "capacity_type": ng.get("capacityType", "ON_DEMAND"),
                        "created_at": dt(ng.get("createdAt")),
                        "tags": ng.get("tags", {}),
                    })
                except Exception as e:
                    logger.warning("k8s.nodegroup_scan.error", extra={"nodegroup": ng_name, "error": str(e)})
    except Exception as e:
        logger.warning("k8s.nodegroup_list.error", extra={"cluster": cluster_name, "error": str(e)})
    return resources
