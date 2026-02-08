"""Sample-note definitions and frequency mapping helpers for piano audio playback."""

from __future__ import annotations

from dataclasses import dataclass
from math import log2

from app.domain.music import (
    EQUAL_TEMPERAMENT,
    GENDER_OPTIONS,
    JUST_INTONATION,
    KEY_OPTIONS,
    calculate_do_frequency,
    note_frequency,
)

BASE_SAMPLE_HZ = 130.8  # C3
SAMPLE_COUNT = 35
MAX_CENTS_ERROR = 20.0

NOTE_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class SampleSpec:
    """Definition for one downloadable piano sample."""

    id: str
    semitone_offset: int
    note: str
    hz: float
    source_filename: str
    output_filename: str


@dataclass(frozen=True)
class FrequencyMapping:
    """Mapping from target frequency to nearest sample with playback rate."""

    target_hz: float
    sample_id: str
    sample_hz: float
    playback_rate: float
    cents_error: float


def build_sample_specs() -> list[SampleSpec]:
    """Return all 35 sample slots needed to cover the app pitch range."""

    specs: list[SampleSpec] = []
    for semitone in range(SAMPLE_COUNT):
        note_name = NOTE_NAMES_FLAT[semitone % 12]
        octave = 3 + semitone // 12
        note = f"{note_name}{octave}"
        specs.append(
            SampleSpec(
                id=f"s{semitone:02d}",
                semitone_offset=semitone,
                note=note,
                hz=BASE_SAMPLE_HZ * (2 ** (semitone / 12)),
                source_filename=f"Piano.mf.{note}.aiff",
                output_filename=f"s{semitone:02d}.m4a",
            )
        )
    return specs


def _dedupe_sorted_floats(values: list[float], tolerance: float = 1e-6) -> list[float]:
    unique: list[float] = []
    for value in sorted(values):
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


def get_unique_equal_temperament_targets() -> list[float]:
    """Return unique equal-temperament frequencies currently reachable in the app."""

    frequencies: list[float] = []
    for gender in [item["id"] for item in GENDER_OPTIONS]:
        for key in [item["id"] for item in KEY_OPTIONS]:
            do_frequency = calculate_do_frequency(gender=gender, key_id=key)
            for semitone in range(12):
                frequencies.append(note_frequency(semitone, do_frequency, EQUAL_TEMPERAMENT))
    return _dedupe_sorted_floats(frequencies)


def get_unique_target_frequencies() -> list[float]:
    """Return unique frequencies across equal temperament and just intonation."""

    frequencies: list[float] = []
    for temperament in [EQUAL_TEMPERAMENT, JUST_INTONATION]:
        for gender in [item["id"] for item in GENDER_OPTIONS]:
            for key in [item["id"] for item in KEY_OPTIONS]:
                do_frequency = calculate_do_frequency(gender=gender, key_id=key)
                for semitone in range(12):
                    frequencies.append(note_frequency(semitone, do_frequency, temperament))
    return _dedupe_sorted_floats(frequencies)


def map_target_frequency(target_hz: float, sample_specs: list[SampleSpec]) -> FrequencyMapping:
    """Map a target frequency to the nearest sample and playback rate."""

    if not sample_specs:
        raise ValueError("sample_specs must not be empty")

    nearest = min(sample_specs, key=lambda item: abs(1200 * log2(target_hz / item.hz)))
    cents_error = 1200 * log2(target_hz / nearest.hz)
    playback_rate = target_hz / nearest.hz

    return FrequencyMapping(
        target_hz=target_hz,
        sample_id=nearest.id,
        sample_hz=nearest.hz,
        playback_rate=playback_rate,
        cents_error=cents_error,
    )


def worst_mapping_error(
    targets: list[float] | None = None,
    sample_specs: list[SampleSpec] | None = None,
) -> tuple[float, FrequencyMapping]:
    """Return the worst absolute cents error across all target frequencies."""

    checked_targets = targets if targets is not None else get_unique_target_frequencies()
    checked_specs = sample_specs if sample_specs is not None else build_sample_specs()

    if not checked_targets:
        raise ValueError("targets must not be empty")

    mappings = [map_target_frequency(target, checked_specs) for target in checked_targets]
    worst = max(mappings, key=lambda mapping: abs(mapping.cents_error))
    return abs(worst.cents_error), worst
