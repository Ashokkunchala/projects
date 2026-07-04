"""Infrastructure-as-Code template parser — Terraform Plan JSON, HCL, CloudFormation."""

import json as _json
import logging
import os
import re
import tempfile
import zipfile
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import yaml as _yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

try:
    import git as _git
    _GIT_AVAILABLE = True
except ImportError:
    _GIT_AVAILABLE = False


# ─── Resource type → (provider, service) mapping ────────────────────────────

_AWS_RESOURCE_MAP = {
    # Compute
    "aws_instance": ("aws", "ec2"),
    "aws_ebs_volume": ("aws", "ec2"),
    "aws_ebs_snapshot": ("aws", "ec2"),
    "aws_eip": ("aws", "ec2"),
    "aws_nat_gateway": ("aws", "ec2"),
    "aws_launch_template": ("aws", "free"),
    "aws_launch_configuration": ("aws", "free"),
    "aws_autoscaling_group": ("aws", "autoscaling"),
    "aws_placement_group": ("aws", "free"),
    "aws_spot_instance_request": ("aws", "ec2"),
    "aws_spot_fleet_request": ("aws", "ec2"),
    # Load Balancing
    "aws_lb": ("aws", "elb"),
    "aws_lb_target_group": ("aws", "free"),
    "aws_alb": ("aws", "elb"),
    "aws_lb_listener": ("aws", "free"),
    "aws_lb_listener_rule": ("aws", "free"),
    # RDS
    "aws_db_instance": ("aws", "rds"),
    "aws_rds_cluster": ("aws", "rds"),
    "aws_rds_cluster_instance": ("aws", "rds"),
    "aws_db_subnet_group": ("aws", "free"),
    "aws_db_parameter_group": ("aws", "free"),
    # Storage
    "aws_s3_bucket": ("aws", "s3"),
    "aws_s3_bucket_object": ("aws", "free"),
    "aws_efs_file_system": ("aws", "efs"),
    "aws_efs_mount_target": ("aws", "free"),
    "aws_fsx_lustre_file_system": ("aws", "fsx"),
    "aws_fsx_windows_file_system": ("aws", "fsx"),
    "aws_fsx_ontap_file_system": ("aws", "fsx"),
    "aws_fsx_openzfs_file_system": ("aws", "fsx"),
    "aws_backup_vault": ("aws", "backup"),
    "aws_backup_plan": ("aws", "free"),
    # Serverless
    "aws_lambda_function": ("aws", "lambda"),
    "aws_lambda_layer_version": ("aws", "free"),
    "aws_lambda_permission": ("aws", "free"),
    # Containers / K8s
    "aws_eks_cluster": ("aws", "eks"),
    "aws_eks_node_group": ("aws", "eks"),
    "aws_eks_addon": ("aws", "eks"),
    "aws_eks_identity_provider_config": ("aws", "free"),
    "aws_ecs_cluster": ("aws", "ecs"),
    "aws_ecs_service": ("aws", "ecs"),
    "aws_ecs_task_definition": ("aws", "free"),
    "aws_ecr_repository": ("aws", "ecr"),
    "aws_ecr_replication_configuration": ("aws", "free"),
    # Networking
    "aws_vpc": ("aws", "free"),
    "aws_subnet": ("aws", "free"),
    "aws_security_group": ("aws", "free"),
    "aws_security_group_rule": ("aws", "free"),
    "aws_network_interface": ("aws", "free"),
    "aws_internet_gateway": ("aws", "free"),
    "aws_nat_gateway": ("aws", "ec2"),
    "aws_eip": ("aws", "ec2"),
    "aws_route_table": ("aws", "free"),
    "aws_route": ("aws", "free"),
    "aws_route53_zone": ("aws", "route53"),
    "aws_route53_record": ("aws", "free"),
    "aws_cloudfront_distribution": ("aws", "cloudfront"),
    "aws_api_gateway_rest_api": ("aws", "apigateway"),
    "aws_api_gateway_stage": ("aws", "free"),
    "aws_apigatewayv2_api": ("aws", "apigateway"),
    "aws_apigatewayv2_stage": ("aws", "free"),
    "aws_vpc_endpoint": ("aws", "vpc_endpoints"),
    "aws_vpc_peering_connection": ("aws", "free"),
    "aws_ec2_transit_gateway": ("aws", "transit_gateway"),
    "aws_ec2_transit_gateway_vpc_attachment": ("aws", "transit_gateway"),
    "aws_dx_connection": ("aws", "direct_connect"),
    "aws_dx_private_virtual_interface": ("aws", "direct_connect"),
    "aws_globalaccelerator_accelerator": ("aws", "global_accelerator"),
    "aws_networkfirewall_firewall": ("aws", "network_firewall"),
    "aws_networkfirewall_firewall_policy": ("aws", "free"),
    "aws_shield_protection": ("aws", "shield"),
    "aws_wafv2_web_acl": ("aws", "waf"),
    "aws_wafv2_rule_group": ("aws", "free"),
    # Database
    "aws_elasticache_cluster": ("aws", "elasticache"),
    "aws_elasticache_replication_group": ("aws", "elasticache"),
    "aws_elasticache_subnet_group": ("aws", "free"),
    "aws_dynamodb_table": ("aws", "dynamodb"),
    "aws_dax_cluster": ("aws", "dax"),
    "aws_redshift_cluster": ("aws", "redshift"),
    "aws_redshift_subnet_group": ("aws", "free"),
    "aws_docdb_cluster": ("aws", "documentdb"),
    "aws_docdb_cluster_instance": ("aws", "documentdb"),
    "aws_neptune_cluster": ("aws", "neptune"),
    "aws_neptune_cluster_instance": ("aws", "neptune"),
    "aws_mq_broker": ("aws", "mq"),
    # Messaging / Streaming
    "aws_sqs_queue": ("aws", "sqs"),
    "aws_sns_topic": ("aws", "sns"),
    "aws_sns_topic_subscription": ("aws", "free"),
    "aws_kinesis_stream": ("aws", "kinesis"),
    "aws_kinesis_firehose_delivery_stream": ("aws", "kinesis"),
    "aws_msk_cluster": ("aws", "msk"),
    "aws_msk_configuration": ("aws", "free"),
    "aws_eventbridge_bus": ("aws", "eventbridge"),
    "aws_eventbridge_rule": ("aws", "free"),
    "aws_sfn_state_machine": ("aws", "step_functions"),
    "aws_appsync_graphql_api": ("aws", "appsync"),
    # Analytics
    "aws_emr_cluster": ("aws", "emr"),
    "aws_emr_serverless_application": ("aws", "emr_serverless"),
    "aws_glue_job": ("aws", "glue"),
    "aws_glue_crawler": ("aws", "glue"),
    "aws_glue_trigger": ("aws", "free"),
    "aws_athena_workgroup": ("aws", "athena"),
    "aws_opensearch_domain": ("aws", "opensearch"),
    "aws_elasticsearch_domain": ("aws", "opensearch"),
    "aws_quicksight_user": ("aws", "quicksight"),
    # AI / ML
    "aws_sagemaker_notebook_instance": ("aws", "sagemaker"),
    "aws_sagemaker_endpoint": ("aws", "sagemaker"),
    "aws_sagemaker_model": ("aws", "free"),
    "aws_sagemaker_training_job": ("aws", "sagemaker"),
    "aws_bedrock_custom_model": ("aws", "bedrock"),
    # Security / IAM
    "aws_iam_role": ("aws", "free"),
    "aws_iam_role_policy": ("aws", "free"),
    "aws_iam_policy": ("aws", "free"),
    "aws_iam_role_policy_attachment": ("aws", "free"),
    "aws_iam_user": ("aws", "free"),
    "aws_iam_group": ("aws", "free"),
    "aws_iam_openid_connect_provider": ("aws", "free"),
    "aws_iam_instance_profile": ("aws", "free"),
    "aws_kms_key": ("aws", "kms"),
    "aws_kms_alias": ("aws", "free"),
    "aws_secretsmanager_secret": ("aws", "secretsmanager"),
    "aws_secretsmanager_secret_version": ("aws", "free"),
    "aws_acm_certificate": ("aws", "acm"),
    "aws_acm_certificate_validation": ("aws", "free"),
    "aws_acmpca_certificate_authority": ("aws", "acm_pca"),
    "aws_cognito_user_pool": ("aws", "cognito_idp"),
    "aws_cognito_identity_pool": ("aws", "cognito_sync"),
    "aws_directory_service_directory": ("aws", "directory_service"),
    "aws_guardduty_detector": ("aws", "guardduty"),
    "aws_guardduty_filter": ("aws", "free"),
    # Management / Observability
    "aws_cloudwatch_log_group": ("aws", "cloudwatch"),
    "aws_cloudwatch_log_stream": ("aws", "free"),
    "aws_cloudwatch_metric_alarm": ("aws", "cloudwatch"),
    "aws_cloudwatch_dashboard": ("aws", "free"),
    "aws_cloudtrail": ("aws", "cloudtrail"),
    "aws_config_config_recorder": ("aws", "config_service"),
    "aws_config_rule": ("aws", "config_service"),
    "aws_xray_group": ("aws", "xray"),
    "aws_xray_sampling_rule": ("aws", "free"),
    # Developer Tools
    "aws_codebuild_project": ("aws", "codebuild"),
    "aws_codebuild_report_group": ("aws", "free"),
    "aws_codepipeline": ("aws", "codepipeline"),
    "aws_codedeploy_app": ("aws", "free"),
    "aws_codeartifact_repository": ("aws", "codeartifact"),
    # Business Apps
    "aws_connect_instance": ("aws", "connect"),
    "aws_ses_domain_identity": ("aws", "ses"),
    "aws_ses_configuration_set": ("aws", "free"),
    "aws_workspaces_workspace": ("aws", "workspaces"),
    "aws_workspaces_directory": ("aws", "free"),
    "aws_pinpoint_app": ("aws", "pinpoint"),
    # Media
    "aws_media_convert_queue": ("aws", "mediaconvert"),
    "aws_media_live_channel": ("aws", "medialive"),
    "aws_ivs_channel": ("aws", "ivs"),
    # Other
    "aws_ec2_tag": ("aws", "free"),
    "aws_default_vpc": ("aws", "free"),
    "aws_default_subnet": ("aws", "free"),
    "aws_default_security_group": ("aws", "free"),
    "aws_service_discovery_service": ("aws", "free"),
    "aws_resourcegroups_group": ("aws", "free"),
    "aws_db_event_subscription": ("aws", "free"),
    # Transfer
    "aws_transfer_server": ("aws", "transfer_family"),
    "aws_transfer_user": ("aws", "free"),
    # ECS
    "aws_ecs_task_definition": ("aws", "free"),
    "aws_ecs_cluster": ("aws", "ecs"),
    "aws_ecs_service": ("aws", "ecs"),
    # Lambda
    "aws_lambda_function": ("aws", "lambda"),
    "aws_lambda_event_source_mapping": ("aws", "free"),
    "aws_lambda_function_event_invoke_config": ("aws", "free"),
    # Time/null providers
    "time_sleep": ("aws", "free"),
    "time_offset": ("aws", "free"),
    "null_resource": ("aws", "free"),
    "random_id": ("aws", "free"),
    "random_password": ("aws", "free"),
    "random_string": ("aws", "free"),
    "tls_private_key": ("aws", "free"),
    "local_file": ("aws", "free"),
    "terraform_data": ("aws", "free"),
}

