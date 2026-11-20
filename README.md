# Local Voice Clone TTS

> **English** · [中文](README.zh-CN.md)

A Hermes Agent skill that gives the agent a cloned speaking voice — zero-shot from a
short reference clip, running entirely on your own machine.

No cloud TTS, no per-character billing, no uploading the source audio to a third party.

```bash
# after installing the skill and its venv
python scripts/doctor.py            # PASS / WARN / FAIL sweep
python scripts/voice_switch.py on   # wire it into Hermes and verify
```

---

## What it actually does

```
text ──► voice_client.py ──HTTP──► voice_server.py ──► mp3
         (Hermes command            (Chatterbox resident
          provider, 120 s cap)       in VRAM, every take graded
                                     by Whisper before shipping)
```

- **Zero-shot cloning.** 3–25 seconds of one speaker is enough; no training run.
- **Quality gate.** Each take is transcribed back and compared with the input text.
  A take that loops, mumbles, or drifts outside a plausible duration is discarded and
  regenerated (up to 3 takes, capped at 70 s so Hermes' 120 s provider timeout never fires).
- **Language guard.** The clone speaks English and, through the multilingual
  checkpoint bundled with the same package, 22 other languages (Chinese, Japanese,
  Korean, Russian, Arabic, and more). English keeps the English-only model for the best
  prosody; everything else is routed to the multilingual one automatically. A cloud voice
  is used only if the multilingual model is unavailable.
- **Resident service.** Model weights load once; each request is seconds, not minutes.
- **Reversible.** `voice_switch.py off` puts Hermes back on Edge TTS and stops the
  service. Nothing is deleted.

## Languages

| What you send | Which model speaks | Quality |
|---|---|---|
| English | English checkpoint | best prosody |
| Chinese, Japanese, Korean, Russian, Arabic, Hebrew, Greek, Hindi … | multilingual checkpoint (23 languages) | good, with a caveat below |
| a language neither supports | cloud voice (optional fallback) | intelligible, wrong timbre |

**Use a reference clip in the same language as the output.** This is the single
biggest quality factor after the clip's cleanliness, and it is counter-intuitive:
zero-shot cloning transfers the *timbre* across languages, but not the *accent*.
An English reference reciting Chinese produces Chinese words in an English mouth —
recognisable, clearly foreign. A Chinese reference gives a Chinese voice.

The server routes by script, so you can mix languages in one session; the model
swaps on demand (`VOICE_MAX_MODELS=1` keeps only one resident, which is what an
8 GB card wants).

Check it before you rely on it:

```bash
python prepare_reference.py 素材.wav --target-language zh   # warns on MISMATCH
python doctor.py                                            # 'non-English' line states readiness
```

```yaml
VOICE_MULTILINGUAL=1        # 0 = English only, non-English falls back to cloud
VOICE_MAX_MODELS=1          # 1 = swap models, 2 = keep both loaded
VOICE_CJK_CPS=4.0           # characters/second used by the junk-duration filter
```

## Why a resident server

Loading weights costs 45 s to 4 min. Hermes aborts a command provider at 120 s.
So the model stays hot in a localhost server, and the client only pays for synthesis.
`MAX_SECONDS` exists to keep the retry loop inside that cap — do not raise it past ~90.

## Requirements

| Item | Notes |
|---|---|
| Python 3.10–3.11 | torch and chatterbox wheels lag newer versions |
| NVIDIA GPU, 6 GB+ VRAM | CPU works at roughly 4–5× the latency, and it is the usual "why is it slow" answer |
| ffmpeg on `PATH` | every encode and trim step |
| ~5 GB disk | CUDA torch dominates; keep caches off the system drive |
| Hermes Agent | the provider is a `tts.providers.<name>` command entry |

## Install

```bash
git clone <this repo> ~/.hermes/skills/local-voice-clone-tts
cd ~/.hermes/skills/local-voice-clone-tts

uv venv -p 3.11 venv
uv pip install --python venv/Scripts/python.exe chatterbox-tts "setuptools<81" resemble-perth edge-tts demucs
uv pip install --python venv/Scripts/python.exe --reinstall \
    --index-url https://download.pytorch.org/whl/cu124 torch==2.6.0+cu124 torchaudio==2.6.0+cu124
```

`setuptools<81` is not optional: `resemble-perth` imports `pkg_resources`, which
setuptools 81 removed, and the model refuses to initialise without a watermarker.

## Make a reference clip

```bash
python prepare_reference.py episode.mp4 --start 302 --end 311
```

Decode → demucs vocal separation (removes music and SFX) → silence trim → loudness
normalise → 24 kHz mono WAV. It refuses clips under 3 s and warns over 25 s.

A dirty reference is the single largest quality loss. Music bleeding into the
reference bleeds into the cloned voice, and no amount of parameter tuning fixes it.

## Use it

```bash
python scripts/doctor.py                 # is everything healthy?
python scripts/voice_switch.py on        # wire into Hermes + verify with a probe line
python scripts/voice_switch.py status
python scripts/voice_switch.py off
```

Installing this as a Hermes command provider means editing config with
`hermes config set` — never by hand.

## Tuning (measured, not guessed)

| `cfg_weight` | Pace on a 15-word line |
|---|---|
| 0.30 | 73 wpm — deliberate, may feel slow |
| 0.45 | 107 wpm — default recommendation |
| 0.55 | 129 wpm — close to conversational |

`temperature` 0.65 (down from the 0.8 default) visibly reduces take-to-take drift.
Full tables in `references/tuning.md`.

## Repository layout

```
SKILL.md                     skill entry point (Hermes reads this)
scripts/
  voice_server.py            resident synthesis service
  voice_client.py            Hermes command-provider client
  voice_switch.py            idempotent on / off / status / restart
  prepare_reference.py       source audio → clean reference clip
  doctor.py                  read-only health check
  voice_config.py            every knob, path-relative, env-overridable
references/                  pipeline, tuning, troubleshooting, legal
examples/                    JARVIS case study with real numbers
```

## Legal

Cloning a voice is regulated in most jurisdictions, and platforms enforce it faster
than courts do. Do not publish or distribute a clone of a real person or a
performance you do not hold rights to. Read `references/legal-and-ethics.md` before
you publish anything made with this.

The repository ships **no reference audio**. Cut your own, from material you have the
right to use — your own recordings first.

## License

MIT — see `LICENSE`.

The licence covers the software only. It grants no rights to any voice, recording, or
performance — see `references/legal-and-ethics.md`.
