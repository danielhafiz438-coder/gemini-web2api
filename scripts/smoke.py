"""End-to-end smoke test against a running gemini-web2api server.

Usage: python scripts/smoke.py [base_url]
Exit code 0 = healthy, 1 = failure. Safe to run in CI against localhost.
"""
import json
import sys
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8081").rstrip("/")


def get(path, timeout=30):
    with urllib.request.urlopen(BASE + path, timeout=timeout) as r:
        return json.loads(r.read().decode())


def post(path, payload, timeout=180):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def main():
    health = get("/healthz")
    bl = health["build_label"]
    print(f"healthz  ok  version={health['version']} bl={bl['bl']} ({bl['source']})")

    body = json.loads(post("/v1/chat/completions", {
        "model": health["default_model"],
        "messages": [{"role": "user", "content": "Reply with the single word: PONG"}],
    }))
    text = body["choices"][0]["message"]["content"] or ""
    print(f"chat     ok  model={body['model']} content={text[:60]!r}")
    if not text.strip():
        raise SystemExit("empty chat completion")

    raw = post("/v1/chat/completions", {
        "model": health["default_model"],
        "stream": True,
        "messages": [{"role": "user", "content": "Count 1 to 3."}],
    })
    if "data: [DONE]" not in raw:
        raise SystemExit("stream did not terminate with [DONE]")
    if '"error"' in raw:
        raise SystemExit(f"stream reported an error: {raw[-300:]}")
    chunks = raw.count("data: ")
    print(f"stream   ok  chunks={chunks}")
    print("PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FAIL: {type(e).__name__}: {e}")
        raise SystemExit(1)
