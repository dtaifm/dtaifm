"""Teacher diagnostics for the `dtaifm teachers` command.

Reports metadata for every registered teacher (kind, base URL, env vars,
install hints). When ``check=True``, pings local HTTP adapters at their
configured base URLs and reports reachable/offline. The HTTP client is
injectable so tests never touch the network.
"""

from __future__ import annotations

import os
from typing import Any

from dtaifm.teacher.registry import available_teachers


_LOCAL_PROVIDERS = {
    "ollama": {
        "default_base_url": "http://localhost:11434",
        "env_var": "DTAIFM_OLLAMA_BASE_URL",
        "check_path": "/api/tags",
        "models_key": "models",
        "model_id_field": "name",
    },
    "lemonade": {
        "default_base_url": "http://localhost:13305",
        "env_var": "DTAIFM_LEMONADE_BASE_URL",
        "check_path": "/v1/models",
        "models_key": "data",
        "model_id_field": "id",
    },
}


def describe_teacher(name: str, *, check: bool = False, http_client: Any | None = None) -> dict:
    info: dict = {"name": name}

    if name in _LOCAL_PROVIDERS:
        cfg = _LOCAL_PROVIDERS[name]
        base_url = (os.environ.get(cfg["env_var"]) or cfg["default_base_url"]).rstrip("/")
        info.update({
            "kind": "local_http",
            "base_url": base_url,
            "default_base_url": cfg["default_base_url"],
            "base_url_env": cfg["env_var"],
        })
        if check:
            info.update(_check_local_endpoint(base_url + cfg["check_path"], cfg, http_client))
        else:
            info["status"] = "registered"
    elif name == "anthropic":
        info.update({
            "kind": "cloud_sdk",
            "requires_env": "ANTHROPIC_API_KEY",
            "requires_extra": "dtaifm[anthropic]",
            "status": "registered",
        })
    else:
        info.update({"kind": "builtin", "status": "registered"})

    return info


def describe_all(*, check: bool = False, http_client: Any | None = None) -> list[dict]:
    return [describe_teacher(name, check=check, http_client=http_client) for name in available_teachers()]


def format_teachers_text(infos: list[dict]) -> str:
    lines = ["Registered teachers:", ""]
    for info in infos:
        name = info["name"]
        kind = info.get("kind", "unknown")
        lines.append(f"  {name}  [{kind}]")
        if "base_url" in info:
            lines.append(f"      base_url:     {info['base_url']}")
            lines.append(f"      override env: {info['base_url_env']}")
            if "status" in info:
                lines.append(f"      status:       {info['status']}")
            if info.get("endpoint"):
                lines.append(f"      checked:      {info['endpoint']}")
            if "models" in info:
                models = info["models"]
                if models:
                    lines.append(f"      models:       {', '.join(models)}")
                else:
                    lines.append("      models:       (none returned)")
            if info.get("error"):
                lines.append(f"      error:        {info['error']}")
        else:
            if "requires_env" in info:
                lines.append(f"      requires env: {info['requires_env']}")
            if "requires_extra" in info:
                lines.append(f"      requires:     pip install '{info['requires_extra']}'")
            if "status" in info:
                lines.append(f"      status:       {info['status']}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ----------------------------------------------------------------------
# internal
# ----------------------------------------------------------------------

def _check_local_endpoint(url: str, cfg: dict, http_client: Any | None) -> dict:
    """Ping a local HTTP endpoint. Returns offline info on any error — never raises."""
    client = http_client
    if client is None:
        # Import here so unused diagnostics don't pull in urllib state.
        from dtaifm.teacher.adapters._http import HttpJsonClient
        client = HttpJsonClient(timeout=5.0)

    try:
        response = client.get(url)
    except (OSError, ValueError) as exc:
        return {"status": "offline", "endpoint": url, "error": str(exc)}

    result: dict = {"status": "reachable", "endpoint": url}
    if isinstance(response, dict):
        models_list = response.get(cfg["models_key"], [])
        if isinstance(models_list, list):
            field = cfg["model_id_field"]
            names = [m.get(field) for m in models_list if isinstance(m, dict) and m.get(field)]
            result["models"] = names
    return result
