"""Music theory utilities and pitch mapping for Tonic Ear."""

from __future__ import annotations

from dataclasses import dataclass

MALE_DO_C = 130.8
FEMALE_DO_C = 261.6

EQUAL_TEMPERAMENT = "equal_temperament"
JUST_INTONATION = "just_intonation"

TEMPERAMENT_OPTIONS = [
    {"id": EQUAL_TEMPERAMENT, "label": "12-Tone Equal Temperament"},
    {"id": JUST_INTONATION, "label": "5-limit Just Intonation"},
]

KEY_OPTIONS = [
    {"id": "C", "label": "1=C"},
    {"id": "C#/Db", "label": "1=C#/Db"},
    {"id": "D", "label": "1=D"},
    {"id": "D#/Eb", "label": "1=D#/Eb"},
    {"id": "E", "label": "1=E"},
    {"id": "F", "label": "1=F"},
    {"id": "F#/Gb", "label": "1=F#/Gb"},
    {"id": "G", "label": "1=G"},
    {"id": "G#/Ab", "label": "1=G#/Ab"},
    {"id": "A", "label": "1=A"},
    {"id": "A#/Bb", "label": "1=A#/Bb"},
    {"id": "B", "label": "1=B"},
]

KEY_OFFSETS = {entry["id"]: index for index, entry in enumerate(KEY_OPTIONS)}

GENDER_OPTIONS = [
    {"id": "male", "label": "Male", "baseDoAtC": MALE_DO_C},
    {"id": "female", "label": "Female", "baseDoAtC": FEMALE_DO_C},
]

GENDER_BASE_DO = {"male": MALE_DO_C, "female": FEMALE_DO_C}

# Semitone ratios relative to Do for 5-limit just intonation.
JUST_INTONATION_RATIOS = [
    1 / 1,
    16 / 15,
    9 / 8,
    6 / 5,
    5 / 4,
    4 / 3,
    45 / 32,
    3 / 2,
    8 / 5,
    5 / 3,
    9 / 5,
    15 / 8,
]


@dataclass(frozen=True)
class NoteDefinition:
    """Single note entry in a movable-do system."""

    token: str
    display: str
    degree: int
    accidental: str
    semitone: int
    enharmonic_degree: int | None = None
    enharmonic_accidental: str | None = None


CHROMA_NOTES = [
    NoteDefinition(token="1", display="1", degree=1, accidental="natural", semitone=0),
    NoteDefinition(
        token="#1",
        display="#1/b2",
        degree=1,
        accidental="sharp",
        semitone=1,
        enharmonic_degree=2,
        enharmonic_accidental="flat",
    ),
    NoteDefinition(token="2", display="2", degree=2, accidental="natural", semitone=2),
    NoteDefinition(
        token="#2",
        display="#2/b3",
        degree=2,
        accidental="sharp",
        semitone=3,
        enharmonic_degree=3,
        enharmonic_accidental="flat",
    ),
    NoteDefinition(token="3", display="3", degree=3, accidental="natural", semitone=4),
    NoteDefinition(token="4", display="4", degree=4, accidental="natural", semitone=5),
    NoteDefinition(
        token="#4",
        display="#4/b5",
        degree=4,
        accidental="sharp",
        semitone=6,
        enharmonic_degree=5,
        enharmonic_accidental="flat",
    ),
    NoteDefinition(token="5", display="5", degree=5, accidental="natural", semitone=7),
    NoteDefinition(
        token="#5",
        display="#5/b6",
        degree=5,
        accidental="sharp",
        semitone=8,
        enharmonic_degree=6,
        enharmonic_accidental="flat",
    ),
    NoteDefinition(token="6", display="6", degree=6, accidental="natural", semitone=9),
    NoteDefinition(
        token="#6",
        display="#6/b7",
        degree=6,
        accidental="sharp",
        semitone=10,
        enharmonic_degree=7,
        enharmonic_accidental="flat",
    ),
    NoteDefinition(token="7", display="7", degree=7, accidental="natural", semitone=11),
]