_AZURE_RESOURCE_MAP = {
    "azurerm_virtual_machine": ("azure", "virtual_machines"),
    "azurerm_linux_virtual_machine": ("azure", "virtual_machines"),
    "azurerm_windows_virtual_machine": ("azure", "virtual_machines"),
    "azurerm_virtual_machine_extension": ("azure", "free"),
    "azurerm_managed_disk": ("azure", "managed_disks"),
    "azurerm_snapshot": ("azure", "snapshots"),
    "azurerm_kubernetes_cluster": ("azure", "aks"),
    "azurerm_kubernetes_cluster_node_pool": ("azure", "aks"),
    "azurerm_storage_account": ("azure", "storage_accounts"),
    "azurerm_storage_container": ("azure", "free"),
    "azurerm_storage_blob": ("azure", "free"),
    "azurerm_mssql_database": ("azure", "sql_databases"),
    "azurerm_mssql_server": ("azure", "free"),
    "azurerm_cosmosdb_account": ("azure", "cosmosdb"),
    "azurerm_redis_cache": ("azure", "redis"),
    "azurerm_linux_web_app": ("azure", "app_services"),
    "azurerm_windows_web_app": ("azure", "app_services"),
    "azurerm_app_service": ("azure", "app_services"),
    "azurerm_app_service_plan": ("azure", "app_service_plans"),
    "azurerm_service_plan": ("azure", "app_service_plans"),
    "azurerm_public_ip": ("azure", "public_ips"),
    "azurerm_lb": ("azure", "load_balancers"),
    "azurerm_lb_backend_address_pool": ("azure", "free"),
    "azurerm_lb_rule": ("azure", "free"),
    "azurerm_application_gateway": ("azure", "application_gateways"),
    "azurerm_application_gateway_backend_address_pool": ("azure", "free"),
    "azurerm_nat_gateway": ("azure", "nat_gateways"),
    "azurerm_nat_gateway_public_ip_association": ("azure", "free"),
    "azurerm_key_vault": ("azure", "key_vault"),
    "azurerm_key_vault_secret": ("azure", "free"),
    "azurerm_container_registry": ("azure", "container_registry"),
    "azurerm_service_bus_namespace": ("azure", "service_bus"),
    "azurerm_service_bus_queue": ("azure", "free"),
    "azurerm_service_bus_topic": ("azure", "free"),
    "azurerm_eventhub_namespace": ("azure", "event_hubs"),
    "azurerm_eventhub": ("azure", "free"),
    "azurerm_postgresql_server": ("azure", "postgresql"),
    "azurerm_postgresql_database": ("azure", "free"),
    "azurerm_mysql_server": ("azure", "mysql"),
    "azurerm_mysql_database": ("azure", "free"),
    "azurerm_resource_group": ("azure", "free"),
    "azurerm_virtual_network": ("azure", "free"),
    "azurerm_subnet": ("azure", "free"),
    "azurerm_network_security_group": ("azure", "free"),
    "azurerm_network_interface": ("azure", "free"),
    "azurerm_role_assignment": ("azure", "free"),
    "azurerm_user_assigned_identity": ("azure", "free"),
    # Terraform/Azure provider built-ins
    "azurerm_template_deployment": ("azure", "free"),
}

