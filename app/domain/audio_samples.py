"""Piano sample definitions and equal-temperament sample mapping helpers."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import log2

from app.domain.music import EQUAL_TEMPERAMENT, GENDER_OPTIONS, KEY_OPTIONS, calculate_do_frequency, note_frequency

SAMPLE_MIN_HZ = 70.0
SAMPLE_MAX_HZ = 1000.0
MAX_CENTS_ERROR = 10.0

NOTE_NAMES_FLAT = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")


@dataclass(frozen=True)
class SampleSpec:
    """Definition for one downloadable piano sample."""

    id: str
    midi: int
    note: str
    hz: float
    source_filename: str
    output_filename: str


@dataclass(frozen=True)
class FrequencyMapping:
    """Mapping from target frequency to nearest raw sample."""

    target_hz: float
    sample_id: str
    midi: int
    sample_hz: float
    cents_error: float


def midi_to_hz(midi: int) -> float:
    """Convert MIDI note number to frequency in Hz (A4=440)."""

    return 440.0 * (2 ** ((midi - 69) / 12))


def midi_to_note_name(midi: int) -> str:
    """Return note label in flat naming, for example Db4."""

    note_name = NOTE_NAMES_FLAT[midi % 12]
    octave = (midi // 12) - 1
    return f"{note_name}{octave}"


def _available_midi_values() -> tuple[int, ...]:
    values = tuple(midi for midi in range(21, 109) if SAMPLE_MIN_HZ <= midi_to_hz(midi) <= SAMPLE_MAX_HZ)
    if not values:
        raise ValueError("No MIDI notes available in configured sample range")
    return values


@lru_cache(maxsize=1)
def _sample_spec_tuple() -> tuple[SampleSpec, ...]:
    specs: list[SampleSpec] = []
    for midi in _available_midi_values():
        note = midi_to_note_name(midi)
        sample_id = f"m{midi:03d}"
        specs.append(
            SampleSpec(
                id=sample_id,
                midi=midi,
                note=note,
                hz=midi_to_hz(midi),
                source_filename=f"Piano.ff.{note}.aiff",
                output_filename=f"{sample_id}.m4a",
            )
        )
    return tuple(specs)


def build_sample_specs() -> list[SampleSpec]:
    """Return all 88 raw piano sample definitions (A0..C8)."""

    return list(_sample_spec_tuple())


@lru_cache(maxsize=1)
def _sample_by_midi() -> dict[int, SampleSpec]:
    return {spec.midi: spec for spec in _sample_spec_tuple()}


@lru_cache(maxsize=1)
def _sample_by_id() -> dict[str, SampleSpec]:
    return {spec.id: spec for spec in _sample_spec_tuple()}


def get_sample_for_midi(midi: int) -> SampleSpec:
    """Return nearest available sample spec for a MIDI note."""

    available = _available_midi_values()
    nearest = min(available, key=lambda value: abs(value - int(midi)))
    return _sample_by_midi()[nearest]


def get_sample_by_id(sample_id: str) -> SampleSpec:
    """Resolve one sample id to its spec."""

    sample = _sample_by_id().get(sample_id)
    if sample is None:
        raise ValueError(f"Unknown sample id '{sample_id}'")
    return sample


def _dedupe_sorted_floats(values: list[float], tolerance: float = 1e-6) -> list[float]:
    unique: list[float] = []
    for value in sorted(values):
        if not unique or abs(value - unique[-1]) > tolerance:
            unique.append(value)
    return unique


def get_unique_equal_temperament_targets() -> list[float]:
    """Return unique equal-temperament frequencies reachable in the app."""

    frequencies: list[float] = []
    for gender in [item["id"] for item in GENDER_OPTIONS]:
        for key in [item["id"] for item in KEY_OPTIONS]:
            do_frequency = calculate_do_frequency(gender=gender, key_id=key)
            for semitone in range(12):
                frequencies.append(note_frequency(semitone, do_frequency, EQUAL_TEMPERAMENT))
    return _dedupe_sorted_floats(frequencies)


def map_target_frequency(target_hz: float) -> FrequencyMapping:
    """Map a target frequency to nearest raw sample (no playback-rate correction)."""

    if target_hz <= 0:
        raise ValueError(f"target_hz must be positive, got {target_hz}")

    samples = _sample_spec_tuple()
    sample = min(samples, key=lambda item: abs(1200 * log2(target_hz / item.hz)))
    cents_error = 1200 * log2(target_hz / sample.hz)

    return FrequencyMapping(
        target_hz=target_hz,
        sample_id=sample.id,
        midi=sample.midi,
        sample_hz=sample.hz,
        cents_error=cents_error,
    )


def worst_mapping_error(targets: list[float] | None = None) -> tuple[float, FrequencyMapping]:
    """Return worst absolute cents error for provided targets."""

    checked_targets = targets if targets is not None else get_unique_equal_temperament_targets()
    if not checked_targets:
        raise ValueError("targets must not be empty")

    mappings = [map_target_frequency(target) for target in checked_targets]
    worst = max(mappings, key=lambda mapping: abs(mapping.cents_error))
    return abs(worst.cents_error), worst
