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
3. **Zero-shot models degrade into humming** on text outside their language, so
   CJK is detected and routed to a cloud voice instead of being fed to the clone.

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
- Never feed CJK to the clone model — the fallback exists precisely because the
  model hums instead of speaking it.
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