_GCP_RESOURCE_MAP = {
    "google_compute_instance": ("gcp", "compute_instances"),
    "google_compute_disk": ("gcp", "persistent_disks"),
    "google_compute_address": ("gcp", "static_ips"),
    "google_compute_snapshot": ("gcp", "snapshots"),
    "google_storage_bucket": ("gcp", "gcs_buckets"),
    "google_storage_bucket_object": ("gcp", "free"),
    "google_sql_database_instance": ("gcp", "cloud_sql"),
    "google_sql_database": ("gcp", "free"),
    "google_container_cluster": ("gcp", "gke_clusters"),
    "google_container_node_pool": ("gcp", "gke_clusters"),
    "google_cloudfunctions_function": ("gcp", "cloud_functions"),
    "google_cloud_run_service": ("gcp", "cloud_run"),
    "google_bigquery_dataset": ("gcp", "bigquery_datasets"),
    "google_bigquery_table": ("gcp", "free"),
    "google_spanner_instance": ("gcp", "cloud_spanner"),
    "google_spanner_database": ("gcp", "free"),
    "google_pubsub_topic": ("gcp", "pubsub_topics"),
    "google_pubsub_subscription": ("gcp", "free"),
    "google_dataproc_cluster": ("gcp", "dataproc_clusters"),
    "google_app_engine_standard_app_version": ("gcp", "app_engine"),
    "google_redis_instance": ("gcp", "memorystore_redis"),
    "google_artifact_registry_repository": ("gcp", "artifact_registry"),
    "google_bigtable_instance": ("gcp", "cloud_bigtable"),
    "google_ai_platform_endpoint": ("gcp", "vertex_ai_endpoints"),
    "google_vertex_ai_endpoint": ("gcp", "vertex_ai_endpoints"),
    "google_compute_firewall": ("gcp", "free"),
    "google_compute_network": ("gcp", "free"),
    "google_compute_subnetwork": ("gcp", "free"),
    "google_compute_router": ("gcp", "free"),
    "google_service_account": ("gcp", "free"),
    "google_project_iam_member": ("gcp", "free"),
    "google_project_service": ("gcp", "free"),
    "google_kms_key_ring": ("gcp", "free"),
    "google_kms_crypto_key": ("gcp", "kms"),
    "google_secret_manager_secret": ("gcp", "free"),
    "google_secret_manager_secret_version": ("gcp", "free"),
}

