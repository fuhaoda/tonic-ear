import random

from app.domain.generator import generate_session, get_meta
from app.domain.music import get_note_pool


def test_meta_contains_expected_module_count_and_structure():
    meta = get_meta()
    assert "modules" in meta
    assert len(meta["modules"]) == 25
    assert meta["defaults"]["showVisualHints"] is False

    module_ids = {module["id"] for module in meta["modules"]}
    assert "MI-L4" not in module_ids
    assert "M2-L1" in module_ids
    assert "M2-L6" in module_ids
    assert "M3-L5" in module_ids
    assert "M4-L6" in module_ids


def test_generate_session_returns_20_questions():
    random.seed(7)
    session = generate_session(
        module_id="M2-L2",
        gender="male",
        key="C",
        temperament="equal_temperament",
    )

    assert len(session["questions"]) == 20
    assert session["settings"]["moduleId"] == "M2-L2"


def test_compare_two_has_distinct_notes_per_question():
    random.seed(11)
    session = generate_session(
        module_id="M2-L4",
        gender="female",
        key="F#/Gb",
        temperament="just_intonation",
    )

    for question in session["questions"]:
        semitones = {note["semitone"] for note in question["notes"]}
        assert len(semitones) == 2
        assert {choice["id"] for choice in question["choices"]} == {"first_higher", "second_higher"}


def test_m4_l1_uses_l2_pool_for_valid_four_note_questions():
    random.seed(17)
    session = generate_session(
        module_id="M4-L1",
        gender="male",
        key="D",
        temperament="equal_temperament",
    )

    assert session["settings"]["effectiveNotePoolLevel"] == "L2"
    allowed_semitones = {note.semitone for note in get_note_pool("L2")}

    for question in session["questions"]:
        semitones = [note["semitone"] for note in question["notes"]]
        assert len(semitones) == 4
        assert len(set(semitones)) == 4
        assert set(semitones).issubset(allowed_semitones)


def test_single_note_l4_requires_accidental_selector():
    random.seed(19)
    session = generate_session(
        module_id="MS-L4",
        gender="female",
        key="A",
        temperament="just_intonation",
    )

    for question in session["questions"]:
        assert question["choices"]["requiresAccidental"] is True
        assert question["choices"]["accidentals"] == ["flat", "natural", "sharp"]


def test_compare_two_l5_uses_whole_tone_distance():
    random.seed(23)
    session = generate_session(
        module_id="M2-L5",
        gender="male",
        key="C",
        temperament="equal_temperament",
    )

    for question in session["questions"]:
        semitones = sorted(note["semitone"] for note in question["notes"])
        assert semitones[1] - semitones[0] == 2


def test_compare_two_l6_uses_semitone_distance():
    random.seed(29)
    session = generate_session(
        module_id="M2-L6",
        gender="male",
        key="C",
        temperament="equal_temperament",
    )

    for question in session["questions"]:
        semitones = sorted(note["semitone"] for note in question["notes"])
        assert semitones[1] - semitones[0] == 1


def test_sort_three_l5_has_whole_tone_steps_when_sorted():
    random.seed(31)
    session = generate_session(
        module_id="M3-L5",
        gender="female",
        key="E",
        temperament="just_intonation",
    )

    for question in session["questions"]:
        semitones = sorted(note["semitone"] for note in question["notes"])
        diffs = [right - left for left, right in zip(semitones, semitones[1:])]
        assert diffs == [2, 2]


def test_sort_four_l6_has_semitone_steps_when_sorted():
    random.seed(37)
    session = generate_session(
        module_id="M4-L6",
        gender="female",
        key="A",
        temperament="equal_temperament",
    )

    for question in session["questions"]:
        semitones = sorted(note["semitone"] for note in question["notes"])
        diffs = [right - left for left, right in zip(semitones, semitones[1:])]
        assert diffs == [1, 1, 1]
