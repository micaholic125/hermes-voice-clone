# Case study: a butler-voiced assistant, start to finish

A record of one real build, including the wrong turns. Numbers are from an
RTX 4060 Laptop (8 GB) on Windows 11. **No reference audio is included in this
repository** — for copyright reasons the clip stayed on the developer's machine, and
`references/legal-and-ethics.md` explains why.

## The request

"Give yourself a different voice. Something like JARVIS — that calm, British,
understated tone. Not this one."

Constraints that emerged from questioning:

- English voice, Chinese text replies (the user reads Chinese, listens in English).
- Personal use only.
- Willing to set up a local environment.
- Judgement by ear, not by spec sheet.

## Route chosen: zero-shot local

Cloud APIs were the fastest path to quality, but the source audio would have to be
uploaded and the platforms require a rights attestation for a voice the user does not
own. Local cloning keeps the audio on the machine and makes unlimited takes free.

Cost, measured later: ~5 GB of disk (CUDA torch), 45 s–4 min cold start, 7–13 s per
sentence warm.

## Stage 1 — find candidate lines

Source: a 33-minute compilation of the character's dialogue from the films.

Transcription: faster-whisper `small`, CPU int8, `vad_filter=True` → **515 segments in
276 s**, i.e. ~0.14× realtime. A keyword filter on `sir` / `mr.` narrowed it to 33
candidates with timestamps.

Lessons:

- Transcribe once, filter on the text, then cut. Cheaper than listening.
- Character compilations contain *other* characters (and, in this case, the sequel's
  villain). Confirm the speaker before cutting — the transcript alone will not tell you.

## Stage 2 — clean the reference

Five candidate clips, 4–9 s each, ran through `demucs --two-stems=vocals` to strip the
score.

The difference is not subtle: the raw clip carries the music bed, and a clone made from
it inherits a metallic sheen on every word. With the separated vocal, that artefact
disappeared.

Chosen reference: **9.2 s**, one speaker, trimmed, `loudnorm I=-16`, 24 kHz mono.

## Stage 3 — clone and listen

First runs were on CPU, because the 2.4 GB CUDA wheel kept stalling mid-download:
**~60 s per sentence**. On the GPU after `--reinstall +cu124`: **13 s per sentence**,
and the first call overall took 109 s (weights into VRAM).

Quality gate built after the third bad take: transcribe each take with Whisper, compare
with the input text, retry up to three times, ship nothing below 0.30 similarity. That
is what finally removed the "sometimes it hums" class of bug — a duration check alone
does not catch a loop wearing words.

## Stage 4 — the language trap

The user's replies are Chinese. Feeding Chinese text to an English-only zero-shot model
does not raise an error — it produces moaning with prosody. The fix is a hard branch:
detect CJK, route to a cloud voice, never let it reach the clone.

Evidence it was needed: `CJK text -> cloud fallback` fired **19 times** in the first day
of real use.

## Stage 5 — wire into Hermes

Resident HTTP server on `127.0.0.1:8765`, plus a 40-line client registered as
`tts.providers.<name>` (`type: command`).

The 120-second provider cap drove three decisions: the resident server (no cold start
per request), a 70 s retry budget, and a startup entry so the first reply of the day is
not a four-minute wait.

## Stage 6 — tuning, measured

Same 15-word line, three pace settings:

| `cfg_weight` | duration | pace |
|---|---|---|
| 0.30 | 12.24 s | 73.5 wpm |
| 0.45 | 8.44 s | 106.6 wpm |
| 0.55 | 6.96 s | 129.3 wpm |

The user picked 0.45 after listening: "still deliberate, but I am not waiting."

A false conclusion worth recording: the first comparison mixed samples of different
text lengths and used their seconds as evidence of pace. **Only compare pace on
identical text.**

## What it cost

| Item | Cost |
|---|---|
| Money | 0 |
| Disk | ~5.2 GB module + 10.2 GB of package cache (later evicted; C: filled up) |
| Time | one evening, most of it on the CUDA wheel and the language trap |
| Quality vs cloud | close on timbre, weaker on micro-prosody |

## What would be done differently

1. Download the CUDA wheel first, on a wired connection, before anything else.
2. Build the transcription grader before the first listening test — it converts
   "sounds wrong" into a number.
3. Decide the language policy up front. It is a branch in the code, not a tuning knob.
4. Keep the reference clip out of version control from the first commit, not after the
   repository is public.