_ALL_RESOURCE_MAP = {}
_ALL_RESOURCE_MAP.update(_AWS_RESOURCE_MAP)
_ALL_RESOURCE_MAP.update(_AZURE_RESOURCE_MAP)
_ALL_RESOURCE_MAP.update(_GCP_RESOURCE_MAP)


def detect_resource(terraform_type: str) -> tuple[str, str]:
    """Map a Terraform/CloudFormation type to (provider, service)."""
    result = _ALL_RESOURCE_MAP.get(terraform_type)
    if result:
        return result
    if terraform_type.startswith("azurerm_"):
        return ("azure", terraform_type.replace("azurerm_", "").split("_")[0])
    if terraform_type.startswith("google_"):
        return ("gcp", terraform_type.replace("google_", "").split("_")[0])
    if terraform_type.startswith("aws_"):
        svc = terraform_type.replace("aws_", "").split("_")[0]
        return ("aws", svc)
    if terraform_type.startswith("AWS::"):
        parts = terraform_type.split("::")
        svc = parts[1].lower() if len(parts) > 1 else "unknown"
        return ("aws", svc)
    return ("aws", terraform_type.split("_")[0])


# ─── Terraform Plan JSON parser ─────────────────────────────────────────────

def parse_tfplan_json(content: str) -> list[dict]:
    """Parse `terraform plan -json` output or `terraform show -json` output.

    This handles 100% of HCL features because Terraform itself does the parsing.
    Supports both planned_values and configuration.resources.
    """
    try:
        plan = _json.loads(content)
    except _json.JSONDecodeError:
        return []

    resources = []
    seen = set()

    def extract_values(r: dict, source_label: str) -> Optional[dict]:
        rtype = r.get("type", "")
        rname = r.get("name", "")
        addr = r.get("address", f"{rtype}.{rname}")
        if addr in seen:
            return None
        seen.add(addr)

        provider, service = detect_resource(rtype)
        if provider == "aws" and service == "free":
            return {
                "type": rtype, "name": rname, "address": addr,
                "config": {"_free": "true"},
                "provider": provider, "service": service,
                "source": f"terraform_plan_{source_label}",
            }

        values = r.get("values", {})
        config = {}
        for k, v in values.items():
            if isinstance(v, (str, int, float, bool)):
                config[k] = str(v)
            elif isinstance(v, (list, dict)):
                try:
                    config[k] = _json.dumps(v)
                except Exception:
                    config[k] = str(v)

        return {
            "type": rtype, "name": rname, "address": addr,
            "config": config,
            "provider": provider, "service": service,
            "source": f"terraform_plan_{source_label}",
        }

    # Extract from planned_values
    pv = plan.get("planned_values", {})
    root = pv.get("root_module", {})

    def walk_module(mod: dict, source_label: str = "plan"):
        for r in mod.get("resources", []):
            extracted = extract_values(r, source_label)
            if extracted:
                resources.append(extracted)
        for child in mod.get("child_modules", []):
            walk_module(child, source_label)

    walk_module(root)

    # If planned_values is empty, try configuration.resources
    if not resources:
        conf = plan.get("configuration", {})
        conf_root = conf.get("root_module", {})
        for r in conf_root.get("resources", []):
            expr = r.get("expr", {})
            config = {}
            for k, v in expr.items():
                if isinstance(v, dict) and "constant_value" in v:
                    config[k] = str(v["constant_value"])
            rtype = r.get("type", "")
            rname = r.get("name", "")
            provider, service = detect_resource(rtype)
            resources.append({
                "type": rtype, "name": rname, "address": f"{rtype}.{rname}",
                "config": config,
                "provider": provider, "service": service,
                "source": "terraform_plan_config",
            })

    return resources


