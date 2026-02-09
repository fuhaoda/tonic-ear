import json
from pathlib import Path

from app.domain.audio_samples import (
    MAX_CENTS_ERROR,
    build_sample_specs,
    get_unique_equal_temperament_targets,
    get_sample_by_id,
    map_target_frequency,
    worst_mapping_error,
)
from app.domain.music import EQUAL_TEMPERAMENT, GENDER_OPTIONS, KEY_OPTIONS, calculate_do_frequency, note_frequency
from app.domain.generator import generate_session, get_meta

REPO_ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = REPO_ROOT / "web" / "assets" / "audio" / "piano"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"


def test_equal_temperament_unique_count_matches_expected():
    sample_specs = build_sample_specs()
    equal_targets = get_unique_equal_temperament_targets()

    assert len(sample_specs) == 46
    assert sample_specs[0].midi == 38
    assert sample_specs[-1].midi == 83
    assert len(equal_targets) == 35


def test_worst_mapping_error_with_88_samples_under_10_cents():
    equal_targets = get_unique_equal_temperament_targets()
    worst_cents, _ = worst_mapping_error(equal_targets)
    assert worst_cents <= MAX_CENTS_ERROR


def test_all_equal_gender_key_targets_map_within_budget():
    combination_count = 0
    for gender in [option["id"] for option in GENDER_OPTIONS]:
        for key in [option["id"] for option in KEY_OPTIONS]:
            do_frequency = calculate_do_frequency(gender=gender, key_id=key)
            for semitone in range(12):
                frequency = note_frequency(semitone, do_frequency, EQUAL_TEMPERAMENT)
                mapping = map_target_frequency(frequency)
                assert abs(mapping.cents_error) <= MAX_CENTS_ERROR
                combination_count += 1

    assert combination_count == 288


def test_manifest_exists_and_declares_valid_bounds():
    assert MANIFEST_PATH.exists()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["sampleCount"] == 46
    assert manifest["targetFrequencyCount"] == 35
    assert manifest["maxMappingErrorCents"] <= MAX_CENTS_ERROR
    assert manifest["sampleHzRange"] == [70.0, 1000.0]
    assert manifest["durationMs"] == 1000

    audio_files = list(AUDIO_DIR.glob("*.m4a"))
    assert len(audio_files) == 46
    total_bytes = sum(path.stat().st_size for path in audio_files)
    total_megabytes = total_bytes / (1024 * 1024)
    assert total_megabytes < 10.0


def test_generated_sessions_use_manifest_sample_ids():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest_ids = {sample["id"] for sample in manifest["samples"]}

    modules = [module["id"] for module in get_meta()["modules"]]

    for module_id in modules:
        for gender, key in [
            ("male", "C"),
            ("female", "B"),
        ]:
            session = generate_session(
                module_id=module_id,
                gender=gender,
                key=key,
                temperament="equal_temperament",
            )
            for question in session["questions"]:
                for note in question["notes"]:
                    assert note["sampleId"] in manifest_ids
                    sample_spec = get_sample_by_id(note["sampleId"])
                    assert sample_spec.midi == note["midi"]
