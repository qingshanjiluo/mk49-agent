"""Configuration loader: config.json < environment < defaults.

LLM/image keys are discovered from environment variables, config.json, or an
external litellm .env file. Real keys are never written into this repository.
"""

import json
import os

DEFAULT_BASE_URL = "https://forum.mk49.top/bbs"

# Candidate locations of a litellm .env holding upstream channel keys.
LITELLM_ENV_CANDIDATES = [
    r"G:\皮皮\编程项目\05_应用与平台\litellm\.env",
]

DEFAULTS = {
    "base_url": DEFAULT_BASE_URL,
    "username": "",
    "password": "",
    "target_categories": [2],
    "scan_interval": 600,
    "max_threads_per_cycle": 15,
    "daily_post_limit": 3,
    "comment_probability": 0.6,
    "like_probability": 0.3,
    "welcome_newcomers": True,
    "enable_image_posts": True,
    "image_provider": "pollinations",
    "llm_model": "agnes-2.5-flash",
    "state_file": "state/agent_state.json",
}


def _load_env_file(path):
    out = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                out[key.strip()] = val.strip().strip("'").strip('"')
    except OSError:
        pass
    return out


def load_config(path="config.json"):
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg.update({k: v for k, v in json.load(fh).items() if v is not None})
        except (OSError, ValueError) as exc:
            print("[config] failed to read %s: %s" % (path, exc))

    # environment overrides — only explicit MK49_* / BOT_* variables may
    # override config.json (plain USERNAME/PASSWORD are OS account names and
    # must never shadow the forum credentials).
    for key in list(DEFAULTS):
        env_val = os.getenv("MK49_" + key.upper())
        if env_val is not None:
            cfg[key] = env_val
    if os.getenv("BOT_USERNAME"):
        cfg["username"] = os.getenv("BOT_USERNAME")
    if os.getenv("BOT_PASSWORD"):
        cfg["password"] = os.getenv("BOT_PASSWORD")

    # coerce list/int/float fields that may arrive as strings
    if isinstance(cfg.get("target_categories"), str):
        cfg["target_categories"] = [
            int(x) for x in cfg["target_categories"].split(",") if x.strip()
        ]
    for key in ("scan_interval", "max_threads_per_cycle", "daily_post_limit"):
        cfg[key] = int(cfg[key])
    for key in ("comment_probability", "like_probability"):
        cfg[key] = float(cfg[key])
    return cfg


def load_llm_env():
    """Merge LLM related env vars from the process and litellm .env files."""
    merged = {}
    for cand in LITELLM_ENV_CANDIDATES:
        if os.path.exists(cand):
            merged.update(_load_env_file(cand))
    merged.update(
        {k: v for k, v in os.environ.items() if "API_KEY" in k or k.endswith(("_BASE_URL", "_MODEL"))}
    )
    return merged