# ─── Improved Terraform HCL parser (regex) ─────────────────────────────────

_TF_RESOURCE_BLOCK_RE = re.compile(
    r'(?:resource|data)\s+"([^"]+)"\s+"([^"]+)"'
    r'(?:\s+count\s*=\s*([^\s{]+))?'
    r'(?:\s+for_each\s*=\s*([^\s{]+))?'
    r'\s*\{',
    re.MULTILINE,
)

_TF_VARIABLE_DEFAULT_RE = re.compile(
    r'variable\s+"([^"]+)"\s*\{(?:[^}]*?)default\s*=\s*"([^"]*)"',
    re.MULTILINE,
)

_TF_MODULE_RE = re.compile(
    r'module\s+"([^"]+)"\s*\{',
    re.MULTILINE,
)


def _balanced_braces(text: str, start: int) -> tuple[str, int]:
    """Extract balanced brace-delimited block from position `start`.

    Handles strings with { } inside them (quoted strings).
    """
    depth = 0
    i = start
    in_string = False
    string_char = None

    if i < len(text) and text[i] == '{':
        depth = 1
        i += 1
    else:
        return "", start

    block_start = i
    while i < len(text) and depth > 0:
        c = text[i]
        if in_string:
            if c == '\\':
                i += 2
                continue
            elif c == string_char:
                in_string = False
        else:
            if c in ('"', "'"):
                in_string = True
                string_char = c
            elif c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
        i += 1

    return text[block_start:i - 1], i


