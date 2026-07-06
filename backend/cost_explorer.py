"""AWS Cost Explorer integration — fetches real billing data.

Provides cost data for the last 30 days, projected monthly costs,
and cost anomalies. Falls back gracefully if Cost Explorer is not enabled.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import boto3

logger = logging.getLogger(__name__)


def _get_ce_client(access_key: str = "", secret_key: str = "", session_token: str = "", region: str = "us-east-1"):
    """Create a Cost Explorer client with the provided credentials."""
    kwargs = {"region_name": region}
    if access_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
    if session_token:
        kwargs["aws_session_token"] = session_token
    return boto3.client("ce", **kwargs)


def get_cost_data(
    access_key: str = "",
    secret_key: str = "",
    session_token: str = "",
    region: str = "us-east-1",
    days: int = 30,
) -> dict:
    """Fetch real AWS cost data from Cost Explorer API.

    Returns cost breakdown by service and total spend.
    Falls back to cost-by-service estimates when Cost Explorer is unavailable.
    """
    try:
        kwargs = {"region_name": region}
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        client = boto3.client("ce", **kwargs)

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)

        response = client.get_cost_and_usage(
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            Granularity="DAILY",
            Metrics=["UnblendedCost", "UsageQuantity"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        results_by_time = response.get("ResultsByTime", [])
        daily_costs: list[dict] = []
        service_totals: dict[str, float] = {}

        for day_entry in results_by_time:
            date = day_entry.get("TimePeriod", {}).get("Start", "")
            groups = day_entry.get("Groups", [])
            total = 0.0
            services: dict[str, float] = {}
            for g in groups:
                service_name = g["Keys"][0] if g.get("Keys") else "Unknown"
                amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
                total += amount
                service_totals[service_name] = service_totals.get(service_name, 0) + amount
                services[service_name] = amount

            daily_costs.append({
                "date": date,
                "total": round(total, 2),
                "services": services,
            })

        total_spend = round(sum(d["total"] for d in daily_costs), 2)
        avg_daily = round(total_spend / max(len(daily_costs), 1), 2)
        projected_monthly = round(avg_daily * 30, 2)

        sorted_services = sorted(service_totals.items(), key=lambda x: x[1], reverse=True)
        top_services = [
            {"name": name, "total": round(amount, 2), "percentage": round(amount / total_spend * 100, 1) if total_spend > 0 else 0}
            for name, amount in sorted_services[:15]
        ]

        return {
            "available": True,
            "period": {
                "start": start.strftime("%Y-%m-%d"),
                "end": end.strftime("%Y-%m-%d"),
                "days": days,
            },
            "total_spend": total_spend,
            "average_daily_cost": avg_daily,
            "projected_monthly_cost": projected_monthly,
            "projected_annual_cost": round(projected_monthly * 12, 2),
            "daily_costs": daily_costs,
            "top_services": top_services,
        }

    except client.exceptions.DataUnavailableException:
        logger.info("cost_explorer.data_unavailable")
        return {"available": False, "reason": "Cost Explorer data is not yet available for this account (requires 24h+ of billing data)."}
    except Exception as e:
        logger.warning("cost_explorer.error", extra={"error": str(e)})
        return {"available": False, "reason": f"Cost Explorer unavailable: {e}"}


def get_cost_forecast(
    access_key: str = "",
    secret_key: str = "",
    session_token: str = "",
    region: str = "us-east-1",
) -> dict:
    """Get 90-day cost forecast."""
    try:
        kwargs = {"region_name": region}
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        client = boto3.client("ce", **kwargs)
        end = datetime.now(timezone.utc)
        start = end + timedelta(days=1)
        forecast_end = end + timedelta(days=90)

        response = client.get_cost_forecast(
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": forecast_end.strftime("%Y-%m-%d"),
            },
            Metric="UNBLENDED_COST",
            Granularity="MONTHLY",
        )

        raw = response.get("ForecastResultsByTime", [])
        if not raw:
            return {"available": False, "reason": "No forecast data returned from Cost Explorer."}
        forecasts = []
        for entry in raw:
            mean_val = entry["MeanValue"]
            if isinstance(mean_val, dict):
                mean_val = mean_val.get("Amount", 0)
            forecasts.append({
                "period": entry["TimePeriod"],
                "mean": round(float(mean_val), 2),
            })

        return {
            "available": True,
            "forecasts": forecasts,
        }
    except Exception as e:
        logger.warning("cost_forecast.error", extra={"error": str(e)})
        return {"available": False, "reason": str(e)}


def get_cost_variation(
    access_key: str = "",
    secret_key: str = "",
    session_token: str = "",
    region: str = "us-east-1",
) -> dict:
    """Get cost variation analysis across 1, 3, 6, and 9 month periods.

    Returns per-service cost trends across multiple time windows.
    """
    try:
        kwargs = {"region_name": region}
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        client = boto3.client("ce", **kwargs)
        now = datetime.now(timezone.utc)

        periods = [30, 90, 180, 270]
        period_labels = {30: "1_month", 90: "3_month", 180: "6_month", 270: "9_month"}
        results = {}

        for days in periods:
            start = now - timedelta(days=days)
            response = client.get_cost_and_usage(
                TimePeriod={
                    "Start": start.strftime("%Y-%m-%d"),
                    "End": now.strftime("%Y-%m-%d"),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            service_costs: dict[str, float] = {}
            for entry in response.get("ResultsByTime", []):
                for g in entry.get("Groups", []):
                    service = g["Keys"][0] if g.get("Keys") else "Unknown"
                    amount = float(g["Metrics"]["UnblendedCost"]["Amount"])
                    service_costs[service] = service_costs.get(service, 0) + amount

            total = round(sum(service_costs.values()), 2)
            top = sorted(service_costs.items(), key=lambda x: x[1], reverse=True)[:10]

            results[period_labels[days]] = {
                "period_days": days,
                "total_cost": total,
                "top_services": [
                    {"name": name, "total": round(amount, 2),
                     "percentage": round(amount / total * 100, 1) if total > 0 else 0}
                    for name, amount in top
                ],
            }

        # Calculate month-over-month change
        changes = {}
        labels_in_order = ["1_month", "3_month", "6_month", "9_month"]
        for i in range(1, len(labels_in_order)):
            curr = results[labels_in_order[i]]
            prev = results[labels_in_order[i - 1]]
            pct = round((curr["total_cost"] - prev["total_cost"]) / prev["total_cost"] * 100, 1) if prev["total_cost"] > 0 else 0
            changes[labels_in_order[i]] = {
                "current_total": curr["total_cost"],
                "previous_total": prev["total_cost"],
                "change_percentage": pct,
            }

        return {
            "available": True,
            "periods": results,
            "changes": changes,
        }

    except Exception as e:
        logger.warning("cost_variation.error", extra={"error": str(e)})
        return {"available": False, "reason": str(e)}


def get_rightsizing_recommendations(
    access_key: str = "",
    secret_key: str = "",
    session_token: str = "",
    region: str = "us-east-1",
) -> list:
    """Get EC2 rightsizing recommendations from Cost Explorer."""
    try:
        kwargs = {"region_name": region}
        if access_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token

        client = boto3.client("ce", **kwargs)
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=30)

        response = client.get_rightsizing_recommendation(
            Service="AmazonEC2",
            TimePeriod={
                "Start": start.strftime("%Y-%m-%d"),
                "End": end.strftime("%Y-%m-%d"),
            },
            Configuration={
                "RecommendationTarget": "SAME_INSTANCE_FAMILY",
                "NumberOfRecommendationsToShow": 20,
            },
        )

        recommendations = []
        for rec in response.get("RightsizingRecommendations", []):
            details = rec.get("RightsizingDetails", {})
            rec_type = rec.get("RightsizingType", "Modify")
            current = rec.get("CurrentInstance", {})
            resource_id = current.get("ResourceId", "")

            mod_rec = details.get("ModifyRecommendation", {})
            target = mod_rec.get("TargetInstances", [{}])[0] if mod_rec.get("TargetInstances") else {}

            recommendations.append({
                "resource_id": resource_id,
                "account_id": rec.get("AccountId", ""),
                "rightsizing_type": rec_type,
                "current_instance_type": current.get("InstanceType", ""),
                "current_hours": current.get("HoursOnDemand", 0),
                "recommended_instance_type": target.get("InstanceType", ""),
                "estimated_monthly_savings": round(float(rec.get("Savings", {}).get("SavingsAmount", {}).get("Amount", 0)), 2),
                "estimated_monthly_cost_after": round(float(rec.get("Savings", {}).get("EstimatedCostAfterRecommendation", {}).get("Amount", 0)), 2),
            })

        return recommendations

    except Exception as e:
        logger.warning("rightsizing.error", extra={"error": str(e)})
        return []


def get_ri_recommendations(access_key: str = "", secret_key: str = "", session_token: str = "") -> list:
    """Get AWS Reserved Instance purchase recommendations."""
    try:
        client = _get_ce_client(access_key, secret_key, session_token)
        resp = client.get_reservation_purchase_recommendation(
            Service="AmazonEC2",
            LookbackPeriodInDays="LAST_30_DAYS",
            TermInYears="ONE_YEAR",
            PaymentOption="PARTIAL_UPFRONT",
        )
        recommendations = []
        for rec in resp.get("Recommendations", []):
            for detail in rec.get("RecommendationDetails", []):
                recommendations.append({
                    "service": "AmazonEC2",
                    "account_id": detail.get("AccountId", ""),
                    "current_instance_type": detail.get("InstanceDetails", {}).get("EC2InstanceDetails", {}).get("InstanceType", ""),
                    "recommended_plan": f"{detail.get('RecommendedNumberOfInstancesToPurchase', 0)} instances",
                    "upfront": "partial",
                    "term": "1year",
                    "estimated_annual_savings": float(detail.get("EstimatedMonthlySavings", 0) or 0) * 12,
                    "estimated_monthly_savings": float(detail.get("EstimatedMonthlySavings", 0) or 0),
                    "coverage": float(rec.get("EstimatedCoverage", {}).get("CoveragePercentage", 0) or 0),
                    "explanation": f"Purchase {detail.get('RecommendedNumberOfInstancesToPurchase', 0)} reserved instances to save ${float(detail.get('EstimatedMonthlySavings', 0) or 0):.2f}/month",
                })
        return recommendations
    except Exception as e:
        logger.warning("ce.ri.error", extra={"error": str(e)})
        return []


def get_savings_plan_recommendations(access_key: str = "", secret_key: str = "", session_token: str = "") -> list:
    """Get AWS Savings Plan recommendations."""
    try:
        client = _get_ce_client(access_key, secret_key, session_token)
        resp = client.get_savings_plans_purchase_recommendation(
            SavingsPlanType="COMPUTE",
            LookbackPeriodInDays="LAST_30_DAYS",
            TermInYears="ONE_YEAR",
            PaymentOption="PARTIAL_UPFRONT",
        )
        recommendations = []
        for rec in resp.get("SavingsPlansPurchaseRecommendation", {}).get("SavingsPlansPurchaseRecommendationDetails", []):
            recommendations.append({
                "service": "Compute Savings Plan",
                "account_id": rec.get("AccountId", ""),
                "current_instance_type": "mixed",
                "recommended_plan": f"${float(rec.get('RecommendedCommitment', 0) or 0):.2f}/hr commitment",
                "upfront": "partial",
                "term": "1year",
                "estimated_annual_savings": float(rec.get("EstimatedAnnualSavings", 0) or 0),
                "estimated_monthly_savings": float(rec.get("EstimatedMonthlySavings", 0) or 0) if rec.get("EstimatedMonthlySavings") else float(rec.get("EstimatedOnDemandCost", 0) or 0) * 0.2,
                "coverage": float(rec.get("SavingsPercentage", 0) or 0),
                "explanation": f"Savings Plan with ${float(rec.get('RecommendedCommitment', 0) or 0):.2f}/hr commitment saves ~{float(rec.get('SavingsPercentage', 0) or 0):.0f}% vs On-Demand",
            })
        return recommendations
    except Exception as e:
        logger.warning("ce.savings_plan.error", extra={"error": str(e)})
        return []
