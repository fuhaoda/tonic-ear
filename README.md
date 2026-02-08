# Tonic Ear

Tonic Ear is a web app for progressive ear training.
It helps you improve pitch discrimination through structured drills, repeatable question sets, and immediate audio feedback.

## Purpose

Tonic Ear is designed to train:

- Pitch height judgment (which note is higher/lower)
- Relative ordering (sort 3 or 4 notes low to high)
- Scale-step distance recognition
- Single-note movable-do recognition without visual hint

The app supports repeated practice at the same difficulty level while keeping score based on first attempt.

## Core Features

- 20 questions per session, fixed by module
- Progressive module ladder (L1 -> L6)
- Global settings for:
  - Gender base Do (`male=130.8Hz`, `female=261.6Hz`)
  - Key (`1=C` through `1=B`)
  - Temperament (`Equal` / `Just`, API values: `equal_temperament` / `just_intonation`)
- Repeat playback for each question
- Tone length selector (`Short 900ms / Normal 1300ms / Full 2000ms`)
- First-attempt scoring with optional retry on the same question
- Optional `Show Answer` after first incorrect attempt
- Visual hint mode (toggle on/off)
- Local progress persistence (`localStorage`)
- Desktop keyboard tones (`1-7`) and mobile touch keyboard (`1-7`, press and hold)
- Piano sample playback with runtime nearest-note mapping (`<=20 cents` error)

## Modules

- `M2-L1..L6`: Two-note higher/lower
- `M3-L1..L6`: Three-note sorting (low -> high)
- `M4-L1..L6`: Four-note sorting (low -> high)
- `MI-L1..L3`: Two-note scale-step distance
- `MS-L1..L4`: Single-note guess (no visual hint)

## Level Definitions

`M2/M3/M4` use `L1..L6`:

- `L1` (Triad): only `1,3,5`
- `L2` (Pentatonic): `1,2,3,5,6`
- `L3` (Heptatonic): `1,2,3,4,5,6,7`
- `L4` (Chromatic): full 12-note set (`1,#1,2,#2,3,4,#4,5,#5,6,#6,7`)
- `L5` (Whole-tone proximity): notes are constrained to one whole tone apart (2 semitones)
- `L6` (Semitone proximity): notes are constrained to one semitone apart

How spacing constraints apply:

- `M2-L5/L6`: the two notes differ by exactly 2/1 semitones
- `M3-L5/L6`: when sorted low to high, adjacent notes differ by 2/1 semitones
- `M4-L5/L6`: when sorted low to high, adjacent notes differ by 2/1 semitones

Other module ranges:

- `MI` supports `L1..L3` only
- `MS` supports `L1..L4` only

Note: `M4-L1` internally uses the `L2` note pool because `L1` has only 3 unique notes and four-note sorting requires 4 unique notes.

## Tech Stack

- Backend: FastAPI
- Frontend: Vanilla HTML/CSS/JavaScript
- Audio: 35-piano-sample pack (`.m4a`) + WebAudio playback-rate mapping
- Tests: pytest + FastAPI TestClient
- Deployment: local Python or Docker

## Piano Audio Pack

The app ships with a compact piano sample set in `web/assets/audio/piano/`:

- `35` base samples (`C3` to `Bb5`)
- `manifest.json` with sample metadata and mapping diagnostics
- runtime mapping from target note Hz to nearest sample + `playbackRate`
- hard pitch error guard: `abs(centsError) <= 20` (`< 0.2` semitone)
- samples are rebuilt with onset alignment and loudness normalization:
  - per-sample onset detection and trim
  - fixed `5ms` pre-attack padding for consistent start timing
  - `loudnorm` targeting `-20 LUFS`, `TP -2 dBTP`
  - fixed length `2000ms` for all files
- source set: University of Iowa MIS Piano (`mf`)

Current package size target/hard cap:

- target: `<10MB`
- hard cap: `<20MB`