NOTE_BY_TOKEN = {note.token: note for note in CHROMA_NOTES}

DIFFICULTY_LEVELS = {
    "L1": {
        "id": "L1_TRIAD",
        "label": "Triad Notes",
        "tokens": ["1", "3", "5"],
        "display": "1,3,5",
    },
    "L2": {
        "id": "L2_PENTA",
        "label": "Pentatonic Expansion",
        "tokens": ["1", "2", "3", "5", "6"],
        "display": "1,2,3,5,6",
    },
    "L3": {
        "id": "L3_HEPTA",
        "label": "Heptatonic",
        "tokens": ["1", "2", "3", "4", "5", "6", "7"],
        "display": "1,2,3,4,5,6,7",
    },
    "L4": {
        "id": "L4_CHROMA",
        "label": "Chromatic",
        "tokens": ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
        "display": "1,#1/b2,2,#2/b3,3,4,#4/b5,5,#5/b6,6,#6/b7,7",
    },
    "L5": {
        "id": "L5_WHOLE_TONE",
        "label": "Whole-Tone Proximity",
        "tokens": ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
        "display": "L5 uses close-note drills (1 whole tone / 2 semitones)",
    },
    "L6": {
        "id": "L6_SEMITONE",
        "label": "Semitone Proximity",
        "tokens": ["1", "#1", "2", "#2", "3", "4", "#4", "5", "#5", "6", "#6", "7"],
        "display": "L6 uses closest-note drills (1 semitone)",
    },
}


def calculate_do_frequency(gender: str, key_id: str) -> float:
    """Calculate Do frequency for selected gender and key."""

    if gender not in GENDER_BASE_DO:
        raise ValueError(f"Unknown gender '{gender}'")
    if key_id not in KEY_OFFSETS:
        raise ValueError(f"Unknown key '{key_id}'")

    base_do = GENDER_BASE_DO[gender]
    semitone_shift = KEY_OFFSETS[key_id]
    return base_do * (2 ** (semitone_shift / 12))


def note_frequency(semitone: int, do_frequency: float, temperament: str) -> float:
    """Get note frequency for semitone offset from Do."""

    if temperament == EQUAL_TEMPERAMENT:
        return do_frequency * (2 ** (semitone / 12))
    if temperament == JUST_INTONATION:
        return do_frequency * JUST_INTONATION_RATIOS[semitone]
    raise ValueError(f"Unknown temperament '{temperament}'")


def get_note_pool(level: str) -> list[NoteDefinition]:
    """Return note definitions for the requested difficulty level."""

    if level not in DIFFICULTY_LEVELS:
        raise ValueError(f"Unknown level '{level}'")
    tokens = DIFFICULTY_LEVELS[level]["tokens"]
    return [NOTE_BY_TOKEN[token] for token in tokens]


def build_note_payload(note: NoteDefinition, do_frequency: float, temperament: str) -> dict:
    """Serialize note data for frontend playback and UI."""

    payload = {
        "token": note.token,
        "label": note.display,
        "degree": note.degree,
        "accidental": note.accidental,
        "semitone": note.semitone,
        "frequency": round(note_frequency(note.semitone, do_frequency, temperament), 4),
    }
    if note.enharmonic_degree and note.enharmonic_accidental:
        payload["enharmonic"] = {
            "degree": note.enharmonic_degree,
            "accidental": note.enharmonic_accidental,
        }
    return payload


def get_difficulty_metadata() -> list[dict]:
    """Difficulty metadata exposed by the API."""

    return [
        {
            "level": level,
            "id": info["id"],
            "label": info["label"],
            "displayNotes": info["display"],
            "tokens": info["tokens"],
        }
        for level, info in DIFFICULTY_LEVELS.items()
    ]
