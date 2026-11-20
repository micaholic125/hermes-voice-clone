# Tuning

All numbers below were measured on one 15-word English line, one reference clip,
RTX 4060 Laptop. Absolute pace will differ with the reference; the *shape* of the
curves will not.

## Pace: `cfg_weight`

| Value | Duration | Pace | Character |
|---|---|---|---|
| 0.30 | 12.2 s | 73 wpm | deliberate, butler-slow; listeners may find it sluggish |
| 0.45 | 8.4 s | 107 wpm | **default** — weight without the wait |
| 0.55 | 7.0 s | 129 wpm | close to conversational, loses some gravity |

Reference point: ordinary English conversation is 130–150 wpm. Anything below
~90 wpm reads as "reading to you", not "talking to you".

**Do not change `cfg_weight` per sample.** It is a pacing dial, not a mood dial;
mixing values across a session is what makes a voice feel inconsistent.

## Performance: `exaggeration`

- `0.20` — flat, newsreader-like, no irony.
- `0.45` — default; light colour, suits an assistant.
- `0.70`+ — theatrical; drifts quickly into caricature on zero-shot voices.

## Variance: `temperature`

Default is 0.8. At 0.8 the same text produces noticeably different prosody each run,
which users report as "the speed keeps changing". **0.65** keeps expressiveness and
removes most of the drift.

## Reliability: retries and grading

| Knob | Default | Meaning |
|---|---|---|
| `TEMPERATURE` | 0.65 | sampling randomness |
| `MIN_P` | 0.05 | nucleus floor; raise to 0.1 if takes ramble |
| `REPETITION_PENALTY` | 1.2 | raise to 1.3 for text with repeated phrases |
| `TAKES` | 3 | attempts per request |
| `VERIFY_MIN_SIMILARITY` | 0.55 | accept a take immediately at or above this |
| `SHIP_MIN_SIMILARITY` | 0.30 | below this, ship nothing and return an error |
| `MAX_SECONDS` | 70 | retry budget; must stay under Hermes' 120 s cap |

The `similarity` score is a word-sequence ratio between what Whisper heard and what
you asked for. Empirically: ≥0.75 is clean, 0.55–0.75 is usable with a slight stumble,
<0.45 is usually a hum or a loop wearing words.

## Symptom → parameter

| Symptom | First move |
|---|---|
| Pace drifts between replies | confirm `TEMPERATURE` 0.65 and one fixed `CFG_WEIGHT`; `restart` |
| Voice sounds bored/flat | raise `exaggeration` to 0.55 |
| Voice sounds like a caricature | drop `exaggeration` to 0.30 |
| Sentences end mid-thought | the text was chunked too small — let the caller send whole sentences |
| Long text truncates | the 120 s cap hit; split the text at sentence boundaries upstream |
| Every take fails the gate | the reference is wrong, not the parameters: re-cut it |

## What tuning cannot fix

- Music bleeding through the reference (metallic sheen).
- A different speaker in the reference (voice averages two people).
- The wrong accent entirely (zero-shot clones timbre, not a regional accent it never heard).
- Non-native accent: an English reference makes Chinese sound foreign. The router gets
the words right; only a same-language reference fixes the accent.
