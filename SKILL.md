---
name: local-voice-clone-tts
description: "Use when cloning a voice for local TTS."
version: 1.0.0
author: Hermes Agent + user
license: MIT
platforms: [windows, linux, macos]
metadata:
  hermes:
    tags: [tts, voice-cloning, chatterbox, demucs, whisper, local-inference]
---

# Local voice-clone TTS

Give Hermes a cloned voice that runs on this machine: zero-shot from a short
reference clip, served over localhost, wired in as `tts.provider`. No cloud, no
per-character billing, no uploading the source audio anywhere.

## When to Use

- The user wants a specific voice (a character, a narrator, their own) as the
  agent's speaking voice.
- The user wants TTS that works offline or without paying a cloud provider.
- A clone already exists on this machine and stops working (see
  `references/troubleshooting.md`).
- Someone needs to switch the cloned voice on or off safely.

## Architecture (why it looks like this)

```
text ──► voice_client.py ──HTTP──► voice_server.py ──► mp3
         (Hermes command            (model resident
          provider, 120 s cap)       in VRAM, grading
                                     every take)
```

Three constraints shaped it, and every design choice follows from them:

1. **Cold start is expensive** (tens of seconds to load weights), so the model
   lives in a resident server rather than a one-shot script.
2. **Hermes kills a command provider at 120 s**, so the retry loop is capped at
   `MAX_SECONDS` (70 by default) and the service must already be warm.
3. **A model only speaks what it was trained on.** English runs on the English-only
   checkpoint; every other supported language is detected by script and routed to the
   multilingual checkpoint with `language_id`. A cloud voice is only the last resort.

## Quickstart

```bash
# 1. environment (its own venv — never the Hermes one)
uv venv -p 3.11 venv
uv pip install --python venv/Scripts/python.exe chatterbox-tts "setuptools<81" resemble-perth edge-tts demucs
uv pip install --python venv/Scripts/python.exe --reinstall \
    --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0+cu124 torchaudio==2.6.0+cu124
venv/Scripts/python.exe -c "import torch; print(torch.cuda.is_available())"   # must be True

# 2. reference clip (3-25 s, one speaker, music removed)
venv/Scripts/python.exe scripts/prepare_reference.py source.mp4 --start 302 --end 311

# 3. health, then on
venv/Scripts/python.exe scripts/doctor.py
venv/Scripts/python.exe scripts/voice_switch.py on
```

## Cloning a non-English voice (Chinese, Japanese, Korean …)

Same pipeline, three differences — and one of them is the reference clip.

```bash
# 1. Cut the reference from a speaker of THAT language, not an English one.
#    Timbre transfers across languages; accent does not.
python scripts/prepare_reference.py 中文素材.wav --target-language zh   # MATCH / MISMATCH

# 2. Check the multilingual checkpoint is importable.
python scripts/doctor.py          # look for "chatterbox.mtl_tts  PASS"

# 3. Send the text. The server detects the script and routes automatically.
python scripts/voice_switch.py on
```

What happens under the hood, in the log:

```
[voice] loading multilingual model on cuda
[voice] multilingual model: loading (first use downloads ~3.7 GB)
[voice] multilingual model ready
[voice] take 1: 4.2s (expected 3.6s) similarity 0.97
```

Costs and limits you should state out loud to the user before they start:

| Item | Value |
|---|---|
| First-use download | ~3.7 GB (only when a non-English request arrives) |
| Extra VRAM | ~2 GB while resident; default swaps English ↔ multilingual (~30 s per swap) |
| Quality gate | compares **characters** for CJK, words for space-delimited scripts |
| Accent | an English reference speaking Chinese sounds foreign — say so up front |
| Toggle | `VOICE_MULTILINGUAL=0` restores the old behaviour (cloud fallback for CJK) |

If the user wants the best Chinese rather than a Chinese-accented reuse of an English
voice, tell them the honest options: (a) a Chinese reference clip, (b) a Chinese-native
backend such as CosyVoice2 / GPT-SoVITS substituted at `get_model()` in
`voice_server.py`. Do not promise "same voice, perfect Mandarin" — that combination is
not physically available with zero-shot cloning.

## Operations

| Command | Does |
|---|---|
| `voice_switch.py status` | provider / startup entry / port / pids / health |
| `voice_switch.py on` | set `tts.provider`, enable autostart, start server, synthesize one probe line |
| `voice_switch.py off` | back to `edge`, disable autostart, stop server, verify the port is free |
| `voice_switch.py restart` | required after any edit to `voice_config.py` |
| `doctor.py` | read-only PASS/WARN/FAIL sweep |

Exit code `0` means the requested state was reached and verified. **Always run
`status` after `on`/`off`** — the exit code alone is not the acceptance check.

## Judgment: what the scripts do not decide for you

| Signal | Action |
|---|---|
| "turn it off / stop talking" | `off` only. Do not delete models, references, or edit config |
| "I want to hear it" | `status`, then `on`, report the probe result |
| "the voice sounds wrong / drifts / hums" | `status` + read the last 20 lines of `server.log` **before** touching any parameter |
| `timeout after 120s` from Hermes | the service was cold; `on`/`status` first, never raise the timeout |
| port open but `/health` fails | `off` then `on`; if it persists, kill by pid |
| cold start taking minutes | normal (two models into VRAM), not a fault |

## Red lines

- Never hand-edit `config.yaml`; use `hermes config set`.
- Never send a language to a checkpoint that does not support it: an English model fed
  Chinese hums, it does not error. Routing is automatic — do not bypass `detect_language`.
- **Use a reference clip in the same language as the output.** Cloning transfers timbre
  across languages, not accent: an English reference reading Chinese sounds like an
  English speaker reading Chinese. See `references/pipeline.md`.
- Never call the provider while the service is cold: the 120 s cap will kill it.
- Never ship a reference clip cut from copyrighted film or a private recording
  without the rights — see `references/legal-and-ethics.md`.

## Reference files

- `references/pipeline.md` — the full workflow, from picking a source to
  wiring the provider, with the decision points spelled out.
- `references/tuning.md` — measured effect of `cfg_weight`, `exaggeration`,
  `temperature`; symptom → parameter table.
- `references/troubleshooting.md` — failure table with root causes and fixes.
- `references/legal-and-ethics.md` — voice rights, consent, platform terms.
- `examples/jarvis-case-study.md` — a worked end-to-end example with real
  numbers and every wrong turn recorded.
