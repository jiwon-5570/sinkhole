from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import threading
import time
from typing import Any
from uuid import uuid4
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _request(url: str, username: str | None = None, password: str | None = None) -> tuple[int, dict[str, Any]]:
    request = Request(url)
    if username is not None and password is not None:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")

    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return int(exc.code), json.loads(raw) if raw else {}


def _post_json(
    url: str,
    payload: dict[str, Any],
    username: str | None = None,
    password: str | None = None,
) -> tuple[int, dict[str, Any]]:
    request = Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    if username is not None and password is not None:
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")

    try:
        with urlopen(request, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return int(exc.code), json.loads(raw) if raw else {}


def main() -> None:
    username = "smoke"
    password = "check"

    workspace_tmp = Path(__file__).resolve().parents[1] / "db" / "tmp"
    workspace_tmp.mkdir(parents=True, exist_ok=True)
    temp_path = workspace_tmp / f"smoke-{os.getpid()}-{uuid4().hex}"
    temp_path.mkdir(parents=True, exist_ok=False)

    try:
        os.environ.update(
            {
                "SINKHOLE_ENV": "test",
                "SINKHOLE_DB_PATH": str(temp_path / "app.db"),
                "SINKHOLE_REPORTS_DIR": str(temp_path / "reports"),
                "SINKHOLE_RELOAD": "0",
                "SINKHOLE_APPLY_SCHEMA_ON_START": "1",
                "SINKHOLE_SEED_DEMO": "0",
                "SINKHOLE_ANALYZE_ON_START": "1",
                "SINKHOLE_ENABLE_BASIC_AUTH": "1",
                "SINKHOLE_BASIC_AUTH_USERNAME": username,
                "SINKHOLE_BASIC_AUTH_PASSWORD": password,
                "SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY": "0",
            }
        )

        import uvicorn

        from app.main import app

        port = _free_port()
        server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()

        base_url = f"http://127.0.0.1:{port}"
        try:
            deadline = time.time() + 20
            last_error: Exception | None = None
            while time.time() < deadline:
                try:
                    status, payload = _request(f"{base_url}/api/health")
                    if status == 200 and payload.get("success"):
                        break
                except (ConnectionError, URLError) as exc:
                    last_error = exc
                time.sleep(0.2)
            else:
                raise RuntimeError(f"server did not become healthy: {last_error}")

            status, _ = _request(f"{base_url}/api/regions")
            if status != 401:
                raise RuntimeError(f"expected unauthenticated /api/regions to return 401, got {status}")

            status, payload = _request(f"{base_url}/api/regions", username, password)
            rows = payload.get("data") or []
            if status != 200 or not payload.get("success") or rows:
                raise RuntimeError("authenticated /api/regions should return no demo rows in real-data smoke check")

            status, payload = _request(f"{base_url}/api/app-config", username, password)
            config = payload.get("data") or {}
            if status != 200 or config.get("google_maps_api_key"):
                raise RuntimeError("app config exposed a Google Maps API key during smoke check")
        finally:
            server.should_exit = True
            thread.join(timeout=5)
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)

    print("OK: smoke check passed")


if __name__ == "__main__":
    main()
