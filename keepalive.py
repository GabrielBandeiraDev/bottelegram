#!/usr/bin/env python3
"""
Pinga /health do app no Render.
Use fora do Render (cron local, cron-job.org, etc.) ou: python keepalive.py
"""
import os
import sys
import urllib.request

URL = os.getenv(
    "RENDER_HEALTH_URL",
    "https://SUBSTITUA.onrender.com/health",
)
TIMEOUT = int(os.getenv("HEALTH_TIMEOUT", "30"))


def main():
    try:
        req = urllib.request.Request(URL, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")[:200]
            print(f"OK {resp.status} — {body}")
    except Exception as e:
        print(f"Falhou: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
