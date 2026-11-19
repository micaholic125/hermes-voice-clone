"""Read-only health check for the clone voice module.

    python doctor.py

Prints PASS / WARN / FAIL per check. It never edits configuration, never
restarts anything: diagnose first, act second.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_config as cfg  # noqa: E402

results: list[tuple[str, str, str]] = []


def check(name: str, status: str, detail: str = "") -> None:
    results.append((status, name, detail))


def main() -> int:
    # interpreter
    v = sys.version_info
    check("python version", "PASS" if (3, 9) <= (v.major, v.minor) <= (3, 12) else "WARN",
          f"{v.major}.{v.minor}.{v.micro} (3.10-3.11 recommended for torch/chatterbox)")

    # ffmpeg
    check("ffmpeg", "PASS" if shutil.which("ffmpeg") else "FAIL",
          shutil.which("ffmpeg") or "not on PATH — every encode step needs it")

    # torch + cuda
    try:
        import torch
        cuda = torch.cuda.is_available()
        check("torch", "PASS", f"{torch.__version__}")
        check("cuda", "PASS" if cuda else "WARN",
              torch.cuda.get_device_name(0) if cuda else "no GPU visible — CPU works but ~4-5x slower")
    except Exception as exc:
        check("torch", "FAIL", f"{type(exc).__name__}: {exc}")

    # model deps
    for mod, why in [("chatterbox", "the cloning backend"), ("faster_whisper", "take grading (optional)")]:
        try:
            __import__(mod)
            check(mod, "PASS", why)
        except Exception as exc:
            check(mod, "WARN" if mod == "faster_whisper" else "FAIL", f"{type(exc).__name__}: {exc}")

    # reference audio
    if not cfg.REFERENCE.exists():
        check("reference audio", "FAIL", f"missing: {cfg.REFERENCE} — run prepare_reference.py")
    else:
        try:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                  "-of", "default=nw=1:nk=1", str(cfg.REFERENCE)],
                                 capture_output=True, text=True, check=True).stdout.strip()
            secs = float(out)
            check("reference audio", "PASS" if secs >= 3 else "WARN",
                  f"{cfg.REFERENCE.name}, {secs:.1f}s")
        except Exception as exc:
            check("reference audio", "WARN", f"unreadable: {exc}")

    # port + health
    with socket.socket() as s:
        s.settimeout(0.5)
        open_ = s.connect_ex((cfg.HOST, cfg.PORT)) == 0
    if open_:
        try:
            with urllib.request.urlopen(f"http://{cfg.HOST}:{cfg.PORT}/health", timeout=5) as r:
                check("service", "PASS", json.dumps(json.loads(r.read())))
        except Exception as exc:
            check("service", "FAIL", f"port open but health unreachable: {exc}")
    else:
        check("service", "INFO", f"port {cfg.PORT} closed — run voice_switch.py on")

    # hermes provider
    hermes = shutil.which("hermes")
    if not hermes:
        check("hermes cli", "WARN", "not on PATH; cannot verify tts.provider")
    else:
        out = subprocess.run([hermes, "config", "get", "tts"], capture_output=True,
                             text=True, encoding="utf-8", errors="replace").stdout
        provider = next((l.split(":", 1)[1].strip() for l in out.splitlines()
                         if l.strip().startswith("provider:")), "(unknown)")
        want = cfg.PROVIDER
        check("tts.provider", "PASS" if provider == want else "WARN",
              f"{provider} (expected '{want}' when the module is on)")

    # caches on the system drive
    for label, path in [("uv cache", os.path.expandvars(r"%LOCALAPPDATA%\uv\cache")),
                        ("hf cache", os.path.expandvars(r"%USERPROFILE%\.cache\huggingface"))]:
        p = Path(path)
        if p.exists():
            try:
                size_mb = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) // 2**20
                check(label, "WARN" if size_mb > 5000 else "INFO", f"{size_mb} MB at {p}")
            except OSError:
                pass

    width = max(len(n) for _, n, _ in results)
    for status, name, detail in results:
        print(f"[{status:<4}] {name:<{width}}  {detail}")
    fails = sum(1 for s, _, _ in results if s == "FAIL")
    print(f"\n{fails} failure(s). Read FAIL first, then WARN; only then change anything.")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
