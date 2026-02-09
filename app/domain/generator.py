"""Session and question generation for Tonic Ear."""

from __future__ import annotations

import random
import uuid
from dataclasses import dataclass
from itertools import combinations

from app.domain.audio_samples import map_target_frequency, validate_instrument
from app.domain.music import (
    EQUAL_TEMPERAMENT,
    GENDER_OPTIONS,
    KEY_OPTIONS,
    TEMPERAMENT_OPTIONS,
    build_note_payload,
    calculate_do_frequency,
    get_difficulty_metadata,
    get_note_pool,
    note_frequency,
)

QUESTION_COUNT = 20
PITCH_MODULE_LEVELS = ["L1", "L2", "L3", "L4", "L5", "L6"]
INSTRUMENT_OPTIONS = [
    {"id": "piano", "label": "Piano"},
    {"id": "guitar", "label": "Guitar"},
]


@dataclass(frozen=True)
class ModuleConfig:
    module_id: str
    title: str
    question_type: str
    level: str
    recommended_order: int


def _build_modules() -> list[ModuleConfig]:
    modules: list[ModuleConfig] = []
    order = 1

    # Two-note compare.
    for level in PITCH_MODULE_LEVELS:
        modules.append(
            ModuleConfig(
                module_id=f"M2-{level}",
                title=f"Two Notes: Higher or Lower ({level})",
                question_type="compare_two",
                level=level,
                recommended_order=order,
            )
        )
        order += 1

    # Three-note sorting.
    for level in PITCH_MODULE_LEVELS:
        modules.append(
            ModuleConfig(
                module_id=f"M3-{level}",
                title=f"Three Notes: Sort Low to High ({level})",
                question_type="sort_three",
                level=level,
                recommended_order=order,
            )
        )
        order += 1

    # Four-note sorting.
    for level in PITCH_MODULE_LEVELS:
        modules.append(
            ModuleConfig(
                module_id=f"M4-{level}",
                title=f"Four Notes: Sort Low to High ({level})",
                question_type="sort_four",
                level=level,
                recommended_order=order,
            )
        )
        order += 1

    # Scale-step interval (L1-L3 only).
    for level in ["L1", "L2", "L3"]:
        modules.append(
            ModuleConfig(
                module_id=f"MI-{level}",
                title=f"Two Notes: Scale-Step Distance ({level})",
                question_type="interval_scale",
                level=level,
                recommended_order=order,
            )
        )
        order += 1

    # Single note without visual hint.
    for level in ["L1", "L2", "L3", "L4"]:
        modules.append(
            ModuleConfig(
                module_id=f"MS-{level}",
                title=f"Single Note Guess ({level})",
                question_type="single_note",
                level=level,
                recommended_order=order,
            )
        )
        order += 1

    return modules


MODULES = _build_modules()
MODULE_MAP = {module.module_id: module for module in MODULES}


def get_meta() -> dict:
    """Public metadata for frontend configuration."""

    return {
        "genders": GENDER_OPTIONS,
        "keys": KEY_OPTIONS,
        "temperaments": TEMPERAMENT_OPTIONS,
        "instruments": INSTRUMENT_OPTIONS,
        "difficulties": get_difficulty_metadata(),
        "modules": [
            {
                "id": module.module_id,
                "title": module.title,
                "questionType": module.question_type,
                "level": module.level,
                "recommendedOrder": module.recommended_order,
            }
            for module in MODULES
        ],
        "defaults": {
            "gender": "male",
            "key": "C",
            "temperament": EQUAL_TEMPERAMENT,
            "instrument": "piano",
            "showVisualHints": False,
            "questionCount": QUESTION_COUNT,
        },
    }


