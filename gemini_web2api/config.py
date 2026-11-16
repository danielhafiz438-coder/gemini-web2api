"""Configuration management."""
import json
import os

DEFAULT_BL = "boq_assistant-bard-web-server_20260716.08_p0"

DEFAULT_CONFIG = {
    "port": 8081,
    "host": "0.0.0.0",
    "retry_attempts": 3,
    "retry_delay_sec": 2,
    "request_timeout_sec": 180,
    # "auto" discovers the live label from gemini.google.com (see bl.py);
    # pin a literal label only when you need to freeze the upstream build.
    "gemini_bl": "auto",
    "bl_cache_sec": 3600,
    "bl_fetch_timeout_sec": 15,
    "auth_user": None,
    "xsrf_token": None,
    "default_model": "gemini-3.6-flash",
    "log_requests": True,
    "cookie_file": None,
    "proxy": None,
    "api_keys": [],
    "temporary_chats": False,
    # Custom models: {"name": {"mode": 1, "think": 4, "desc": "..."}}
    "models": {},
}


CONFIG = dict(DEFAULT_CONFIG)


def load_config(path: str = None):
    """Load config from JSON file."""
    if path and os.path.exists(path):
        with open(path) as f:
            CONFIG.update(json.load(f))
    return CONFIG


def find_config():
    """Search for config file in standard locations."""
    for p in ["./config.json", os.path.expanduser("~/.config/gemini-web2api/config.json")]:
        if os.path.exists(p):
            return p
    return None