Rebuild samples (download + transcode + manifest):

```bash
python3 scripts/build_piano_samples.py --clean --bitrate 128k
```

Requirements for rebuild:

- `ffmpeg` available on PATH
- network access to University of Iowa MIS source files

Optional knobs:

```bash
python3 scripts/build_piano_samples.py --clean --bitrate 96k --duration 2.0 --target-mb 10 --max-total-mb 20
```

## Quick Start (Local)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 2121 --reload
```

Open:

- `http://localhost:2121` (recommended)
- `http://127.0.0.1:2121` (recommended)

Important:

- `0.0.0.0` is the server bind address, not a reliable browser URL.
- In Safari especially, avoid `http://0.0.0.0:2121`.

## Docker Deployment

### Prerequisites

- Docker Engine / Docker Desktop installed
- Docker daemon running (`docker info` should succeed)

### Start with Docker Compose

```bash
docker compose up -d --build
```

Open `http://localhost:2121`.

### Verify container status

```bash
docker compose ps
docker compose logs -f
```

### Stop services

```bash
docker compose down
```

### Pull latest code and redeploy

```bash
git pull
docker compose up -d --build
```

### Notes

- App listens on container port `8080`
- Host port mapping is `2121:8080` (configured in `docker-compose.yml`)
- If host port `2121` is occupied, change the `ports` mapping in `docker-compose.yml`
- Sample assets are already included in the image via `COPY web ./web`

## How To Use

1. Open Dashboard.
2. Choose `Gender`, `Key`, and `Temperament`.
3. Select a module and start.
4. During quiz:
   - `Repeat` to replay the current audio
   - Auto-play uses selected tone length, `Repeat` always uses full 2000ms
   - Answer the question
   - If first attempt is incorrect, score is locked for that question
   - You can retry for practice, or click `Show Answer`
5. Click `Next` to move on.
6. At the end, view score and mistake replay.
7. Click the top `Home` button at any time to return to Dashboard.

## Input Controls

### Desktop keyboard

- Tap `1-7` for immediate piano-like notes
- Hold key beyond `300ms` to continue into sustained tone
- Release key to stop sustain
- Every tap guarantees at least `300ms` audible output
- App tab must be focused
- Press `Home` key to return to Dashboard quickly

### Tablet/mobile touch keyboard

- Tap `1-7` for immediate notes
- Hold button beyond `300ms` to sustain
- Release to stop sustain

## Visual Hint Behavior

- Default: OFF
- If enabled, quiz displays a 1-7 guide lane with note markers for compare/sort modules
- Single-note module keeps visual hint hidden by design

## API

### `GET /api/v1/meta`

Returns app metadata:

- Settings options (gender/key/temperament)
- Module definitions
- Difficulty definitions
- Defaults

### `POST /api/v1/session`

Request body:

```json
{
  "moduleId": "M2-L1",
  "gender": "male",
  "key": "C",
  "temperament": "equal_temperament"
}
```

Response includes:

- `sessionId`
- `settings`
- `questions` (20 items)

## Data Persistence

Local browser storage keys:

- `tonicEar.settings`
- `tonicEar.history`
- `tonicEar.moduleStats`

No account system is required for v1.

## Testing

```bash
. .venv/bin/activate
pytest -q
```

Audio-specific checks included in test suite:

- 35 equal-temperament unique frequencies match 35 sample bases
- 299 unique target frequencies map within `<=20 cents`
- all 576 gender/key/temperament combinations pass mapping bound
- sample manifest and package size guard (`<10MB`)

## Troubleshooting

### Blank page in Safari

Use `http://localhost:2121` instead of `http://0.0.0.0:2121`.

### No sound on first interaction

Some browsers block audio before user gesture.
Click any button (for example `Repeat`) once, then audio playback is enabled.

### Port conflict

If `2121` is occupied, run with a different port:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 3000 --reload
```

Then open `http://localhost:3000`.
