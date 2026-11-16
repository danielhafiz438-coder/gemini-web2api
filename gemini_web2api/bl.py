"""Gemini Web build label ("bl") discovery.

Google rejects requests carrying a stale ``bl`` query parameter. Upstream
hard-codes one in ``config.py``, so every Gemini Web deploy that bumps the
label breaks the proxy until someone edits the constant by hand.

The live label is published in the app page's ``WIZ_global_data`` object as
``cfb2h``, so we read it from there instead and cache it.
"""
import re
import threading
import time
import urllib.request

from .config import CONFIG, DEFAULT_BL

#: Matches both label families seen upstream:
#:   boq_assistant-bard-web-server_20260716.08_p0
#:   boq_gemini-web-uiserver_20261012.19_p1
BL_RE = re.compile(r"boq_[A-Za-z0-9._\-]+_\d{8}\.\d+_p\d+")
_CFB2H_RE = re.compile(r'"cfb2h"\s*:\s*"([^"]+)"')

_APP_URL = "https://gemini.google.com/app"
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

_cache = {"bl": None, "ts": 0.0, "source": None, "error": None}
_lock = threading.Lock()


def parse_bl(text: str):
    """Extract a build label from page HTML or a JS bundle. Returns None if absent."""
    if not text:
        return None
    m = _CFB2H_RE.search(text)
    if m and BL_RE.fullmatch(m.group(1)):
        return m.group(1)
    m = BL_RE.search(text)
    return m.group(0) if m else None


def fetch_bl(timeout: int = 15):
    """Fetch the app page and return its build label, or None on failure."""
    req = urllib.request.Request(
        _APP_URL,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    bl = parse_bl(body)
    if not bl:
        # Label may live in a referenced bundle rather than the shell page.
        for src in re.findall(r'src="([^"]+\.js)"', body)[:10]:
            url = src if src.startswith("http") else "https://gemini.google.com" + src
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": _UA})
                with urllib.request.urlopen(req2, timeout=timeout) as r2:
                    bl = parse_bl(r2.read().decode("utf-8", errors="replace"))
                if bl:
                    break
            except Exception:
                continue
    return bl


def get_bl(force: bool = False) -> str:
    """Return the build label to send upstream.

    An explicit ``gemini_bl`` in config wins. Otherwise the label is discovered
    and cached for ``bl_cache_sec`` seconds, falling back to the last known
    good value and finally to the packaged default.
    """
    configured = (CONFIG.get("gemini_bl") or "").strip()
    if configured and configured.lower() != "auto":
        return configured

    ttl = int(CONFIG.get("bl_cache_sec", 3600))
    with _lock:
        fresh = _cache["bl"] and (time.time() - _cache["ts"]) < ttl
        if fresh and not force:
            return _cache["bl"]

    try:
        bl = fetch_bl(int(CONFIG.get("bl_fetch_timeout_sec", 15)))
    except Exception as e:  # network down, Google changed the page, ...
        bl = None
        _cache["error"] = f"{type(e).__name__}: {e}"

    with _lock:
        if bl:
            _cache.update({"bl": bl, "ts": time.time(), "source": "discovered", "error": None})
            return bl
        if _cache["bl"]:
            # Keep serving the last good label; it usually outlives one bad fetch.
            _cache["ts"] = time.time()
            return _cache["bl"]
        _cache.update({"bl": DEFAULT_BL, "ts": time.time(), "source": "default"})
        return DEFAULT_BL


def invalidate():
    """Drop the cached label so the next call re-discovers it (call after a 400)."""
    with _lock:
        _cache["ts"] = 0.0


def status() -> dict:
    """Diagnostics for /healthz.

    Reads the cache under the lock, but resolves the label outside it: get_bl()
    takes the same non-reentrant lock and would otherwise deadlock.
    """
    with _lock:
        bl_val, source, ts, err = _cache["bl"], _cache["source"], _cache["ts"], _cache["error"]
    if not bl_val:
        bl_val = get_bl()
        with _lock:
            source, ts, err = _cache["source"], _cache["ts"], _cache["error"]
    return {
        "bl": bl_val,
        "source": source or "unknown",
        "age_sec": int(time.time() - ts) if ts else None,
        "last_fetch_error": err,
    }
