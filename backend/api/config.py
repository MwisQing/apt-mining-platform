from typing import Any

from fastapi import APIRouter, Body
from backend.utils import get_config, reload_dicts, get_path, save_config
from backend.services.snapshot_builder import request_snapshot_refresh

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config_api():
    cfg = get_config()
    paths = cfg.get("paths", {})
    rules = cfg.get("rules", {})
    badges = cfg.get("badges", {}).get("enabled", [])
    return {
        "trace_ttl_days": rules.get("trace_ttl_days", 30),
        "default_hide_traced": rules.get("default_hide_traced", True),
        "default_hide_closed": rules.get("default_hide_closed_events", True),
        "dict_apt": paths.get("dict_apt", ""),
        "dict_crime": paths.get("dict_crime", ""),
        "dict_noise": paths.get("dict_noise", ""),
        "db_path": paths.get("db", ""),
        "badges": badges,
    }


@router.post("/reload")
def reload_config_api():
    reload_dicts()
    return {"ok": True}


@router.get("/dicts")
def get_dicts():
    from backend.utils import get_apt_dict, get_advanced_crime, get_noise_family
    return {
        "apt_dict": get_apt_dict(),
        "advanced_crime": get_advanced_crime(),
        "noise_family": list(get_noise_family()),
    }


@router.post("")
def save_config_api(data: Any = Body(...)):
    cfg = get_config()
    rules = cfg.setdefault("rules", {})
    badges_cfg = cfg.setdefault("badges", {})

    if "trace_ttl_days" in data:
        rules["trace_ttl_days"] = int(data["trace_ttl_days"])
    if "default_hide_traced" in data:
        rules["default_hide_traced"] = bool(data["default_hide_traced"])
    if "default_hide_closed" in data:
        rules["default_hide_closed_events"] = bool(data["default_hide_closed"])
    if "badges" in data and isinstance(data["badges"], list):
        badges_cfg["enabled"] = data["badges"]

    save_config(cfg)
    reload_dicts()
    request_snapshot_refresh("config")
    return get_config_api()
