"""Turn any recording into a clean reference clip for voice cloning.

    python prepare_reference.py source.mp4
    python prepare_reference.py source.mp4 --start 302 --end 311
    python prepare_reference.py vocals.wav --no-separate

Pipeline: decode -> optionally strip music/SFX with demucs -> trim silence ->
loudness-normalise -> 24 kHz mono WAV. Prints a report you can paste into a bug
report; refuses clips that are too short or too long to clone well.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import voice_config as cfg  # noqa: E402

MIN_SECONDS, MAX_SECONDS = 3.0, 25.0


def need(binary: str) -> str:
    path = shutil.which(binary)
    if not path:
        sys.exit(f"[!] '{binary}' not found on PATH")
    return path


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=nw=1:nk=1", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source", type=Path)
    ap.add_argument("--start", type=float, default=0.0, help="seconds into the source")
    ap.add_argument("--end", type=float, default=0.0, help="seconds; 0 = take the rest")
    ap.add_argument("--no-separate", action="store_true", help="skip demucs vocal separation")
    ap.add_argument("--out", type=Path, default=cfg.REFERENCE)
    ap.add_argument("--trim-threshold", default="-40dB", help="silence threshold for trim")
    args = ap.parse_args()

    if not args.source.exists():
        sys.exit(f"[!] no such file: {args.source}")
    need("ffmpeg")
    need("ffprobe")

    work = Path(tempfile.mkdtemp(prefix="voiceref_"))
    raw = work / "raw.wav"
    cut = ["-ss", str(args.start)] if args.start else []
    dur = ["-t", str(args.end - args.start)] if args.end > args.start else []
    subprocess.run(["ffmpeg", "-v", "error", "-y", *cut, *dur, "-i", str(args.source),
                    "-vn", "-ac", "1", "-ar", "24000", str(raw)], check=True)
    stage = raw

    if not args.no_separate:
        print("[1/3] separating vocals with demucs (music/SFX removed)...")
        rc = subprocess.run([sys.executable, "-m", "demucs.separate", "-n", "htdemucs",
                             "--two-stems=vocals", "-o", str(work / "sep"), str(raw)]).returncode
        if rc == 0:
            candidates = list((work / "sep").rglob("vocals.wav"))
            if candidates:
                stage = candidates[0]
            else:
                print("[!] demucs produced no vocals.wav; continuing with the raw track")
        else:
            print("[!] demucs failed (is it installed?); continuing with the raw track")

    print("[2/3] trimming silence and normalising loudness...")
    proc = subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", str(stage),
        "-af", f"silenceremove=start_periods=1:start_threshold={args.trim_threshold}:"
               f"start_silence=0.1,areverse,silenceremove=start_periods=1:"
               f"start_threshold={args.trim_threshold}:start_silence=0.1,areverse,"
               f"{cfg.LOUDNORM}",
        "-ac", "1", "-ar", "24000", str(args.out),
    ])
    if proc.returncode != 0:
        print("[!] trim/normalise failed; falling back to a plain conversion")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(stage), "-ac", "1",
                        "-ar", "24000", str(args.out)], check=True)

    print("[3/3] checking the result...")
    secs = duration(args.out)
    print(f"\n  output      : {args.out}")
    print(f"  duration    : {secs:.1f}s  (target {MIN_SECONDS:.0f}-{MAX_SECONDS:.0f}s)")

    ok = True
    if secs < MIN_SECONDS:
        print("  FAIL        : too short — the clone will have too little to imitate")
        ok = False
    elif secs > MAX_SECONDS:
        print("  WARN        : long reference; the model only uses the opening ~10s")
    if not args.no_separate and "vocals" not in str(stage):
        print("  WARN        : separation did not run; music residue will leak into the voice")

    print("\n  next: python scripts/voice_switch.py on")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
