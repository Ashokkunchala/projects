"""AWS scanner package — shared helpers and scanner modules."""

import datetime
import logging
from typing import Callable, Optional

from cloud_organizations import AccountCredentials

logger = logging.getLogger(__name__)


def tag(resource: dict, key: str) -> str:
    for t in resource.get("Tags", []):
        if t.get("Key") == key:
            return t.get("Value", "")
    return ""


def tags(resource: dict) -> dict:
    return {t["Key"]: t["Value"] for t in resource.get("Tags", [])}


def dt(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def age(dt_value) -> int:
    if dt_value is None:
        return 0
    now = datetime.datetime.now(dt_value.tzinfo)
    return (now - dt_value).days


def base(type_: str, id_: str, name: str, region: str, creds: AccountCredentials) -> dict:
    return {
        "type": type_,
        "id": id_,
        "name": name or id_,
        "region": region,
        "account_id": creds.account_id,
        "account_name": creds.account_name,
    }


from .kubernetes import scan_kubernetes
