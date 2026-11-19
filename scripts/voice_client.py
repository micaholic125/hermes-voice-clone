"""Hermes command-provider client: text file in, audio file out.

Hermes calls this with {text_path} {output_path} {format}. It talks to the
resident server, starting it first if the port is closed.

    python voice_client.py in.txt out.mp3 mp3
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_config as cfg  # noqa: E402

BASE = f"http://{cfg.HOST}:{cfg.PORT}"
STARTUP_TIMEOUT = int(os.environ.get("VOICE_STARTUP_TIMEOUT", "480"))


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((cfg.HOST, cfg.PORT)) == 0


def start_server() -> None:
    py = sys.executable
    log = open(cfg.LOG, "ab")
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    try:
        subprocess.Popen([py, str(HERE / "voice_server.py")], stdout=log, stderr=log,
                         cwd=str(HERE), creationflags=flags)
    finally:
        log.close()
    deadline = time.time() + STARTUP_TIMEOUT
    while time.time() < deadline:
        if port_open():
            return
        time.sleep(2.0)
    raise RuntimeError(f"voice server did not come up within {STARTUP_TIMEOUT}s; see {cfg.LOG}")


def request_tts(text: str, out_path: str, fmt: str) -> dict:
    body = json.dumps({"text": text, "out": os.path.abspath(out_path), "format": fmt}).encode()
    req = urllib.request.Request(f"{BASE}/tts", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: voice_client.py <text_path> <output_path> [format]", file=sys.stderr)
        return 2
    text_path, out_path = sys.argv[1], sys.argv[2]
    fmt = sys.argv[3] if len(sys.argv) > 3 else "mp3"
    text = Path(text_path).read_text(encoding="utf-8").strip()
    if not text:
        print("empty input text", file=sys.stderr)
        return 2
    if not port_open():
        start_server()
    for attempt in (1, 2):
        try:
            result = request_tts(text, out_path, fmt)
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "unknown error"))
            return 0
        except (urllib.error.URLError, ConnectionError):
            if attempt == 2:
                raise
            start_server()
    return 0


if __name__ == "__main__":
    sys.exit(main())
