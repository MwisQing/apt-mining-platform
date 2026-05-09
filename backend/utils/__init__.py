import yaml
import os

_config = {}
_apt_dict = {}
_advanced_crime = {}
_noise_family = {}


def _flatten_orgs(orgs):
    result = {}
    for org in orgs:
        canonical = org.get("canonical", "")
        tier = org.get("tier", None)
        aliases = org.get("aliases", [])
        for alias in aliases:
            result[alias.lower()] = {"canonical": canonical, "tier": tier}
        if canonical:
            result[canonical.lower()] = {"canonical": canonical, "tier": tier}
    return result


def _project_root():
    """Get project root directory (parent of backend/)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_config():
    global _config
    cfg_path = os.path.join(_project_root(), "config", "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        _config = yaml.safe_load(f)
    return _config


def save_config(cfg):
    global _config
    cfg_path = os.path.join(_project_root(), "config", "config.yaml")
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    _config = cfg
    return _config


def get_config():
    if not _config:
        load_config()
    return _config


def get_path(key):
    cfg = get_config()
    path = cfg.get("paths", {}).get(key, "")
    if not os.path.isabs(path):
        path = os.path.join(_project_root(), path)
    return path


def load_apt_dicts():
    global _apt_dict, _advanced_crime, _noise_family
    apt_path = get_path("dict_apt")
    crime_path = get_path("dict_crime")
    noise_path = get_path("dict_noise")

    if os.path.exists(apt_path):
        with open(apt_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _apt_dict = _flatten_orgs(data.get("organizations", []))

    if os.path.exists(crime_path):
        with open(crime_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        _advanced_crime = _flatten_orgs(data.get("organizations", []))

    if os.path.exists(noise_path):
        with open(noise_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        families = data.get("families", {})
        _noise_family = set()
        for family_aliases in families.values():
            for alias in (family_aliases or []):
                _noise_family.add(alias.lower())


def get_apt_dict():
    if not _apt_dict:
        load_apt_dicts()
    return _apt_dict


def get_advanced_crime():
    if not _advanced_crime:
        load_apt_dicts()
    return _advanced_crime


def get_noise_family():
    if not _noise_family:
        load_apt_dicts()
    return _noise_family


def reload_dicts():
    load_config()
    load_apt_dicts()
