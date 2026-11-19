# Troubleshooting

Read the log first. `server.log` contains a line per take with its duration and
similarity score — that single line answers half of these.

```
[voice] take 1: 8.4s (expected 7.0s) similarity 0.91 :: 'Good evening sir, all systems'
```

---

## Service will not start

| Symptom | Cause | Fix |
|---|---|---|
| `FAILED to start`, log ends at `loading model` | VRAM exhausted or another process holds it | close other GPU apps; `nvidia-smi` to check |
| log ends at `loading model` for >5 min | weights still downloading/caching | watch `HF_HOME`; on a slow network set `HF_ENDPOINT` to a mirror |
| `reference audio missing` | no `reference.wav` | `prepare_reference.py`, or set `VOICE_REFERENCE` |
| traceback on `perth` / `PerthImplicitWatermarker` is None | `resemble-perth` needs `pkg_resources`, removed in setuptools 81 | `pip install "setuptools<81"` in the module's venv |
| traceback on `torch` import | wrong wheel | reinstall the CUDA wheel with `--reinstall ... +cu124` |

## It starts but nothing comes out

| Symptom | Cause | Fix |
|---|---|---|
| `timeout after 120s` from Hermes | provider was called cold | `voice_switch.py on` first, confirm `listening` |
| `every take was unintelligible` | reference is bad, or text is not the model's language | re-cut the reference; check the language guard fired |
| audio file is 0–2 KB | encode failed | run the ffmpeg command from `server.log` by hand |
| port open, `/health` hangs | process wedged | `voice_switch.py off`, then `on` |

## It speaks, but wrong

| Symptom | Cause | Fix |
|---|---|---|
| Humming / wordless moaning | CJK or other unsupported text fed to the clone | confirm `CJK text -> cloud fallback` in the log; set `VOICE_FALLBACK_VOICE` |
| Pace wanders between replies | `temperature` at 0.8, or `cfg_weight` changed mid-session | 0.65 and one fixed `cfg_weight`, then `restart` |
| Sounds like two people | reference contains a second speaker or laughter | re-cut; one speaker only |
| Metallic sheen | music residue in the reference | re-run `prepare_reference.py` without `--no-separate` |
| Cuts off mid-sentence | text chunked too small, or `MAX_SECONDS` hit | send whole sentences; keep `MAX_SECONDS` ≤ 90 |
| Same sentence sounds different every time | sampling randomness at high `exaggeration` | lower to 0.35–0.45 |

## Pace / speed

Pace is set by `cfg_weight` and the tempo of the reference clip itself. A fast-talking
reference makes a fast voice; slowing the reference down (1.05–1.1 s stretch with
ffmpeg `atempo=0.92`) shifts the whole voice without touching config.

## After a Hermes upgrade

Config survives; **code patches do not**. If a fix lived in Hermes' own source (not in
this skill), an upgrade or runtime rebuild silently removes it and the symptom returns
with "the config looks right". Re-apply from the notes you kept, then restart the gateway.

## Disk

Every `pip install` of torch caches a couple of GB. On Windows:

```powershell
uv cache clean
setx UV_CACHE_DIR D:\cache\uv
setx HF_HOME D:\cache\hf
```

Check with `doctor.py` — it reports uv and HF cache sizes on the system drive.