def _extract_nested_config(text: str) -> dict:
    """Extract configuration from HCL block text, handling nested blocks.

    Returns a flat dict of key-value pairs plus nested keys as JSON strings.
    """
    config = {}
    i = 0
    lines = []

    # First pass: split into lines for simple k=v
    # Second pass: handle nested blocks
    while i < len(text):
        line_start = i
        while i < len(text) and text[i] != '\n':
            i += 1
        line = text[line_start:i].strip()
        i += 1
        if not line or line.startswith('#') or line.startswith('//'):
            continue
        lines.append(line)

    # Process lines for key = value patterns and detect nested blocks
    block_buffer = ""
    block_key = None
    brace_depth = 0

    for line in lines:
        stripped = line.strip()

        # Check if this line starts a nested block like `vpc_config {`
        if brace_depth == 0 and '{' in stripped and '=' not in stripped:
            # Could be a nested block
            brace_pos = stripped.find('{')
            potential_key = stripped[:brace_pos].strip()
            if potential_key and not potential_key.startswith('"'):
                block_key = potential_key
                rest = stripped[brace_pos + 1:].strip()
                if rest:
                    block_buffer = rest
                    if '{' in rest:
                        # Count braces to track depth
                        brace_depth = rest.count('{') - rest.count('}')
                    if brace_depth <= 0:
                        _finalize_block(config, block_key, block_buffer)
                        block_key = None
                        block_buffer = ""
                        brace_depth = 0
                    else:
                        brace_depth = rest.count('{') - rest.count('}')
                else:
                    brace_depth = 1
                    block_buffer = ""
                continue

        if brace_depth > 0:
            block_buffer += line + "\n"
            brace_depth += stripped.count('{') - stripped.count('}')
            if brace_depth <= 0 and block_key:
                _finalize_block(config, block_key, block_buffer)
                block_key = None
                block_buffer = ""
                brace_depth = 0
            continue

        if '=' in stripped:
            parts = stripped.split('=', 1)
            key = parts[0].strip()
            val = parts[1].strip()

            # Remove surrounding quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            elif val.startswith('<<'):
                # Heredoc — extract first word
                val = val.strip('"').strip("'")

            # Handle lists and maps
            if val.startswith('[') or val.startswith('{'):
                val = val[:80]  # truncate long expressions

            if key and val:
                config[key] = val

    return config


def _finalize_block(config: dict, key: str, content: str):
    """Store a nested block's content as a JSON string in config."""
    # Extract simple key=value pairs from the block
    sub_config = _extract_nested_config(content)
    if sub_config:
        config[f"_{key}"] = _json.dumps(sub_config)


def parse_terraform_hcl_improved(content: str) -> list[dict]:
    """Improved Terraform HCL parser that handles count/for_each, nested blocks.

    For complex modules, recommend using `terraform plan -json` output instead.
    """
    resources = []

    provider_hint = "aws"
    if 'azurerm_' in content:
        provider_hint = "azure"
    elif 'google_' in content:
        provider_hint = "gcp"

    for match in _TF_RESOURCE_BLOCK_RE.finditer(content):
        resource_type = match.group(1)
        resource_name = match.group(2)
        count_expr = match.group(3)
        for_each_expr = match.group(4)

        brace_start = content.find('{', match.end())
        if brace_start == -1:
            continue

        block_text, _ = _balanced_braces(content, brace_start)
        config = _extract_nested_config(block_text)

        if count_expr:
            config["_count"] = count_expr.strip()
        if for_each_expr:
            config["_for_each"] = for_each_expr.strip()

        provider, service = detect_resource(resource_type)

        resources.append({
            "type": resource_type,
            "name": resource_name,
            "address": f"{resource_type}.{resource_name}",
            "config": config,
            "provider": provider,
            "service": service,
            "source": "terraform_hcl",
        })

    return resources


# ─── CloudFormation parser (enhanced) ──────────────────────────────────────