def generate_session(
    module_id: str,
    gender: str,
    key: str,
    temperament: str,
    instrument: str = "piano",
) -> dict:
    """Generate one training session with 20 questions."""

    if module_id not in MODULE_MAP:
        raise ValueError(f"Unknown module '{module_id}'")

    validate_instrument(instrument)

    module = MODULE_MAP[module_id]
    effective_level = _resolve_note_pool_level(module)
    notes_pool = get_note_pool(effective_level)
    do_frequency = calculate_do_frequency(gender=gender, key_id=key)

    questions = [
        _generate_question(
            module=module,
            question_number=index + 1,
            notes_pool=notes_pool,
            do_frequency=do_frequency,
            temperament=temperament,
            instrument=instrument,
        )
        for index in range(QUESTION_COUNT)
    ]

    return {
        "sessionId": str(uuid.uuid4()),
        "settings": {
            "moduleId": module_id,
            "moduleTitle": module.title,
            "level": module.level,
            "effectiveNotePoolLevel": effective_level,
            "questionType": module.question_type,
            "gender": gender,
            "key": key,
            "temperament": temperament,
            "instrument": instrument,
            "questionCount": QUESTION_COUNT,
            "doFrequency": round(do_frequency, 4),
        },
        "questions": questions,
    }


def _resolve_note_pool_level(module: ModuleConfig) -> str:
    """Resolve note pool level used to keep questions valid."""

    # L1 triad has only three unique notes, but 4-note sorting requires four pitches.
    # We lift only this case to L2 to keep unique-note constraint intact.
    if module.question_type == "sort_four" and module.level == "L1":
        return "L2"
    return module.level


def _generate_question(
    module: ModuleConfig,
    question_number: int,
    notes_pool: list,
    do_frequency: float,
    temperament: str,
    instrument: str,
) -> dict:
    if module.question_type == "compare_two":
        return _generate_compare_two(module, question_number, notes_pool, do_frequency, temperament, instrument)
    if module.question_type == "sort_three":
        return _generate_sort(
            module,
            question_number,
            notes_pool,
            do_frequency,
            temperament,
            instrument,
            note_count=3,
        )
    if module.question_type == "sort_four":
        return _generate_sort(
            module,
            question_number,
            notes_pool,
            do_frequency,
            temperament,
            instrument,
            note_count=4,
        )
    if module.question_type == "interval_scale":
        return _generate_interval(module, question_number, notes_pool, do_frequency, temperament, instrument)
    if module.question_type == "single_note":
        return _generate_single_note(module, question_number, notes_pool, do_frequency, temperament, instrument)
    raise ValueError(f"Unsupported question type '{module.question_type}'")


def _generate_compare_two(module, question_number, notes_pool, do_frequency, temperament, instrument) -> dict:
    interval_step = _interval_constraint_for_level(module.level)
    picked = _pick_compare_notes(notes_pool, interval_step)
    note_payloads = _build_note_payloads(picked, do_frequency, temperament, instrument)

    correct_answer = "first_higher" if picked[0].semitone > picked[1].semitone else "second_higher"

    return {
        "id": f"{module.module_id}-Q{question_number}",
        "type": module.question_type,
        "notes": note_payloads,
        "visualHints": _build_visual_hints(picked),
        "choices": [
            {"id": "first_higher", "label": "First note is higher"},
            {"id": "second_higher", "label": "Second note is higher"},
        ],
        "correctAnswer": correct_answer,
        "promptText": "Listen to two notes. Which one is higher?",
    }


def _generate_sort(
    module,
    question_number,
    notes_pool,
    do_frequency,
    temperament,
    instrument,
    note_count: int,
) -> dict:
    interval_step = _interval_constraint_for_level(module.level)
    picked = _pick_sort_notes(notes_pool, note_count, interval_step)
    note_payloads = _build_note_payloads(picked, do_frequency, temperament, instrument)
    sorted_indices = sorted(range(note_count), key=lambda idx: picked[idx].semitone)

    return {
        "id": f"{module.module_id}-Q{question_number}",
        "type": module.question_type,
        "notes": note_payloads,
        "visualHints": _build_visual_hints(picked),
        "choices": {
            "positions": [str(i) for i in range(1, note_count + 1)],
            "format": "index_sequence",
        },
        "correctAnswer": "-".join(str(idx + 1) for idx in sorted_indices),
        "promptText": f"Listen to {note_count} notes. Sort from low to high.",
    }


