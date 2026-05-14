from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parents[1]
PYTHON = ROOT_DIR / ".venv-1" / "Scripts" / "python.exe"
LOG_DIR = BACKEND_DIR / "data" / "tmp"
LOG_DIR.mkdir(parents=True, exist_ok=True)
OUT_LOG = LOG_DIR / "server-detached.out.log"
ERR_LOG = LOG_DIR / "server-detached.err.log"


def main() -> None:
    env = os.environ.copy()
    env.update(
        {
            "SINKHOLE_RELOAD": "0",
            "SINKHOLE_PUBLIC_DATA_AUTO_COLLECT": "0",
            "SINKHOLE_PUBLIC_DATA_COLLECT_ON_START": "0",
            "SINKHOLE_ANALYZE_ON_START": "0",
            "SINKHOLE_LOCAL_CONSTRUCTION_FILE_IMPORT_ENABLED": "0",
            "PYTHONPATH": str(BACKEND_DIR),
        }
    )
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    with OUT_LOG.open("ab") as stdout, ERR_LOG.open("ab") as stderr:
        proc = subprocess.Popen(
            [
                str(PYTHON),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "5000",
                "--log-level",
                "info",
            ],
            cwd=BACKEND_DIR,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            close_fds=True,
            creationflags=flags,
        )
    print(proc.pid)


if __name__ == "__main__":
    sys.exit(main())
