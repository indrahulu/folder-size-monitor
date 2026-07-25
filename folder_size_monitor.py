#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shlex
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG_PATH = os.getenv("FOLDER_MONITOR_CONFIG", "/etc/folder-size-monitor.json")
INFLUX_URL = os.getenv("INFLUX_URL", "http://docker2-pdn1:8181").rstrip("/")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN")
if not INFLUX_TOKEN:
    raise SystemExit("INFLUX_TOKEN is required")

DEFAULT_DB = os.getenv("INFLUX_DB", "infrastruktur")
DEFAULT_SITE = os.getenv("SITE", "pdns1")
DEFAULT_MEASUREMENT = os.getenv("MEASUREMENT", "ukuran_folder")
DU_TIMEOUT_SEC = int(os.getenv("DU_TIMEOUT_SEC", "120"))
SERVER_NAME = os.getenv("SERVER_NAME") or socket.gethostname().split(".")[0]


def lp_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(" ", "\\ ")
        .replace(",", "\\,")
        .replace("=", "\\=")
    )


def load_config() -> dict:
    data = json.loads(Path(CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("config root must be an object")
    return data


def du_bytes(path: str) -> int:
    # --apparent-size is intentionally NOT used; we want disk usage growth.
    cmd = ["bash", "-lc", f"ionice -c3 nice -n 19 du -sB1 -- {shlex.quote(path)}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=DU_TIMEOUT_SEC)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip() or f"du exited {proc.returncode}"
        raise RuntimeError(err)
    return int(proc.stdout.split()[0])


def write_points(database: str, lines: list[str]) -> None:
    if not lines:
        return
    body = ("\n".join(lines) + "\n").encode("utf-8")
    url = f"{INFLUX_URL}/api/v3/write_lp?" + urllib.parse.urlencode({"db": database, "precision": "ns"})
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {INFLUX_TOKEN}",
            "Content-Type": "text/plain; charset=utf-8",
            "Accept": "application/json, text/plain, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        resp.read()


def main() -> int:
    cfg = load_config()
    database = str(cfg.get("database", DEFAULT_DB))
    site = str(cfg.get("site", DEFAULT_SITE))
    measurement = str(cfg.get("measurement", DEFAULT_MEASUREMENT))
    items = cfg.get("paths", [])
    if not isinstance(items, list):
        raise ValueError("config.paths must be a list")

    ts_ns = int(time.time() * 1_000_000_000)
    ok_count = 0
    fail_count = 0
    lines: list[str] = []

    for item in items:
        if isinstance(item, str):
            path = item
            label = None
        elif isinstance(item, dict):
            path = str(item.get("path", "")).strip()
            label = item.get("label")
            label = str(label).strip() if label is not None else None
        else:
            fail_count += 1
            print(f"[WARN] invalid path entry: {item!r}", file=sys.stderr)
            continue

        if not path:
            fail_count += 1
            print("[WARN] empty path entry", file=sys.stderr)
            continue

        try:
            size = du_bytes(path)
            tags = [
                f"path={lp_escape(path)}",
                f"server={lp_escape(SERVER_NAME)}",
                f"site={lp_escape(site)}",
            ]
            if label:
                tags.append(f"label={lp_escape(label)}")
            fields = f"size={size}i"
            lines.append(f"{measurement},{','.join(tags)} {fields} {ts_ns}")
            ok_count += 1
        except Exception as exc:
            fail_count += 1
            print(f"[WARN] {path}: {exc}", file=sys.stderr)

    write_points(database, lines)
    print(
        json.dumps(
            {
                "ok": True,
                "database": database,
                "measurement": measurement,
                "server": SERVER_NAME,
                "site": site,
                "written": ok_count,
                "failed": fail_count,
            },
            ensure_ascii=False,
        ),
        file=sys.stderr,
    )
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
