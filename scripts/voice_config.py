"""Runtime configuration for the clone voice service.

Everything resolves relative to this file, so the whole folder can be moved or
copied to another machine without editing paths. Environment variables win over
the defaults below.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # repository root (scripts/ lives inside it)

# --- paths -----------------------------------------------------------------
REFERENCE = Path(os.environ.get("VOICE_REFERENCE", ROOT / "reference.wav"))
LOG = ROOT / "server.log"

# --- service ---------------------------------------------------------------
PORT = int(os.environ.get("VOICE_PORT", "8765"))
HOST = "127.0.0.1"
# Used by the switch script: the Hermes tts.provider name this package registers.
PROVIDER = os.environ.get("VOICE_PROVIDER", "jarvis")

# --- voice ----------------------------------------------------------------
EXAGGERATION = float(os.environ.get("VOICE_EXAGGERATION", "0.45"))
CFG_WEIGHT = float(os.environ.get("VOICE_CFG_WEIGHT", "0.45"))
TEMPERATURE = float(os.environ.get("VOICE_TEMPERATURE", "0.65"))
MIN_P = float(os.environ.get("VOICE_MIN_P", "0.05"))
REPETITION_PENALTY = float(os.environ.get("VOICE_REPETITION_PENALTY", "1.2"))

# Sanity envelope for a take. A deliberate voice runs ~100 wpm, not the ~180 a
# "words / 3" estimate implies; derive it from the pace you actually configured.
WORDS_PER_MINUTE = float(os.environ.get("VOICE_WPM", "100"))
DURATION_FLOOR = 0.40    # a take shorter than this fraction of the estimate is junk
DURATION_CEILING = 2.60  # ... and so is one longer than this

# --- quality gate ---------------------------------------------------------
# Each take is transcribed and compared with the input text before it ships.
TAKES = int(os.environ.get("VOICE_TAKES", "3"))
VERIFY_MIN_SIMILARITY = float(os.environ.get("VOICE_VERIFY_MIN_SIMILARITY", "0.55"))
SHIP_MIN_SIMILARITY = float(os.environ.get("VOICE_SHIP_MIN_SIMILARITY", "0.30"))
# Hermes aborts a command provider at 120 s; keep the retry loop well inside it.
MAX_SECONDS = float(os.environ.get("VOICE_MAX_SECONDS", "70"))
# Whisper model used only to grade takes. "small" is fast; point it at a local
# directory to stay offline.
VERIFY_MODEL = os.environ.get("VOICE_VERIFY_MODEL", "small")

# --- languages -------------------------------------------------------------
# English uses the English-only model (best prosody for English). Every other
# language supported by the multilingual model goes through that one instead, so a
# single cloned voice can speak more than English.
#
# Cross-lingual cloning keeps the TIMBRE but not the native accent: a reference in
# the same language as the output always sounds markedly better. Documented in
# references/pipeline.md ("same language in, same language out").
MULTILINGUAL = os.environ.get("VOICE_MULTILINGUAL", "1").strip().lower() not in ("", "0", "false", "no")
# 1 = keep one generative model resident and swap when the language changes (8 GB
# cards); 2 = keep English and multilingual loaded together (needs ~2 GB more VRAM).
MAX_RESIDENT_MODELS = int(os.environ.get("VOICE_MAX_MODELS", "1"))
DEFAULT_LANGUAGE = os.environ.get("VOICE_DEFAULT_LANGUAGE", "en")
# Pace estimate for non-space-delimited scripts (characters per second).
CJK_CHARS_PER_SECOND = float(os.environ.get("VOICE_CJK_CPS", "4.0"))

# Cloud voice used only when the multilingual model is unavailable for a language.
# Set VOICE_FALLBACK_VOICE="" to return an error instead of substituting a voice.
FALLBACK_VOICE = os.environ.get("VOICE_FALLBACK_VOICE", "zh-CN-YunyangNeural")
FALLBACK_SPEED = float(os.environ.get("VOICE_FALLBACK_SPEED", "0.95"))

# --- audio -----------------------------------------------------------------
LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
SAMPLE_RATE = 24000