def _generate_interval(module, question_number, notes_pool, do_frequency, temperament, instrument) -> dict:
    picked = random.sample(notes_pool, 2)
    note_payloads = _build_note_payloads(picked, do_frequency, temperament, instrument)
    distance = abs(picked[0].degree - picked[1].degree)

    possible_distances = sorted(
        {
            abs(a.degree - b.degree)
            for a, b in combinations(notes_pool, 2)
            if abs(a.degree - b.degree) > 0
        }
    )

    return {
        "id": f"{module.module_id}-Q{question_number}",
        "type": module.question_type,
        "notes": note_payloads,
        "visualHints": _build_visual_hints(picked),
        "choices": [str(item) for item in possible_distances],
        "correctAnswer": str(distance),
        "promptText": "How many scale steps apart are these two notes?",
    }


def _generate_single_note(module, question_number, notes_pool, do_frequency, temperament, instrument) -> dict:
    picked = random.choice(notes_pool)
    note_payload = _build_note_payloads([picked], do_frequency, temperament, instrument)[0]

    correct_answer = {
        "degree": str(picked.degree),
        "accidental": picked.accidental,
    }

    accepted = []
    if picked.enharmonic_degree is not None and picked.enharmonic_accidental is not None:
        accepted.append(
            {
                "degree": str(picked.enharmonic_degree),
                "accidental": picked.enharmonic_accidental,
            }
        )
    if accepted:
        correct_answer["accepted"] = accepted

    return {
        "id": f"{module.module_id}-Q{question_number}",
        "type": module.question_type,
        "notes": [note_payload],
        "visualHints": [],
        "choices": {
            "degrees": [str(item) for item in range(1, 8)],
            "accidentals": ["flat", "natural", "sharp"] if module.level == "L4" else ["natural"],
            "requiresAccidental": module.level == "L4",
        },
        "correctAnswer": correct_answer,
        "promptText": "Listen to one note. Choose the movable-do number.",
    }


def _build_visual_hints(notes: list) -> list[dict]:
    semitones = [note.semitone for note in notes]
    min_semitone = min(semitones)
    max_semitone = max(semitones)

    if max_semitone == min_semitone:
        return [{"index": idx + 1, "height": 50.0} for idx in range(len(notes))]

    hints = []
    for idx, note in enumerate(notes):
        normalized = (note.semitone - min_semitone) / (max_semitone - min_semitone)
        hints.append({"index": idx + 1, "height": round(10 + normalized * 80, 2)})
    return hints


def _interval_constraint_for_level(level: str) -> int | None:
    """Return semitone constraint for advanced proximity levels."""

    if level == "L5":
        return 2  # one whole tone
    if level == "L6":
        return 1  # one semitone
    return None


def _pick_compare_notes(notes_pool: list, interval_step: int | None):
    if interval_step is None:
        return random.sample(notes_pool, 2)

    valid_pairs = [
        [left, right]
        for left, right in combinations(notes_pool, 2)
        if abs(left.semitone - right.semitone) == interval_step
    ]
    if not valid_pairs:
        return random.sample(notes_pool, 2)

    picked = random.choice(valid_pairs)
    random.shuffle(picked)
    return picked


def _pick_sort_notes(notes_pool: list, note_count: int, interval_step: int | None):
    if interval_step is None:
        return random.sample(notes_pool, note_count)

    note_by_semitone = {note.semitone: note for note in notes_pool}
    semitone_values = sorted(note_by_semitone.keys())
    valid_sequences = []

    for start in semitone_values:
        sequence = [start + interval_step * idx for idx in range(note_count)]
        if all(semitone in note_by_semitone for semitone in sequence):
            valid_sequences.append(sequence)

    if not valid_sequences:
        return random.sample(notes_pool, note_count)

    selected_sequence = random.choice(valid_sequences)
    picked = [note_by_semitone[semitone] for semitone in selected_sequence]
    random.shuffle(picked)
    return picked


def validate_temperament(temperament: str) -> None:
    if temperament != EQUAL_TEMPERAMENT:
        raise ValueError(f"Unknown temperament '{temperament}'")


def _build_note_payloads(
    notes_pool: list,
    do_frequency: float,
    temperament: str,
    instrument: str,
) -> list[dict]:
    payloads: list[dict] = []
    for note in notes_pool:
        payload = build_note_payload(note, do_frequency, temperament)
        frequency = note_frequency(note.semitone, do_frequency, temperament)
        mapping = map_target_frequency(frequency, instrument=instrument)
        payload["sampleId"] = mapping.sample_id
        payload["midi"] = mapping.midi
        payloads.append(payload)
    return payloads
