import json
from pathlib import Path

from app.domain.audio_samples import (
    MAX_CENTS_ERROR,
    build_sample_specs,
    get_sample_by_id,
    get_unique_equal_temperament_targets,
    map_target_frequency,
    worst_mapping_error,
)
from app.domain.generator import generate_session, get_meta
from app.domain.music import EQUAL_TEMPERAMENT, GENDER_OPTIONS, KEY_OPTIONS, calculate_do_frequency, note_frequency

REPO_ROOT = Path(__file__).resolve().parents[1]
PIANO_DIR = REPO_ROOT / "docs" / "assets" / "audio" / "piano"
GUITAR_DIR = REPO_ROOT / "docs" / "assets" / "audio" / "guitar"


def test_equal_temperament_unique_count_matches_expected():
    equal_targets = get_unique_equal_temperament_targets()
    piano_specs = build_sample_specs("piano")
    guitar_specs = build_sample_specs("guitar")

    assert len(equal_targets) == 35
    assert len(piano_specs) == 46
    assert len(guitar_specs) == 46
    assert piano_specs[0].midi == guitar_specs[0].midi == 38
    assert piano_specs[-1].midi == guitar_specs[-1].midi == 83


def test_worst_mapping_error_with_sample_pack_stays_under_budget():
    equal_targets = get_unique_equal_temperament_targets()

    piano_worst_cents, _ = worst_mapping_error(equal_targets, instrument="piano")
    guitar_worst_cents, _ = worst_mapping_error(equal_targets, instrument="guitar")

    assert piano_worst_cents <= MAX_CENTS_ERROR
    assert guitar_worst_cents <= MAX_CENTS_ERROR


def test_all_equal_gender_key_targets_map_within_budget_for_each_instrument():
    combination_count = 0
    for gender in [option["id"] for option in GENDER_OPTIONS]:
        for key in [option["id"] for option in KEY_OPTIONS]:
            do_frequency = calculate_do_frequency(gender=gender, key_id=key)
            for semitone in range(12):
                frequency = note_frequency(semitone, do_frequency, EQUAL_TEMPERAMENT)
                piano_mapping = map_target_frequency(frequency, instrument="piano")
                guitar_mapping = map_target_frequency(frequency, instrument="guitar")
                assert abs(piano_mapping.cents_error) <= MAX_CENTS_ERROR
                assert abs(guitar_mapping.cents_error) <= MAX_CENTS_ERROR
                combination_count += 1

    assert combination_count == 288


def _assert_manifest_for_instrument(audio_dir: Path, instrument: str) -> None:
    manifest_path = audio_dir / "manifest.json"
    assert manifest_path.exists()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["sampleCount"] == 46
    assert manifest["targetFrequencyCount"] == 35
    assert manifest["maxMappingErrorCents"] <= MAX_CENTS_ERROR
    assert manifest["sampleHzRange"] == [70.0, 1000.0]
    expected_duration_ms = 1000 if instrument == "piano" else 1500
    assert manifest["durationMs"] == expected_duration_ms
    assert manifest["instrument"] == instrument

    audio_files = sorted(audio_dir.glob("*.m4a"))
    assert len(audio_files) == 46
    total_bytes = sum(path.stat().st_size for path in audio_files)
    total_megabytes = total_bytes / (1024 * 1024)
    assert total_megabytes < 20.0


def test_manifests_exist_and_declare_valid_bounds_for_both_instruments():
    _assert_manifest_for_instrument(PIANO_DIR, "piano")
    _assert_manifest_for_instrument(GUITAR_DIR, "guitar")


def test_generated_sessions_use_matching_manifest_sample_ids_for_each_instrument():
    piano_manifest = json.loads((PIANO_DIR / "manifest.json").read_text(encoding="utf-8"))
    guitar_manifest = json.loads((GUITAR_DIR / "manifest.json").read_text(encoding="utf-8"))
    piano_ids = {sample["id"] for sample in piano_manifest["samples"]}
    guitar_ids = {sample["id"] for sample in guitar_manifest["samples"]}

    modules = [module["id"] for module in get_meta()["modules"]]

    for module_id in modules:
        for instrument in ["piano", "guitar"]:
            session = generate_session(
                module_id=module_id,
                gender="male",
                key="C",
                temperament="equal_temperament",
                instrument=instrument,
            )
            for question in session["questions"]:
                for note in question["notes"]:
                    if instrument == "piano":
                        assert note["sampleId"] in piano_ids
                    else:
                        assert note["sampleId"] in guitar_ids
                    sample_spec = get_sample_by_id(note["sampleId"], instrument=instrument)
                    assert sample_spec.midi == note["midi"]
