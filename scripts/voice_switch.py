"""Idempotent on / off / status / restart for the clone voice module.

    python voice_switch.py status
    python voice_switch.py on
    python voice_switch.py off
    python voice_switch.py restart

Exit 0 = requested state reached AND verified. Exit 1 = something failed.
Every action checks the current state first, so running it twice is safe.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_config as cfg  # noqa: E402

HERMES = shutil.which("hermes") or "hermes"
BASE = f"http://{cfg.HOST}:{cfg.PORT}"

if os.name == "nt":
    STARTUP_DIR = Path(os.path.expandvars(
        r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"))
    VBS_NAME = f"{cfg.PROVIDER}-voice.vbs"
    VBS_ON = STARTUP_DIR / VBS_NAME
    # A disabled entry must LEAVE the Startup folder. Windows executes every file it
    # finds there and asks "how do you want to open this?" for anything it cannot run,
    # so a renamed *.vbs.off left in place nags the user on every single boot.
    DISABLED_DIR = cfg.ROOT / "startup-disabled"
    VBS_OFF = DISABLED_DIR / VBS_NAME
    LEGACY_VBS_OFF = STARTUP_DIR / (VBS_NAME + ".off")
else:
    STARTUP_DIR = None
    VBS_ON = VBS_OFF = LEGACY_VBS_OFF = None


def run(cmd: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return 127, f"command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timeout after {timeout}s: {' '.join(cmd)}"


def port_open() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((cfg.HOST, cfg.PORT)) == 0


def server_pids() -> list[str]:
    if os.name == "nt":
        rc, out = run(["netstat", "-ano"])
        if rc != 0:
            return []
        pids = set()
        for line in out.splitlines():
            if f":{cfg.PORT}" in line and "LISTENING" in line.upper():
                parts = line.split()
                if parts and parts[-1].isdigit():
                    pids.add(parts[-1])
        return sorted(pids)
    rc, out = run(["lsof", "-ti", f"tcp:{cfg.PORT}"])
    return [p for p in out.split() if p.isdigit()] if rc == 0 else []


def kill_server() -> None:
    for pid in server_pids():
        if os.name == "nt":
            run(["taskkill", "/F", "/PID", pid])
        else:
            run(["kill", "-9", pid])


def hermes_provider() -> str:
    rc, out = run([HERMES, "config", "get", "tts"], timeout=120)
    for line in out.splitlines():
        if line.strip().startswith("provider:"):
            return line.split(":", 1)[1].strip()
    return "(unknown)"


def set_provider(name: str) -> tuple[bool, str]:
    rc, out = run([HERMES, "config", "set", "tts.provider", name], timeout=120)
    return rc == 0, out.strip().splitlines()[-1] if out.strip() else ""


def start_server(wait: int = 480) -> bool:
    if port_open():
        return True
    log = open(cfg.LOG, "ab")
    flags = 0x08000000 if os.name == "nt" else 0
    try:
        subprocess.Popen([sys.executable, str(HERE / "voice_server.py")],
                         stdout=log, stderr=log, cwd=str(HERE), creationflags=flags)
    finally:
        log.close()
    deadline = time.time() + wait
    while time.time() < deadline:
        if port_open():
            return True
        time.sleep(2.0)
    print("  last log lines:")
    try:
        for line in cfg.LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-8:]:
            print(f"    {line.strip()}")
    except OSError:
        pass
    return False


def warm_and_verify() -> tuple[bool, str]:
    fd, txt = tempfile.mkstemp(suffix=".txt")
    os.close(fd)
    out = os.path.join(tempfile.gettempdir(), f"{cfg.PROVIDER}_probe.mp3")
    try:
        Path(txt).write_text("System check. All voices accounted for.", encoding="utf-8")
        rc, log = run([sys.executable, str(HERE / "voice_client.py"), txt, out, "mp3"], timeout=600)
        if rc != 0:
            return False, log.strip()[-400:]
        if not os.path.exists(out) or os.path.getsize(out) < 5000:
            return False, "probe produced no usable audio"
        return True, f"{os.path.getsize(out) // 1024} KB"
    finally:
        for p in (txt, out):
            if os.path.exists(p):
                os.unlink(p)


def startup_state() -> str:
    if VBS_ON is None:
        return "n/a (non-Windows)"
    if VBS_ON.exists():
        return "enabled"
    if VBS_OFF.exists():
        return "disabled"
    return "absent"


def _migrate_legacy() -> None:
    """Older builds renamed the entry to *.vbs.off *inside* Startup; move it out once."""
    if LEGACY_VBS_OFF and LEGACY_VBS_OFF.exists():
        DISABLED_DIR.mkdir(parents=True, exist_ok=True)
        if VBS_OFF.exists():
            VBS_OFF.unlink()
        shutil.move(str(LEGACY_VBS_OFF), str(VBS_OFF))


def set_startup(enabled: bool) -> None:
    if VBS_ON is None:
        return
    STARTUP_DIR.mkdir(parents=True, exist_ok=True)
    _migrate_legacy()
    if enabled:
        DISABLED_DIR.mkdir(parents=True, exist_ok=True)
        if VBS_OFF.exists() and not VBS_ON.exists():
            shutil.move(str(VBS_OFF), str(VBS_ON))  # may cross drives: not a rename
        if not VBS_ON.exists():
            VBS_ON.write_text(
                "' Start the clone voice server hidden at logon.\n"
                "Set sh = CreateObject(\"WScript.Shell\")\n"
                f'sh.Run """{sys.executable}"" ""{HERE / "voice_server.py"}""", 0, False\n',
                encoding="utf-8")
    else:
        if VBS_ON.exists():
            DISABLED_DIR.mkdir(parents=True, exist_ok=True)
            if VBS_OFF.exists():
                VBS_OFF.unlink()
            shutil.move(str(VBS_ON), str(VBS_OFF))


def do_status() -> int:
    print("clone voice module status")
    print(f"  provider            : {hermes_provider()}  (expected '{cfg.PROVIDER}' when on)")
    print(f"  startup entry       : {startup_state()}")
    print(f"  port {cfg.PORT:<14}: {'listening' if port_open() else 'closed'}")
    print(f"  server pids         : {', '.join(server_pids()) or '-'}")
    if port_open():
        try:
            with urllib.request.urlopen(f"{BASE}/health", timeout=5) as r:
                print(f"  health              : {json.loads(r.read())}")
        except Exception as exc:
            print(f"  health              : unreachable ({exc})")
    print(f"  reference           : {cfg.REFERENCE} "
          f"({'present' if cfg.REFERENCE.exists() else 'MISSING'})")
    return 0


def do_on() -> int:
    ok, msg = set_provider(cfg.PROVIDER)
    print(f"  provider -> {cfg.PROVIDER:<8}: {'ok' if ok else 'FAILED ' + msg}")
    set_startup(True)
    print(f"  startup entry       : {startup_state()}")
    if not start_server():
        print("  server              : FAILED to start")
        return 1
    print("  server              : listening")
    ok, detail = warm_and_verify()
    print(f"  synthesis probe     : {'ok, ' + detail if ok else 'FAILED ' + detail}")
    return 0 if ok else 1


def do_off() -> int:
    ok, msg = set_provider("edge")
    print(f"  provider -> edge    : {'ok' if ok else 'FAILED ' + msg}")
    set_startup(False)
    print(f"  startup entry       : {startup_state()}")
    kill_server()
    deadline = time.time() + 20
    while time.time() < deadline and port_open():
        time.sleep(0.5)
    if port_open():
        kill_server()
        deadline = time.time() + 15
        while time.time() < deadline and port_open():
            time.sleep(0.5)
    if port_open():
        print(f"  server              : STILL LISTENING ({', '.join(server_pids()) or 'unknown pid'})")
        return 1
    print("  server              : stopped")
    print(f"  verify provider     : {hermes_provider()}")
    return 0 if hermes_provider() != cfg.PROVIDER else 1


def do_restart() -> int:
    kill_server()
    time.sleep(1.5)
    return do_on()


def main() -> int:
    action = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    table = {"status": do_status, "on": do_on, "off": do_off, "restart": do_restart}
    if action not in table:
        print(__doc__)
        return 2
    return table[action]()


if __name__ == "__main__":
    sys.exit(main())
