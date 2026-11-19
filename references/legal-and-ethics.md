# Legal and ethical notes

Short version: **cloning a voice is regulated, platforms enforce faster than courts,
and this repository deliberately ships no reference audio.** If you only read one
paragraph, read that one.

This is engineering documentation, not legal advice.

---

## Why the repository contains no sample voice

Every convincing reference clip is somebody's performance. Film dialogue belongs to
the studio, the actor's performance to the actor, and the recording to whoever holds
the master. Publishing a clip — even nine seconds — invites a DMCA takedown and
removes the whole repository with it.

So the repo ships a **procedure**, not a sample. Cut your own, from material you have
the right to use. Your own voice is the safest possible start and also the best way to
learn what the pipeline does.

## What is protected

| Jurisdiction | Instrument | Effect |
|---|---|---|
| China | 民法典 第 1023 条 — voice protected by reference to portrait rights | unauthorised synthesis and publication of a person's voice can be actionable |
| China | 2024 北京互联网法院 voice-cloning case (配音师) | established damages for unauthorised AI reproduction of a dubbing artist's voice |
| USA | ELVIS Act (Tennessee, 2024), NO FAKES Act proposals, right of publicity | voice is a protected attribute; commercial use needs consent |
| EU | AI Act transparency duties + national personality rights | disclosure obligations for synthetic media |
| Platforms | ElevenLabs, MiniMax, Fish Audio terms | all require a written consent / rights attestation before cloning |

The common thread: **personal, private use sits in a grey zone; publication and
commercial use do not.**

## Practical rules

1. **Personal listening** — low risk. Keep it on your machine.
2. **Publishing audio, video, or a bot that speaks in the voice** — you need rights.
   Consent from the speaker, or a licence from the rights holder.
3. **Never** clone a voice to impersonate, defraud, or fabricate statements. That is
   the one line that turns a hobby project into a criminal matter in most countries.
4. **Label synthetic speech** when you share it. Cheap, and increasingly mandatory.
5. **Platform terms still apply** even where the law is unclear — a takedown does not
   need a court.

## Fictional characters

A character's voice is a performance, and the rights usually sit with the studio, not
the actor. "It's just a movie character" is not a defence: the studio is precisely the
party most likely to enforce. A private assistant that quotes a character is a very
different thing from publishing a distributable voice model.

## If you want to publish a voice

- Use **your own voice** — no rights issue at all, and it demonstrates the pipeline honestly.
- Use **public-domain or openly licensed** speech (LibriVox recordings are a common choice;
  check each reader's terms).
- Get **written consent** for any other voice, and keep it with the model.

## For commercial TTS platforms

ElevenLabs, MiniMax and Fish Audio all ask you to attest that you hold the rights.
Attesting falsely is a contract breach with a paper trail — the attestation is the
evidence against you. Do not treat it as a checkbox.
