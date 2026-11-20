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
import gc
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
from typing import Any

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
_models: dict[str, Any] = {}
_models_lock = threading.Lock()

# Script detection: enough to pick the right model, not a language identifier.
_SCRIPT_PATTERNS = [
    ("ja", re.compile(r"[\u3040-\u30ff]")),      # kana first: Japanese also uses han
    ("zh", re.compile(r"[\u4e00-\u9fff]")),
    ("ko", re.compile(r"[\uac00-\ud7af]")),
    ("ru", re.compile(r"[\u0400-\u04ff]")),
    ("ar", re.compile(r"[\u0600-\u06ff]")),
    ("he", re.compile(r"[\u0590-\u05ff]")),
    ("el", re.compile(r"[\u0370-\u03ff]")),
    ("hi", re.compile(r"[\u0900-\u097f]")),
]


def detect_language(text: str) -> str:
    for lang, pattern in _SCRIPT_PATTERNS:
        if pattern.search(text):
            return lang
    return cfg.DEFAULT_LANGUAGE


def get_model(language: str):
    """The generative model for this language.

    English -> the English-only checkpoint (best prosody). Anything else -> the
    multilingual checkpoint, which accepts `language_id`. This function is also the
    single place to swap in a different backend (CosyVoice, GPT-SoVITS, F5-TTS ...):
    as long as it returns (waveform, sample_rate) from (text, reference), nothing
    else in the server has to change.
    """
    key = "en" if language == cfg.DEFAULT_LANGUAGE else "multilingual"
    with _models_lock:
        model = _models.get(key)
        if model is not None:
            return model

        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[voice] loading {key} model on {device}", flush=True)
        if key == "en":
            from chatterbox.tts import ChatterboxTTS
            model = ChatterboxTTS.from_pretrained(device=device)
        else:
            if not cfg.MULTILINGUAL:
                raise RuntimeError(
                    f"language '{language}' needs the multilingual model, but "
                    "VOICE_MULTILINGUAL is off")
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
            # First non-English request downloads its own weights (~3.7 GB). English-only
            # users never pay this cost; say so in the log rather than surprising them.
            print("[voice] multilingual model: loading (first use downloads ~3.7 GB)", flush=True)
            model = ChatterboxMultilingualTTS.from_pretrained(device=device)

        # VRAM: on an 8 GB card both checkpoints plus Whisper is a tight fit, so by
        # default the previous model is evicted rather than kept alongside.
        while len(_models) >= max(1, cfg.MAX_RESIDENT_MODELS):
            evicted = _models.pop(next(iter(_models)))
            del evicted
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        _models[key] = model
        print(f"[voice] {key} model ready", flush=True)
        return model


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
def expected_seconds(text: str, language: str) -> float:
    """Rough duration for this text at the configured pace. Used only as a junk
    filter, so it is deliberately loose: a 6-word line at 100 wpm is ~3.6 s, and
    a take of 2.0 s or 7.5 s can both be perfectly good.

    Scripts without spaces (Chinese, Japanese, Korean) are measured in characters;
    counting "words" there returns 1 and would reject every take."""
    if language != cfg.DEFAULT_LANGUAGE:
        chars = sum(1 for ch in text if not ch.isspace())
        return max(1.5, chars / max(1.0, cfg.CJK_CHARS_PER_SECOND))
    words = max(1, len(text.split()))
    return max(1.5, words / (cfg.WORDS_PER_MINUTE / 60.0))


def _norm_units(text: str) -> list[str]:
    """Comparison units for the quality gate.

    English compares words; Chinese/Japanese compare characters. Without this split
    the regex finds no "words" in CJK text, similarity is 0.0, and every take is
    thrown away even when the audio is perfect."""
    if any("\u3040" <= ch <= "\u9fff" or "\uac00" <= ch <= "\ud7af" for ch in text):
        return [ch for ch in text if ch.isalnum()]
    return _WORD_RE.findall(text.lower())


def similarity(heard: str, text: str) -> float:
    a, b = _norm_units(heard), _norm_units(text)
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

    language = detect_language(text)

    try:
        model = get_model(language)
    except Exception as exc:
        # Only reached when the multilingual model is disabled or unavailable.
        if not cfg.FALLBACK_VOICE:
            raise
        print(f"[voice] no model for '{language}' ({exc}) -> cloud fallback", flush=True)
        asyncio.run(cloud_fallback(text, out_path))
        return out_path

    expected = expected_seconds(text, language)
    best: tuple[float, str] | None = None
    started = time.time()

    for attempt in range(max(1, cfg.TAKES)):
        if attempt and time.time() - started > cfg.MAX_SECONDS:
            print(f"[voice] time budget spent after {attempt} takes", flush=True)
            break
        kwargs = dict(
            audio_prompt_path=str(cfg.REFERENCE),
            exaggeration=cfg.EXAGGERATION,
            cfg_weight=cfg.CFG_WEIGHT,
            temperature=cfg.TEMPERATURE,
            min_p=cfg.MIN_P,
            repetition_penalty=cfg.REPETITION_PENALTY,
        )
        if language != cfg.DEFAULT_LANGUAGE:
            kwargs["language_id"] = language  # multilingual checkpoint only
        with _models_lock, _model_lock:
            wav = model.generate(text, **kwargs)
        dur = wav.shape[-1] / model.sr

        fd, take = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        torchaudio.save(take, wav, model.sr)

        plausible = cfg.DURATION_FLOOR * expected <= dur <= cfg.DURATION_CEILING * expected
        if not plausible:
            score, heard = 0.05, f"<implausible length {dur:.1f}s>"
        else:
            try:
                score, heard = verify_take(take, text, language)
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
