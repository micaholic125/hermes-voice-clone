# The pipeline, end to end

Six stages. Each has one decision that determines whether the result sounds right,
and two of them (source, reference) account for most of the quality.

---

## 1. Decide the route before touching a model

| Route | Cloning | Cost | When it wins |
|---|---|---|---|
| Preset voice (Edge, cloud) | none | free / cheap | you only need a *type* of voice, not a specific person |
| **Zero-shot local (this repo)** | 10–30 s reference | free | personal use, offline, privacy, unlimited takes |
| Few-shot fine-tune (GPT-SoVITS etc.) | 1–3 min material + training | free, hours of compute | fidelity above convenience |
| Commercial API (ElevenLabs, MiniMax) | upload sample | per character + clone fee | fastest path to the best quality, and the voice is yours or licensed |

Decision rule used here: **personal use + a specific voice + willingness to tinker →
zero-shot local**. It wins on cost and privacy, loses a little fidelity to a fine-tune
and a lot to a commercial API.

## 2. Source the audio — the quality ceiling

The reference is the ceiling; nothing downstream can exceed it. Ranked by usefulness:

1. **Your own recording** — clean, lawful, no separation needed.
2. **Interview / podcast / audiobook** of the target speaker — clean, but the delivery
   is conversational, not the character's.
3. **Film or TV dialogue** — the performance you actually want, but buried in music and
   effects; needs separation and still keeps artefacts.
4. **Compressed clips from social video** — last resort; codec noise becomes voice noise.

Find candidate lines cheaply: transcribe the whole file once (faster-whisper with
`vad_filter=True`, CPU int8 runs ~0.15× realtime), then filter the segment list by
keywords the character says (`sir`, `mr.`, the character's catchphrases).

```python
segments, _ = model.transcribe(path, language="en", vad_filter=True, beam_size=1,
                               condition_on_paragraph=False)
```

## 3. Cut and clean the reference

```bash
python scripts/prepare_reference.py source.mp4 --start 302.0 --end 311.2
```

- **demucs `--two-stems=vocals`** removes the music bed. Non-negotiable for film audio.
- **3–25 s**, one speaker, no overlapping dialogue, no laugh track, no stingers.
- **Trim silence** at both ends; the model reads trailing silence as part of the voice.
- **Loudness-normalise** so takes come out at a consistent level (`loudnorm I=-16`).
- Keep it mono 24 kHz.

Sanity check before cloning: play the reference. If you can hear music, the clone will
inherit it as a metallic sheen you cannot tune away.

## 4. Clone

Zero-shot: the model is given `(reference audio, text)` and reproduces the timbre.

```
generate(text, audio_prompt_path=reference, cfg_weight=0.45,
         exaggeration=0.45, temperature=0.65, repetition_penalty=1.2)
```

- **No training step.** If the result is wrong, the reference is wrong, not the model.
- **Grade every take.** Transcribe the output and compare with the input text
  (difflib ratio on normalised words). This catches hums and loops that a duration
  check sails past.
- **Write fewer, longer takes** rather than many short ones — prosody has no context
  to work with inside 6 words.

## 5. Wire it into Hermes

Run the model behind a localhost server; expose a tiny client as a command provider:

```yaml
tts:
  provider: jarvis
  providers:
    jarvis:
      type: command
      command: <venv>/python <skill>/scripts/voice_client.py {text_path} {output_path} {format}
```

Set it with `hermes config set`, never by editing YAML by hand. The provider is
invoked with a **120-second cap** — hence the resident server and the 70 s retry budget.

Add a startup entry so the first reply of the day is not a four-minute wait.

## 6. Operate

`status` → `on` / `off` / `restart`. Every action verifies its own outcome.
Configuration is read at startup: **changing a parameter without `restart` does nothing**,
which is the single most common false "the setting did not work" report.

---

## What to do when it sounds wrong

Work down this list in order; each step is cheaper than the next.

1. **Read `server.log`.** The `similarity` score tells you whether the take was
   understood at all before you theorise about timbre.
2. **Check the language.** CJK into an English model hums; the fallback should have
   caught it — verify it fired.
3. **Check the reference.** Duration, music residue, one speaker, right person.
4. **Only then tune** `cfg_weight` (pace) and `exaggeration` (performance), one at a
   time, with `restart` between changes.
