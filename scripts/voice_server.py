"""Resident TTS server: loads the clone model once, serves /tts over localhost.

    python voice_server.py            # reads voice_config.py

POST /tts   {"text": "...", "out": "C:/tmp/out.mp3", "format": "mp3"}
GET  /health

Why a server instead of a one-shot script: loading the weights costs tens of
seconds; a Hermes command provider is killed at 120 s. Keep the model resident
and each request becomes a couple of seconds of work instead of a cold start.
"""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import torch
import torchaudio

sys.path.insert(0, str(Path(__file__).resolve().parent))
import voice_config as cfg  # noqa: E402

_model = None
_model_lock = threading.Lock()
_verifier = None
_verifier_lock = threading.Lock()
_WORD_RE = re.compile(r"[a-z0-9']+")


# --------------------------------------------------------------- models
def get_model():
    """The generative model. Chatterbox is the default; swap this function to use
    another zero-shot backend (F5-TTS, CosyVoice, GPT-SoVITS, ...) as long as it
    returns (waveform, sample_rate) from (text, reference_path)."""
    global _model
    if _model is None:
        from chatterbox.tts import ChatterboxTTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[voice] loading model on {device}", flush=True)
        _model = ChatterboxTTS.from_pretrained(device=device)
        print("[voice] model ready", flush=True)
    return _model


def get_verifier():
    """Whisper, used only to grade takes. Optional: without it the server falls
    back to a length check (still catches loops, catches fewer swaps)."""
    global _verifier
    if _verifier is None:
        from faster_whisper import WhisperModel
        try:
            _verifier = WhisperModel(cfg.VERIFY_MODEL, device="cuda", compute_type="float16")
            print("[voice] verifier ready on cuda", flush=True)
        except Exception as exc:
            print(f"[voice] verifier cuda unavailable ({exc}); using cpu", flush=True)
            _verifier = WhisperModel(cfg.VERIFY_MODEL, device="cpu", compute_type="int8")
    return _verifier


# --------------------------------------------------------------- helpers
def has_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


def expected_seconds(text: str) -> float:
    """Rough duration for this text at the configured pace. Used only as a junk
    filter, so it is deliberately loose: a 6-word line at 100 wpm is ~3.6 s, and
    a take of 2.0 s or 7.5 s can both be perfectly good."""
    words = max(1, len(text.split()))
    return max(1.5, words / (cfg.WORDS_PER_MINUTE / 60.0))


def _norm_words(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def similarity(heard: str, text: str) -> float:
    a, b = _norm_words(heard), _norm_words(text)
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(a=a, b=b, autojunk=False).ratio()


def verify_take(wav_path: str, text: str, language: str = "en") -> tuple[float, str]:
    model = get_verifier()
    with _verifier_lock:
        segments, _ = model.transcribe(wav_path, beam_size=1, vad_filter=False,
                                       language=language, condition_on_previous_text=False)
        heard = " ".join(s.text.strip() for s in segments)
    return similarity(heard, text), heard


def encode(wav_path: str, out_path: str, fmt: str) -> None:
    if fmt.lower() in ("wav", ""):
        os.replace(wav_path, out_path)
        return
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav_path, "-af", cfg.LOUDNORM,
                    "-ar", str(cfg.SAMPLE_RATE), "-b:a", "96k", out_path], check=True)


async def cloud_fallback(text: str, out_path: str) -> str:
    """Non-Latin text: the clone hums instead of speaking. Hand it to a cloud voice."""
    import edge_tts
    tmp = out_path + ".fallback.mp3"
    rate = f"{round((cfg.FALLBACK_SPEED - 1.0) * 100):+d}%"
    await edge_tts.Communicate(text, cfg.FALLBACK_VOICE, rate=rate).save(tmp)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-af", cfg.LOUDNORM, out_path], check=True)
    os.unlink(tmp)
    return out_path


# --------------------------------------------------------------- synthesis
def synthesize(text: str, out_path: str, fmt: str = "mp3") -> str:
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    if not cfg.REFERENCE.exists():
        raise RuntimeError(f"reference audio missing: {cfg.REFERENCE}")

    if has_cjk(text):
        if not cfg.FALLBACK_VOICE:
            raise RuntimeError("text contains CJK and VOICE_FALLBACK_VOICE is disabled; "
                               "the clone model cannot read it")
        print("[voice] CJK text -> cloud fallback", flush=True)
        asyncio.run(cloud_fallback(text, out_path))
        return out_path

    model = get_model()
    expected = expected_seconds(text)
    best: tuple[float, str] | None = None
    started = time.time()

    for attempt in range(max(1, cfg.TAKES)):
        if attempt and time.time() - started > cfg.MAX_SECONDS:
            print(f"[voice] time budget spent after {attempt} takes", flush=True)
            break
        with _model_lock:
            wav = model.generate(
                text,
                audio_prompt_path=str(cfg.REFERENCE),
                exaggeration=cfg.EXAGGERATION,
                cfg_weight=cfg.CFG_WEIGHT,
                temperature=cfg.TEMPERATURE,
                min_p=cfg.MIN_P,
                repetition_penalty=cfg.REPETITION_PENALTY,
            )
        dur = wav.shape[-1] / model.sr

        fd, take = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        torchaudio.save(take, wav, model.sr)

        plausible = cfg.DURATION_FLOOR * expected <= dur <= cfg.DURATION_CEILING * expected
        if not plausible:
            score, heard = 0.05, f"<implausible length {dur:.1f}s>"
        else:
            try:
                score, heard = verify_take(take, text)
            except Exception as exc:
                print(f"[voice] verifier unavailable ({exc}); length check only", flush=True)
                score, heard = 1.0, ""
        print(f"[voice] take {attempt + 1}: {dur:.1f}s (expected {expected:.1f}s) "
              f"similarity {score:.2f} :: {heard[:90]!r}", flush=True)

        if best is None or score > best[0]:
            if best is not None:
                os.unlink(best[1])
            best = (score, take)
        else:
            os.unlink(take)
        if score >= cfg.VERIFY_MIN_SIMILARITY:
            break

    if best is None:
        raise RuntimeError("no take generated")
    score, chosen = best
    if score < cfg.SHIP_MIN_SIMILARITY:
        os.unlink(chosen)
        raise RuntimeError(f"every take was unintelligible (best {score:.2f}); nothing shipped")

    print(f"[voice] shipping take {score:.2f}", flush=True)
    try:
        encode(chosen, out_path, fmt)
    finally:
        if os.path.exists(chosen):
            os.unlink(chosen)
    return out_path


# --------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/health"):
            self._send(200, {
                "ok": True,
                "device": "cuda" if torch.cuda.is_available() else "cpu",
                "reference": str(cfg.REFERENCE),
                "reference_present": cfg.REFERENCE.exists(),
            })
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.startswith("/tts"):
            self._send(404, {"error": "not found"})
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
            text = (req.get("text") or "").strip()
            out = req.get("out")
            fmt = req.get("format") or "mp3"
            if not text or not out:
                self._send(400, {"error": "text and out are required"})
                return
            self._send(200, {"ok": True, "path": synthesize(text, out, fmt)})
        except Exception as exc:
            traceback.print_exc()
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"})


def main() -> int:
    if not cfg.REFERENCE.exists():
        print(f"[voice] reference audio missing: {cfg.REFERENCE}", flush=True)
        print("[voice] make one with scripts/prepare_reference.py", flush=True)
        return 1
    get_model()
    print(f"[voice] listening on {cfg.HOST}:{cfg.PORT}", flush=True)
    ThreadingHTTPServer((cfg.HOST, cfg.PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
