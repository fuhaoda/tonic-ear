# Tonic Ear

Tonic Ear is a progressive ear-training web app for pitch and scale recognition.
It is built with FastAPI + vanilla JS and is designed for desktop, iPad, and iPhone browsers.

## Purpose

This app helps train:

- Pitch comparison (which note is higher)
- Note ordering (3-note / 4-note low-to-high sorting)
- Scale-step interval distance
- Single-note movable-do recognition

Each session has 20 questions with first-attempt scoring.

## Core Features

- 20-question fixed sessions
- Module ladder with fixed difficulty per module
- Settings:
  - Instrument (`Piano` / `Guitar`)
  - Gender base Do (`male=130.8Hz`, `female=261.6Hz`)
  - Key (`1=C` to `1=B`)
  - Temperament (`Equal` only)
- Repeat playback during quiz
- Optional visual pitch hints
- First-attempt scoring + optional retry practice + show answer
- Local progress persistence (`localStorage`)
- Desktop keyboard `1-7` plus alternate layout `m,.jklu`
- Mobile/tablet compact keyboard `1-7` + optional full-screen keyboard mode
- Browser history and top `Home` button navigation

## Modules

- `M2-L1..L6`: Two-note higher/lower
- `M3-L1..L6`: Three-note sorting (low -> high)
- `M4-L1..L6`: Four-note sorting (low -> high)
- `MI-L1..L3`: Two-note scale-step distance
- `MS-L1..L4`: Single-note guess (no visual hint)

## Level Definitions

`M2/M3/M4` levels:

- `L1`: Triad (`1,3,5`)
- `L2`: Pentatonic (`1,2,3,5,6`)
- `L3`: Heptatonic (`1,2,3,4,5,6,7`)
- `L4`: Chromatic (`1,#1,2,#2,3,4,#4,5,#5,6,#6,7`)
- `L5`: Whole-tone proximity (adjacent spacing = 2 semitones)
- `L6`: Semitone proximity (adjacent spacing = 1 semitone)

Notes:

- `M4-L1` internally uses the `L2` pool so four unique notes are possible.
- `MI` only supports `L1..L3`.
- `MS` only supports `L1..L4`.

## Audio Architecture (Current)

This version uses **raw sample playback only** for all playback (quiz + keyboard):

- Sources:
  - University of Iowa MIS Piano (`ff`)
  - University of Iowa MIS Guitar (`ff`, onset-sliced from range recordings)
- Singing-focused range: **70-1000Hz** with dense semitone coverage (`D2..B5`, 46 files)
- Output assets:
  - `web/assets/audio/piano/`
  - `web/assets/audio/guitar/`
- File format: AAC `.m4a`, mono, 44.1kHz
- Fixed duration:
  - Piano: **1.0 second** per sample
  - Guitar: **1.5 seconds** per sample
- Offline preprocessing only:
  - start alignment (`silenceremove` for piano, `aubio` onset alignment for guitar)
  - peak normalization for consistent loudness
- Runtime playback:
  - WebAudio single engine only
  - no oscillator fallback
  - no runtime timbre shaping
  - quiz playback always uses full raw sample length
  - keyboard playback always triggers full sample-length one-shot per tap
  - polyphony cap = 10 active voices (extra taps are ignored until a voice slot frees)

Current built package sizes:

- Piano: about **0.82MB** (46 samples)
- Guitar: about **1.19MB** (46 samples at 1.5s)

## Build/Rebuild Samples

Requirements:

- `python3`
- `ffmpeg`
- `aubioonset` and `aubiopitch` (required for guitar slicing)
- internet access to the Iowa source files

Rebuild piano:

```bash
python3 scripts/build_piano_samples.py --clean --refresh-sources --duration 1.0 --bitrate 160k
```

Rebuild guitar (default output is 1.5s per note):

```bash
python3 scripts/build_guitar_samples.py --clean --refresh-sources --duration 1.5 --bitrate 160k
```

This regenerates:

- `web/assets/audio/piano/*.m4a` (46 files)
- `web/assets/audio/piano/manifest.json`
- `web/assets/audio/guitar/*.m4a` (46 files)
- `web/assets/audio/guitar/manifest.json`