_CFN_RESOURCE_MAP = {
    "AWS::EC2::Instance": ("ec2", "aws"),
    "AWS::EC2::Volume": ("ec2", "aws"),
    "AWS::EC2::EIP": ("ec2", "aws"),
    "AWS::EC2::NatGateway": ("ec2", "aws"),
    "AWS::EC2::SecurityGroup": ("free", "aws"),
    "AWS::EC2::Subnet": ("free", "aws"),
    "AWS::EC2::VPC": ("free", "aws"),
    "AWS::EC2::InternetGateway": ("free", "aws"),
    "AWS::ECS::Service": ("ecs", "aws"),
    "AWS::ECS::Cluster": ("ecs", "aws"),
    "AWS::ECS::TaskDefinition": ("free", "aws"),
    "AWS::EKS::Cluster": ("eks", "aws"),
    "AWS::EKS::Nodegroup": ("eks", "aws"),
    "AWS::RDS::DBInstance": ("rds", "aws"),
    "AWS::RDS::DBCluster": ("rds", "aws"),
    "AWS::ElastiCache::CacheCluster": ("elasticache", "aws"),
    "AWS::ElastiCache::ReplicationGroup": ("elasticache", "aws"),
    "AWS::S3::Bucket": ("s3", "aws"),
    "AWS::Lambda::Function": ("lambda", "aws"),
    "AWS::DynamoDB::Table": ("dynamodb", "aws"),
    "AWS::DynamoDB::GlobalTable": ("dynamodb", "aws"),
    "AWS::ElasticLoadBalancingV2::LoadBalancer": ("elb", "aws"),
    "AWS::ElasticLoadBalancing::LoadBalancer": ("elb", "aws"),
    "AWS::ElasticLoadBalancingV2::TargetGroup": ("free", "aws"),
    "AWS::EFS::FileSystem": ("efs", "aws"),
    "AWS::Redshift::Cluster": ("redshift", "aws"),
    "AWS::EMR::Cluster": ("emr", "aws"),
    "AWS::EMR::ServerlessApplication": ("emr_serverless", "aws"),
    "AWS::SageMaker::NotebookInstance": ("sagemaker", "aws"),
    "AWS::SageMaker::Endpoint": ("sagemaker", "aws"),
    "AWS::AutoScaling::AutoScalingGroup": ("autoscaling", "aws"),
    "AWS::AutoScaling::LaunchConfiguration": ("free", "aws"),
    "AWS::IAM::Role": ("free", "aws"),
    "AWS::IAM::Policy": ("free", "aws"),
    "AWS::IAM::InstanceProfile": ("free", "aws"),
    "AWS::KMS::Key": ("kms", "aws"),
    "AWS::SecretsManager::Secret": ("secretsmanager", "aws"),
    "AWS::CertificateManager::Certificate": ("acm", "aws"),
    "AWS::CloudFront::Distribution": ("cloudfront", "aws"),
    "AWS::ApiGateway::RestApi": ("apigateway", "aws"),
    "AWS::ApiGatewayV2::Api": ("apigateway", "aws"),
    "AWS::Route53::HostedZone": ("route53", "aws"),
    "AWS::WAFv2::WebACL": ("waf", "aws"),
    "AWS::Logs::LogGroup": ("cloudwatch", "aws"),
    "AWS::SQS::Queue": ("sqs", "aws"),
    "AWS::SNS::Topic": ("sns", "aws"),
    "AWS::Kinesis::Stream": ("kinesis", "aws"),
    "AWS::MSK::Cluster": ("msk", "aws"),
    "AWS::ECS::Service": ("ecs", "aws"),
    "AWS::Elasticsearch::Domain": ("opensearch", "aws"),
    "AWS::OpenSearchService::Domain": ("opensearch", "aws"),
}


def parse_cloudformation(content: str) -> list[dict]:
    """Parse CloudFormation template content (JSON or YAML)."""
    resources = []

    parsed = None
    try:
        parsed = _json.loads(content)
    except _json.JSONDecodeError:
        if _YAML_AVAILABLE:
            try:
                parsed = _yaml.safe_load(content)
            except Exception as e:
                logger.warning("cfn.yaml.parse.error", extra={"error": str(e)})
                return []
        else:
            logger.warning("cfn.parse.error", extra={"detail": "YAML parser not available"})
            return []

    if not parsed or not isinstance(parsed, dict):
        return []

    cfn_resources = parsed.get("Resources", {})
    for logical_id, resource_def in cfn_resources.items():
        if not isinstance(resource_def, dict):
            continue
        rtype = resource_def.get("Type", "")
        props = resource_def.get("Properties", {})
        if not rtype:
            continue

        svc_from_map, provider = _CFN_RESOURCE_MAP.get(rtype, (rtype.split("::")[-1].lower(), "aws"))

        if svc_from_map == "free":
            config = {"_free": "true"}
        else:
            config = {}
            if isinstance(props, dict):
                for k, v in props.items():
                    if isinstance(v, (str, int, float, bool)):
                        config[k] = str(v)
                    elif isinstance(v, list):
                        config[k] = _json.dumps(v)
                    elif isinstance(v, dict):
                        config[k] = _json.dumps(v)

        resources.append({
            "type": rtype,
            "name": logical_id,
            "address": logical_id,
            "config": config,
            "provider": provider,
            "service": svc_from_map if svc_from_map != "free" else "free",
            "source": "cloudformation",
        })

    return resources


# ─── Format detection ──────────────────────────────────────────────────────

def detect_format(content: str) -> str:
    """Auto-detect template format."""
    stripped = content.strip()
    if not stripped:
        return "unknown"

    # Terraform plan JSON?
    if stripped.startswith('{'):
        try:
            parsed = _json.loads(stripped)
            if isinstance(parsed, dict):
                if "planned_values" in parsed or "format_version" in parsed:
                    return "terraform_plan"
                if "Resources" in parsed or "AWSTemplateFormatVersion" in parsed:
                    return "cloudformation"
                if "resource" in parsed.get("terraform", {}):
                    return "terraform"
                return "json"
        except _json.JSONDecodeError:
            pass

    # Terraform HCL?
    if 'resource "' in stripped[:300] or stripped.startswith('# ') or \
       stripped.startswith('terraform {') or stripped.startswith('provider '):
        return "terraform"

    # YAML CloudFormation?
    if _YAML_AVAILABLE:
        try:
            parsed = _yaml.safe_load(stripped)
            if isinstance(parsed, dict):
                if "Resources" in parsed or "AWSTemplateFormatVersion" in parsed:
                    return "cloudformation"
        except Exception:
            pass

    return "unknown"


