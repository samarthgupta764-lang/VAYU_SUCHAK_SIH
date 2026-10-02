"""
Entry point — `python run.py`.

Starts uvicorn serving app.main:app. The browser console at http://HOST:PORT is
the operator shell; pywebview is an optional ~15-line wrapper for later (kept out
so a fresh machine needs nothing but pip + `playwright install chromium`).

PORT / HOST env vars win over the config default, so a harness that assigns a
port (hosted previews, containers, PaaS) just works.
"""

from __future__ import annotations

import os

import uvicorn

from config import settings

if __name__ == "__main__":
    host = os.environ.get("HOST", settings.host)
    port = int(os.environ.get("PORT", settings.port))
    print(f"VAYU-SUCHAK 2.0  ·  http://{host}:{port}")
    print(f"  postgres      : {'on' if settings.postgres_enabled else 'off (SQLite fallback)'}")
    print(f"  travelpayouts : {'on' if settings.travelpayouts_enabled else 'off (cache tier only)'}")
    uvicorn.run("app.main:app", host=host, port=port, reload=False)