## Quick Start (Local)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 2121 --reload
```

Open:

- `http://localhost:2121`
- `http://127.0.0.1:2121`

Do not use `http://0.0.0.0:2121` in Safari.

## Docker Deployment

Build and run:

```bash
docker compose up -d --build
```

Check:

```bash
docker compose ps
docker compose logs -f
```

Stop:

```bash
docker compose down
```

Default mapping is host `2121` -> container `8080`.

## Update On Linux Server (Pull + Rebuild + Cleanup)

SSH into your server and run:

```bash
cd /path/to/tonic-ear
git fetch --all
git checkout main
git pull --ff-only
docker compose down
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs -f --tail=80
```

Open:

- `http://<server-lan-ip>:2121`

Example:

- `http://192.168.86.45:2121`

### Clean Unused Docker Data

Safe cleanup (recommended first):

```bash
docker image prune -f
docker builder prune -f
```

Deeper cleanup (removes all unused images/containers/networks/volumes):

```bash
docker system prune -a --volumes -f
```

Check disk usage before/after:

```bash
docker system df
```

## Home LAN Access

If your Linux server LAN IP is `192.168.86.45`, devices on the same LAN can use:

- `http://192.168.86.45:2121`

## How To Use

1. Choose `Instrument`, `Gender`, `Key`, and `Temperament`.
2. Start a module.
3. Each question auto-plays once.
4. Use `Repeat` as needed.
5. Submit answer.
6. If first attempt is wrong, score is locked but you can retry for practice or click `Show Answer`.
7. Use `Next` to continue.
8. Review score and mistake replay at the end.

## Keyboard / Touch Control

- Desktop:
  - press `1..7`
  - alternate layout: `m=1`, `,=2`, `.=3`, `j=4`, `k=5`, `l=6`, `u=7`
  - hold `Shift` while pressing a degree key to shift up one octave
  - hold `Ctrl` while pressing a degree key to shift down one octave
- Mobile/Tablet compact mode:
  - tap `1..7`
  - tap `Full Keyboard` (top-right of compact pad) to enter full-screen mode
- Mobile/Tablet full-screen mode:
  - right side numeric layout: `7 / 456 / 123`
  - left side: `Oct+` and `Oct-` for octave shift
  - hold `Oct+` and `Oct-` together for ~400ms to return to compact mode
- Each tap triggers the full raw sample length of the selected instrument (piano 1.0s, guitar 1.5s), independent of press length
- Up to 10 notes can overlap; above that new taps are dropped

## iOS Audio Unlock Behavior

- Unlock timeout is tuned to `800ms` (less aggressive than older 500ms).
- First timeout no longer hard-fails the app; audio stays in a "pending unlock" state and retries on the next user gesture.
- AudioContext recreation is delayed until repeated failures, reducing false failures on iPhone Safari refresh.

If audio is silent right after refresh on iPhone, tap once on any keyboard key or `Repeat` to trigger the next unlock attempt.

## Docker Build SSL Note (Corporate Network)

If build fails with `CERTIFICATE_VERIFY_FAILED`, pass trusted hosts to pip during build:

```bash
docker compose build \
  --build-arg PIP_EXTRA_ARGS="--trusted-host pypi.org --trusted-host files.pythonhosted.org"
docker compose up -d --force-recreate
```

## API

### `GET /api/v1/meta`

Returns settings options, module list, difficulty metadata, and defaults.

### `POST /api/v1/session`

Request:

```json
{
  "moduleId": "M2-L1",
  "instrument": "guitar",
  "gender": "male",
  "key": "C",
  "temperament": "equal_temperament"
}
```

Response includes:

- `sessionId`
- `settings`
- `questions` (20)

Each note payload now includes `sampleId` and `midi` for direct sample playback.

## Tests

```bash
source .venv/bin/activate
pytest -q
```

Coverage includes:

- Equal temperament frequency correctness
- Module generation and constraints
- 70-1000Hz sample-manifest checks for piano and guitar (46 files each)
- `< 10 cents` mapping bound verification
- API validation (`just_intonation` rejected)

## Local Data

Saved in browser local storage:

- `tonicEar.settings`
- `tonicEar.history`
- `tonicEar.moduleStats`

`history` and `moduleStats` are tracked per instrument.

No account system in v1.