# ─── Main entry points ─────────────────────────────────────────────────────

def parse_content(content: str, fmt: Optional[str] = None) -> list[dict]:
    """Parse template content with optional explicit format hint."""
    if not fmt or fmt == "auto":
        fmt = detect_format(content)

    if fmt == "terraform_plan":
        return parse_tfplan_json(content)
    elif fmt == "terraform":
        return parse_terraform_hcl_improved(content)
    elif fmt in ("cloudformation", "json", "yaml"):
        return parse_cloudformation(content)
    else:
        logger.warning("parse.unknown_format", extra={"format": fmt})
        return []


def parse_directory(dir_path: str) -> list[dict]:
    """Parse all IaC templates in a local directory.

    Supports .tf, .tf.json, .json, .yaml, .yml, .template files.
    Also looks for terraform plan JSON files (plan.json, tfplan.json).
    """
    all_resources = []

    for root, _dirs, files in os.walk(dir_path):
        for fname in files:
            fpath = os.path.join(root, fname)
            ext = os.path.splitext(fname)[1].lower()
            try:
                with open(fpath) as f:
                    content = f.read()

                # Terraform plan JSON?
                if ext == ".json" and ("planned_values" in content or "format_version" in content):
                    res = parse_tfplan_json(content)
                    all_resources.extend(res)
                    continue

                if ext == ".tf":
                    res = parse_terraform_hcl_improved(content)
                    all_resources.extend(res)
                elif ext == ".tf.json":
                    res = parse_content(content, "terraform_plan")
                    if not res:
                        res = parse_cloudformation(content)
                    all_resources.extend(res)
                elif ext in (".json", ".yaml", ".yml", ".template"):
                    res = parse_content(content, "auto")
                    all_resources.extend(res)

            except Exception as e:
                logger.debug("parse.file.error", extra={"file": fname, "error": str(e)})

    return all_resources


def parse_zip(content: bytes) -> list[dict]:
    """Parse a zip file containing IaC templates."""
    import io
    all_resources = []
    tmpdir = tempfile.mkdtemp(prefix="cost_estimate_zip_")

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(tmpdir)
        all_resources = parse_directory(tmpdir)
    except Exception as e:
        logger.error("zip.parse.error", extra={"error": str(e)})
    finally:
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    return all_resources


def _sanitize_git_url(url: str) -> str:
    """Strip embedded credentials from a git URL."""
    from urllib.parse import urlparse, urlunparse
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in ("http", "https", "git", "ssh"):
        raise ValueError(f"Unsupported git URL scheme: {parsed.scheme}")
    sanitized = parsed._replace(netloc=parsed.hostname or parsed.netloc)
    if parsed.port:
        sanitized = sanitized._replace(netloc=f"{sanitized.hostname}:{parsed.port}")
    return urlunparse(sanitized._replace(params='', query='', fragment=''))


def parse_git_repo(repo_url: str, branch: Optional[str] = None) -> list[dict]:
    """Clone a git repo and parse all IaC templates found within.

    Tries the requested branch first. If that fails (branch not found),
    falls back to the default branch. Scans all supported IaC file types.
    """
    if not _GIT_AVAILABLE:
        logger.warning("git.unavailable", extra={"detail": "gitpython not installed or git CLI missing"})
        return []

    # Strip embedded credentials from URL
    repo_url = _sanitize_git_url(repo_url)

    all_resources = []
    tmpdir = tempfile.mkdtemp(prefix="cost_estimate_")

    try:
        logger.info("git.cloning", extra={"repo": repo_url, "branch": branch or "default"})
        if branch:
            try:
                _git.Repo.clone_from(repo_url, tmpdir, depth=1, branch=branch)
            except Exception:
                logger.info("git.branch_fallback", extra={"repo": repo_url, "branch": branch})
                import shutil
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                tmpdir = tempfile.mkdtemp(prefix="cost_estimate_")
                _git.Repo.clone_from(repo_url, tmpdir, depth=1)
        else:
            _git.Repo.clone_from(repo_url, tmpdir, depth=1)

        all_resources = parse_directory(tmpdir)
    except Exception as e:
        err_str = str(e).lower()
        if "git" in err_str and "not found" in err_str or "executable" in err_str:
            logger.error("git.missing_cli", extra={"detail": "git CLI not found on system PATH"})
        else:
            logger.error("git.clone.error", extra={"repo": repo_url, "error": str(e)})
    finally:
        import shutil
        try:
            shutil.rmtree(tmpdir, ignore_errors=True)
        except Exception:
            pass

    return all_resources
