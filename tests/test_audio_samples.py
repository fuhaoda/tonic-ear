import json
from pathlib import Path

from app.domain.audio_samples import (
    MAX_CENTS_ERROR,
    build_sample_specs,
    get_unique_equal_temperament_targets,
    get_unique_target_frequencies,
    map_target_frequency,
    worst_mapping_error,
)
from app.domain.music import (
    EQUAL_TEMPERAMENT,
    GENDER_OPTIONS,
    JUST_INTONATION,
    KEY_OPTIONS,
    calculate_do_frequency,
    note_frequency,
)
from app.domain.generator import generate_session, get_meta

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = REPO_ROOT / "web" / "assets" / "audio" / "piano"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"


def test_equal_temperament_unique_count_matches_sample_count():
    sample_specs = build_sample_specs()
    equal_targets = get_unique_equal_temperament_targets()

    assert len(sample_specs) == 35
    assert len(equal_targets) == 35


def test_unique_target_count_and_worst_mapping_error():
    sample_specs = build_sample_specs()
    all_targets = get_unique_target_frequencies()
    worst_cents, _ = worst_mapping_error(targets=all_targets, sample_specs=sample_specs)

    assert len(all_targets) == 299
    assert worst_cents <= MAX_CENTS_ERROR


def test_all_576_gender_key_temperament_targets_map_within_budget():
    sample_specs = build_sample_specs()

    combination_count = 0
    for temperament in [EQUAL_TEMPERAMENT, JUST_INTONATION]:
        for gender in [option["id"] for option in GENDER_OPTIONS]:
            for key in [option["id"] for option in KEY_OPTIONS]:
                do_frequency = calculate_do_frequency(gender=gender, key_id=key)
                for semitone in range(12):
                    frequency = note_frequency(semitone, do_frequency, temperament)
                    mapping = map_target_frequency(frequency, sample_specs)
                    assert abs(mapping.cents_error) <= MAX_CENTS_ERROR
                    combination_count += 1

    assert combination_count == 576


def test_manifest_exists_and_declares_valid_bounds():
    assert MANIFEST_PATH.exists()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["sampleCount"] == 35
    assert manifest["targetFrequencyCount"] == 299
    assert manifest["maxMappingErrorCents"] <= MAX_CENTS_ERROR

    audio_files = list(AUDIO_DIR.glob("*.m4a"))
    assert len(audio_files) == 35
    total_bytes = sum(path.stat().st_size for path in audio_files)
    total_megabytes = total_bytes / (1024 * 1024)
    assert total_megabytes < 10.0


def test_generated_sessions_use_frequencies_with_valid_sample_mapping():
    sample_specs = build_sample_specs()
    modules = [module["id"] for module in get_meta()["modules"]]

    for module_id in modules:
        for gender, key, temperament in [
            ("male", "C", EQUAL_TEMPERAMENT),
            ("female", "B", JUST_INTONATION),
        ]:
            session = generate_session(
                module_id=module_id,
                gender=gender,
                key=key,
                temperament=temperament,
            )
            for question in session["questions"]:
                for note in question["notes"]:
                    mapping = map_target_frequency(note["frequency"], sample_specs)
                    assert abs(mapping.cents_error) <= MAX_CENTS_ERROR
