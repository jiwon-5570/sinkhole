from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
LOG_DIR = BACKEND_DIR / "data" / "tmp"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server-persistent.log"


def main() -> None:
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))
    os.environ["SINKHOLE_RELOAD"] = "0"
    os.environ["SINKHOLE_PUBLIC_DATA_AUTO_COLLECT"] = "0"
    os.environ["SINKHOLE_PUBLIC_DATA_COLLECT_ON_START"] = "0"
    os.environ["SINKHOLE_ANALYZE_ON_START"] = "0"
    os.environ["SINKHOLE_LOCAL_CONSTRUCTION_FILE_IMPORT_ENABLED"] = "0"

    log = LOG_FILE.open("a", encoding="utf-8", buffering=1)
    sys.stdout = log
    sys.stderr = log
    print("starting persistent sinkhole server", flush=True)

    try:
        import uvicorn

        uvicorn.run(
            "app.main:app",
            host="127.0.0.1",
            port=5000,
            log_level="info",
            reload=False,
        )
    except BaseException as exc:
        print(f"server crashed: {exc!r}", flush=True)
        raise


if __name__ == "__main__":
    main()
