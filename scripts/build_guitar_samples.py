#!/usr/bin/env python3
"""Download and rebuild aligned guitar samples that match piano sample ordering."""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import json
from math import exp, log, log2, log10, sqrt
from pathlib import Path
import re
import shutil
from statistics import median
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote
from urllib.request import urlretrieve

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domain.audio_samples import (  # noqa: E402
    MAX_CENTS_ERROR,
    SAMPLE_MAX_HZ,
    SAMPLE_MIN_HZ,
    build_sample_specs,
    get_unique_equal_temperament_targets,
    worst_mapping_error,
)

SOURCE_BASE_URL = "https://theremin.music.uiowa.edu/sound%20files/MIS/Piano_Other/guitar"
RANGE_FILENAMES = [
    "Guitar.ff.sulE.E2B2.mono.aif",
    "Guitar.ff.sulE.C3B3.mono.aif",
    "Guitar.ff.sulA.A2B2.mono.aif",
    "Guitar.ff.sulA.C3B3.mono.aif",
    "Guitar.ff.sulA.C4E4.mono.aif",
    "Guitar.ff.sulD.D3B3.mono.aif",
    "Guitar.ff.sulD.C4Ab4.mono.aif",
    "Guitar.ff.sulG.G3B3.mono.aif",
    "Guitar.ff.sulG.C4B4.mono.aif",
    "Guitar.ff.sulG.C5Db5.mono.aif",
    "Guitar.ff.sulB.B3.mono.aif",
    "Guitar.ff.sulB.C4B4.mono.aif",
    "Guitar.ff.sulB.C5Gb5.mono.aif",
    "Guitar.ff.sul_E.E4B4.mono.aif",
    "Guitar.ff.sul_E.C5Bb5.mono.aif",
]

NATIVE_MIN_MIDI = 40
NATIVE_MAX_MIDI = 82
FILL_EDGE_MAP = {
    38: 40,
    39: 40,
    83: 82,
}

AUBIO_ONSET_METHOD = "hfc"
AUBIO_ONSET_FRAME = 1024
AUBIO_ONSET_HOP = 256
AUBIO_PITCH_METHOD = "yinfft"
AUBIO_PITCH_FRAME = 4096
AUBIO_PITCH_HOP = 512
PITCH_WINDOW_START_SEC = 0.02
PITCH_WINDOW_END_SEC = 0.45
ONSET_RMS_WINDOW_SEC = 0.10
MIDI_TOLERANCE_SEMITONES = 0.75
START_PREROLL_SEC = 0.004

TARGET_PEAK_LINEAR = 0.92
GAIN_CLAMP_MIN = 0.35
GAIN_CLAMP_MAX = 2.80
ATTACK_ANALYSIS_SEC = 0.35
MID_WINDOW_START_SEC = 0.35
MID_WINDOW_DURATION_SEC = 0.55
TAIL_ANALYSIS_SEC = 0.60
SUSTAIN_RATIO_FLOOR = 0.24
SUSTAIN_DONOR_RATIO = 0.30
SUSTAIN_REPAIR_MAX_SEMITONES = 8
SUSTAIN_REPAIR_MAX_PASSES = 4
GAIN_SMOOTHING_LAMBDA = 0.08
GAIN_SMOOTHING_PASSES = 1

MAX_ADJACENT_GAIN_STEP_DB = 3.5
MAX_ATTACK_RMS_SPREAD_DB = 3.2
MAX_FULL_RMS_SPREAD_DB = 2.0
MAX_MID_RMS_SPREAD_DB = 7.0
MAX_SUSTAIN_SPREAD_DB = 10.0
QUALITY_SPREAD_LOW_PERCENTILE = 0.10
QUALITY_SPREAD_HIGH_PERCENTILE = 0.90
SUSTAIN_SPREAD_LOW_PERCENTILE = 0.15
SUSTAIN_SPREAD_HIGH_PERCENTILE = 0.85

NOTE_SEMITONES = {
    "C": 0,
    "Db": 1,
    "D": 2,
    "Eb": 3,
    "E": 4,
    "F": 5,
    "Gb": 6,
    "G": 7,
    "Ab": 8,
    "A": 9,
    "Bb": 10,
    "B": 11,
}


@dataclass(frozen=True)
class OnsetCandidate:
    midi: int
    source_filename: str
    onset_sec: float
    estimated_midi: float
    rms: float


@dataclass(frozen=True)
class NativeSelection:
    midi: int
    source_filename: str
    onset_sec: float
    estimated_midi: float
    rms: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="web/assets/audio/guitar", help="Output directory")
    parser.add_argument("--cache-dir", default=".cache/guitar_mis_ff", help="Source cache directory")
    parser.add_argument("--duration", type=float, default=1.5, help="Output duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Output sample rate")
    parser.add_argument("--bitrate", default="160k", help="AAC bitrate, for example 128k/160k")
    parser.add_argument("--target-mb", type=float, default=10.0, help="Soft package-size target")
    parser.add_argument("--max-total-mb", type=float, default=20.0, help="Hard package-size cap")
    parser.add_argument("--clean", action="store_true", help="Remove output dir before build")
    parser.add_argument(
        "--refresh-sources",
        action="store_true",
        help="Force re-download of source files before processing",
    )
    return parser.parse_args()


def require_tools() -> None:
    required = ["ffmpeg", "aubioonset", "aubiopitch"]
    missing = [tool for tool in required if shutil.which(tool) is None]
    if missing:
        raise SystemExit(f"Missing required tools in PATH: {', '.join(missing)}")


def source_url_for_filename(filename: str) -> str:
    return f"{SOURCE_BASE_URL}/{quote(filename)}"


def note_to_midi(token: str) -> int:
    match = re.fullmatch(r"([A-G](?:b)?)(\d)", token)
    if not match:
        raise ValueError(f"Invalid note token '{token}'")
    note_name, octave_str = match.groups()
    octave = int(octave_str)
    return (octave + 1) * 12 + NOTE_SEMITONES[note_name]


def parse_filename_expected_midis(filename: str) -> list[int]:
    match = re.search(r"\.([A-G][b]?\d(?:[A-G][b]?\d)?)\.mono\.aif$", filename)
    if not match:
        raise ValueError(f"Cannot parse note range from '{filename}'")

    tokens = re.findall(r"[A-G][b]?\d", match.group(1))
    if len(tokens) == 1:
        value = note_to_midi(tokens[0])
        return [value]
    if len(tokens) != 2:
        raise ValueError(f"Cannot parse note range from '{filename}'")

    lo = note_to_midi(tokens[0])
    hi = note_to_midi(tokens[1])
    if lo > hi:
        lo, hi = hi, lo
    return list(range(lo, hi + 1))


def download_sources(cache_dir: Path, refresh_sources: bool) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)

    for filename in RANGE_FILENAMES:
        source_path = cache_dir / filename
        if refresh_sources and source_path.exists():
            source_path.unlink()

        if source_path.exists():
            continue

        source_url = source_url_for_filename(filename)
        print(f"Downloading {source_url}")
        urlretrieve(source_url, source_path)


def decode_mono_float_samples(input_path: Path, sample_rate: int) -> array:
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "f32le",
        "-",
    ]
    proc = subprocess.run(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    samples = array("f")
    samples.frombytes(proc.stdout)
    return samples


def run_aubio_onsets(input_path: Path) -> list[float]:
    cmd = [
        "aubioonset",
        "-i",
        str(input_path),
        "-O",
        AUBIO_ONSET_METHOD,
        "-B",
        str(AUBIO_ONSET_FRAME),
        "-H",
        str(AUBIO_ONSET_HOP),
    ]
    output = subprocess.check_output(cmd, text=True)
    values = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            values.append(float(line))
        except ValueError:
            continue
    return values


def run_aubio_pitch_midi(input_path: Path) -> list[tuple[float, float]]:
    cmd = [
        "aubiopitch",
        "-i",
        str(input_path),
        "-p",
        AUBIO_PITCH_METHOD,
        "-u",
        "Hz",
        "-B",
        str(AUBIO_PITCH_FRAME),
        "-H",
        str(AUBIO_PITCH_HOP),
    ]
    output = subprocess.check_output(cmd, text=True)
    values: list[tuple[float, float]] = []
    for line in output.splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        try:
            timestamp = float(parts[0])
            frequency = float(parts[1])
        except ValueError:
            continue
        if frequency <= 40 or frequency >= 2000:
            continue
        midi = 69 + 12 * log2(frequency / 440.0)
        values.append((timestamp, midi))
    return values


def window_rms(samples: array, sample_rate: int, start_sec: float, duration_sec: float) -> float:
    start = max(0, int(round(start_sec * sample_rate)))
    end = min(len(samples), start + int(round(duration_sec * sample_rate)))
    if end <= start:
        return 0.0

    energy = 0.0
    count = 0
    for index in range(start, end):
        value = samples[index]
        energy += value * value
        count += 1

    if count == 0:
        return 0.0
    return sqrt(energy / count)


def detect_candidates_for_file(
    source_path: Path,
    source_filename: str,
    expected_midis: list[int],
    sample_rate: int,
) -> dict[int, OnsetCandidate]:
    onsets = run_aubio_onsets(source_path)
    pitch_track = run_aubio_pitch_midi(source_path)
    decoded = decode_mono_float_samples(source_path, sample_rate=sample_rate)

    candidates: list[OnsetCandidate] = []
    for onset in onsets:
        midi_points = [
            midi
            for timestamp, midi in pitch_track
            if onset + PITCH_WINDOW_START_SEC <= timestamp <= onset + PITCH_WINDOW_END_SEC
        ]
        if len(midi_points) < 5:
            continue

        estimated = float(median(midi_points))
        nearest_midi = min(expected_midis, key=lambda value: abs(value - estimated))
        if abs(nearest_midi - estimated) > MIDI_TOLERANCE_SEMITONES:
            continue

        rms = window_rms(
            decoded,
            sample_rate=sample_rate,
            start_sec=onset,
            duration_sec=ONSET_RMS_WINDOW_SEC,
        )
        candidates.append(
            OnsetCandidate(
                midi=nearest_midi,
                source_filename=source_filename,
                onset_sec=onset,
                estimated_midi=estimated,
                rms=rms,
            )
        )

    best_by_midi: dict[int, OnsetCandidate] = {}
    for candidate in candidates:
        previous = best_by_midi.get(candidate.midi)
        if previous is None or candidate.rms > previous.rms:
            best_by_midi[candidate.midi] = candidate

    return best_by_midi


def source_group_from_filename(filename: str) -> str:
    parts = filename.split(".")
    if len(parts) >= 3:
        return parts[2]
    return filename


def _candidate_base_cost(candidate: OnsetCandidate) -> float:
    pitch_cost = abs(candidate.estimated_midi - candidate.midi) * 16.0
    loud_pref = -2.5 * log(max(candidate.rms, 1e-9))
    return pitch_cost + loud_pref


def _candidate_transition_cost(previous: OnsetCandidate, current: OnsetCandidate) -> float:
    pitch_step_cost = abs((current.estimated_midi - previous.estimated_midi) - 1.0) * 8.0
    rms_jump = abs(log((current.rms + 1e-9) / (previous.rms + 1e-9))) * 6.0
    source_switch = (
        0.0 if source_group_from_filename(previous.source_filename) == source_group_from_filename(current.source_filename) else 0.45
    )
    return pitch_step_cost + rms_jump + source_switch


def select_smooth_native_candidates(
    candidates_by_midi: dict[int, list[OnsetCandidate]],
    required_midis: list[int],
) -> dict[int, OnsetCandidate]:
    layered: list[tuple[int, list[OnsetCandidate]]] = []
    for midi in required_midis:
        options = sorted(
            candidates_by_midi.get(midi, []),
            key=lambda candidate: abs(candidate.estimated_midi - midi),
        )
        if not options:
            raise SystemExit(f"No candidate found for MIDI {midi}")
        # Keep search breadth bounded to avoid combinatorial blowup.
        layered.append((midi, options[:8]))

    dp: list[list[float]] = []
    backtrack: list[list[int]] = []

    first_midi, first_options = layered[0]
    dp.append([_candidate_base_cost(candidate) for candidate in first_options])
    backtrack.append([-1] * len(first_options))

    _ = first_midi  # silence unused warning when linting with stricter configs
    for layer_index in range(1, len(layered)):
        _, options = layered[layer_index]
        _, prev_options = layered[layer_index - 1]
        prev_scores = dp[layer_index - 1]

        scores: list[float] = []
        pointers: list[int] = []
        for candidate in options:
            base = _candidate_base_cost(candidate)
            best_score = float("inf")
            best_pointer = -1
            for prev_index, prev_candidate in enumerate(prev_options):
                transition = _candidate_transition_cost(prev_candidate, candidate)
                score = prev_scores[prev_index] + base + transition
                if score < best_score:
                    best_score = score
                    best_pointer = prev_index
            scores.append(best_score)
            pointers.append(best_pointer)

        dp.append(scores)
        backtrack.append(pointers)

    final_layer_scores = dp[-1]
    best_last_index = min(range(len(final_layer_scores)), key=lambda index: final_layer_scores[index])

    selected: dict[int, OnsetCandidate] = {}
    pointer = best_last_index
    for layer_index in range(len(layered) - 1, -1, -1):
        midi, options = layered[layer_index]
        selected[midi] = options[pointer]
        pointer = backtrack[layer_index][pointer]
        if pointer < 0 and layer_index > 0:
            raise SystemExit("Internal error while reconstructing native candidate path")

    return selected


def collect_native_selections(cache_dir: Path, sample_rate: int) -> dict[int, NativeSelection]:
    required = list(range(NATIVE_MIN_MIDI, NATIVE_MAX_MIDI + 1))
    candidates_by_midi: dict[int, list[OnsetCandidate]] = {midi: [] for midi in required}

    for filename in RANGE_FILENAMES:
        expected_midis = parse_filename_expected_midis(filename)
        source_path = cache_dir / filename
        file_best = detect_candidates_for_file(
            source_path=source_path,
            source_filename=filename,
            expected_midis=expected_midis,
            sample_rate=sample_rate,
        )

        missing = [midi for midi in expected_midis if midi not in file_best]
        if missing:
            print(f"WARNING: {filename} missing candidate MIDI values: {missing}")

        for midi, candidate in file_best.items():
            candidates_by_midi[midi].append(candidate)

    missing_global = [midi for midi in required if not candidates_by_midi.get(midi)]
    if missing_global:
        raise SystemExit(
            "Failed to detect full native guitar MIDI range "
            f"{NATIVE_MIN_MIDI}-{NATIVE_MAX_MIDI}; missing {missing_global}",
        )

    chosen_candidates = select_smooth_native_candidates(
        candidates_by_midi=candidates_by_midi,
        required_midis=required,
    )

    return {
        midi: NativeSelection(
            midi=midi,
            source_filename=candidate.source_filename,
            onset_sec=candidate.onset_sec,
            estimated_midi=candidate.estimated_midi,
            rms=candidate.rms,
        )
        for midi, candidate in chosen_candidates.items()
    }


def render_fixed_duration_wav(
    input_path: Path,
    output_path: Path,
    start_sec: float,
    duration: float,
    sample_rate: int,
) -> None:
    start_sec = max(0.0, start_sec)
    end_sec = start_sec + duration
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-af",
        (
            f"atrim=start={start_sec:.6f}:end={end_sec:.6f},"
            "asetpts=PTS-STARTPTS,"
            f"apad=pad_dur={duration:.6f},"
            f"atrim=end={duration:.6f}"
        ),
        "-c:a",
        "pcm_f32le",
        str(output_path),
    ]
    subprocess.run(ffmpeg_cmd, check=True)


def pitch_shift_wav_to_midi(
    input_path: Path,
    output_path: Path,
    source_midi: int,
    target_midi: int,
    duration: float,
    sample_rate: int,
) -> None:
    ratio = 2 ** ((target_midi - source_midi) / 12)
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-af",
        (
            f"asetrate={sample_rate * ratio:.8f},"
            f"aresample={sample_rate},"
            f"atrim=end={duration:.6f},"
            f"apad=pad_dur={duration:.6f},"
            f"atrim=end={duration:.6f}"
        ),
        "-c:a",
        "pcm_f32le",
        str(output_path),
    ]
    subprocess.run(ffmpeg_cmd, check=True)


def render_native_temp_wavs(
    cache_dir: Path,
    native: dict[int, NativeSelection],
    temp_dir: Path,
    duration: float,
    sample_rate: int,
) -> dict[int, Path]:
    temp_paths: dict[int, Path] = {}

    for midi in range(NATIVE_MIN_MIDI, NATIVE_MAX_MIDI + 1):
        selection = native[midi]
        source_path = cache_dir / selection.source_filename
        target_path = temp_dir / f"m{midi:03d}.wav"
        start = max(0.0, selection.onset_sec - START_PREROLL_SEC)
        render_fixed_duration_wav(
            input_path=source_path,
            output_path=target_path,
            start_sec=start,
            duration=duration,
            sample_rate=sample_rate,
        )
        temp_paths[midi] = target_path

    return temp_paths


def render_edge_fill_temp_wavs(
    temp_paths: dict[int, Path],
    duration: float,
    sample_rate: int,
) -> None:
    for target_midi, source_midi in FILL_EDGE_MAP.items():
        output_path = temp_paths[target_midi] if target_midi in temp_paths else None
        if output_path is None:
            output_path = temp_paths[source_midi].parent / f"m{target_midi:03d}.wav"
        pitch_shift_wav_to_midi(
            input_path=temp_paths[source_midi],
            output_path=output_path,
            source_midi=source_midi,
            target_midi=target_midi,
            duration=duration,
            sample_rate=sample_rate,
        )
        temp_paths[target_midi] = output_path


def measure_peak_and_window_rms(
    input_path: Path,
    sample_rate: int,
    analysis_duration_sec: float | None = None,
) -> tuple[float, float]:
    samples = decode_mono_float_samples(input_path, sample_rate=sample_rate)
    if not samples:
        return 0.0, 0.0

    peak = max(abs(value) for value in samples)

    if analysis_duration_sec is None:
        end_index = len(samples)
    else:
        end_index = min(len(samples), int(round(analysis_duration_sec * sample_rate)))
    window = samples[:end_index] if end_index > 0 else samples
    if not window:
        return peak, 0.0

    energy = 0.0
    for value in window:
        energy += value * value

    rms = sqrt(energy / len(window))
    return peak, rms


def measure_window_rms_segment(
    input_path: Path,
    sample_rate: int,
    start_sec: float,
    duration_sec: float,
) -> float:
    samples = decode_mono_float_samples(input_path, sample_rate=sample_rate)
    if not samples:
        return 0.0
    return window_rms(samples, sample_rate=sample_rate, start_sec=start_sec, duration_sec=duration_sec)


def collect_temp_rms_maps(
    temp_paths: dict[int, Path],
    sample_rate: int,
    duration: float,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    peak_map: dict[str, float] = {}
    full_rms_map: dict[str, float] = {}
    attack_rms_map: dict[str, float] = {}
    mid_rms_map: dict[str, float] = {}
    tail_rms_map: dict[str, float] = {}

    attack_window_duration = min(ATTACK_ANALYSIS_SEC, duration)
    mid_window_start = min(max(0.0, MID_WINDOW_START_SEC), max(0.0, duration - 0.05))
    mid_window_duration = min(max(0.05, MID_WINDOW_DURATION_SEC), max(0.05, duration - mid_window_start))
    tail_window_start = max(0.0, duration - TAIL_ANALYSIS_SEC)
    tail_window_duration = max(0.05, duration - tail_window_start)
    for spec in build_sample_specs("guitar"):
        peak, full_rms = measure_peak_and_window_rms(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            analysis_duration_sec=duration,
        )
        peak_map[spec.id] = peak
        full_rms_map[spec.id] = full_rms
        attack_rms_map[spec.id] = measure_window_rms_segment(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            start_sec=0.0,
            duration_sec=attack_window_duration,
        )
        mid_rms_map[spec.id] = measure_window_rms_segment(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            start_sec=mid_window_start,
            duration_sec=mid_window_duration,
        )
        tail_rms_map[spec.id] = measure_window_rms_segment(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            start_sec=tail_window_start,
            duration_sec=tail_window_duration,
        )

    return peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map


def repair_low_sustain_temp_wavs(
    temp_paths: dict[int, Path],
    sample_rate: int,
    duration: float,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
]:
    peak_map: dict[str, float] = {}
    full_rms_map: dict[str, float] = {}
    attack_rms_map: dict[str, float] = {}
    mid_rms_map: dict[str, float] = {}
    tail_rms_map: dict[str, float] = {}

    def sustain_ratio(sample_id: str) -> float:
        attack = max(attack_rms_map.get(sample_id, 0.0), 1e-12)
        tail = max(tail_rms_map.get(sample_id, 0.0), 0.0)
        return tail / attack

    for _ in range(SUSTAIN_REPAIR_MAX_PASSES):
        peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map = collect_temp_rms_maps(
            temp_paths=temp_paths,
            sample_rate=sample_rate,
            duration=duration,
        )
        repaired_any = False
        for spec in build_sample_specs("guitar"):
            sid = spec.id
            ratio = sustain_ratio(sid)
            if ratio >= SUSTAIN_RATIO_FLOOR:
                continue

            donor_candidates = []
            for donor in build_sample_specs("guitar"):
                if donor.midi == spec.midi:
                    continue
                donor_ratio = sustain_ratio(donor.id)
                semitone_distance = abs(donor.midi - spec.midi)
                if donor_ratio < max(SUSTAIN_DONOR_RATIO, ratio * 1.35):
                    continue
                if semitone_distance > SUSTAIN_REPAIR_MAX_SEMITONES:
                    continue
                attack_similarity = abs(log(max(attack_rms_map.get(donor.id, 1e-12), 1e-12) / max(attack_rms_map.get(sid, 1e-12), 1e-12)))
                donor_candidates.append((semitone_distance, attack_similarity, -donor_ratio, donor))

            if not donor_candidates:
                for donor in build_sample_specs("guitar"):
                    if donor.midi == spec.midi:
                        continue
                    donor_ratio = sustain_ratio(donor.id)
                    semitone_distance = abs(donor.midi - spec.midi)
                    if donor_ratio <= ratio * 1.20:
                        continue
                    if semitone_distance > SUSTAIN_REPAIR_MAX_SEMITONES:
                        continue
                    attack_similarity = abs(
                        log(
                            max(attack_rms_map.get(donor.id, 1e-12), 1e-12)
                            / max(attack_rms_map.get(sid, 1e-12), 1e-12),
                        ),
                    )
                    donor_candidates.append((semitone_distance, attack_similarity, -donor_ratio, donor))

            if not donor_candidates:
                continue

            donor_candidates.sort()
            donor = donor_candidates[0][3]
            repaired_any = True
            pitch_shift_wav_to_midi(
                input_path=temp_paths[donor.midi],
                output_path=temp_paths[spec.midi],
                source_midi=donor.midi,
                target_midi=spec.midi,
                duration=duration,
                sample_rate=sample_rate,
            )

        if not repaired_any:
            break

    sustain_ratio_map = {
        spec.id: max(tail_rms_map.get(spec.id, 0.0), 0.0) / max(attack_rms_map.get(spec.id, 1e-12), 1e-12)
        for spec in build_sample_specs("guitar")
    }
    return peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map, sustain_ratio_map


def _spread_db(values: list[float]) -> float:
    nonzero = [value for value in values if value > 0]
    if len(nonzero) < 2:
        return 0.0
    return 20.0 * log10(max(nonzero) / min(nonzero))


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if percentile <= 0:
        return sorted_values[0]
    if percentile >= 1:
        return sorted_values[-1]
    position = percentile * (len(sorted_values) - 1)
    lower_index = int(position)
    upper_index = min(len(sorted_values) - 1, lower_index + 1)
    fraction = position - lower_index
    return sorted_values[lower_index] * (1.0 - fraction) + sorted_values[upper_index] * fraction


def _spread_db_percentile(values: list[float], low_percentile: float, high_percentile: float) -> float:
    nonzero = [value for value in values if value > 0]
    if len(nonzero) < 2:
        return 0.0
    lo = _percentile(nonzero, low_percentile)
    hi = _percentile(nonzero, high_percentile)
    if lo <= 0 or hi <= 0:
        return 0.0
    return 20.0 * log10(hi / lo)


def smooth_gain_map_by_neighbors(gain_map: dict[str, float]) -> dict[str, float]:
    ordered_specs = sorted(build_sample_specs("guitar"), key=lambda spec: spec.midi)
    log_gain = {spec.id: log(max(gain_map.get(spec.id, 1.0), 1e-12)) for spec in ordered_specs}

    for _ in range(GAIN_SMOOTHING_PASSES):
        next_log_gain: dict[str, float] = {}
        for index, spec in enumerate(ordered_specs):
            neighbors = []
            if index > 0:
                neighbors.append(log_gain[ordered_specs[index - 1].id])
            if index + 1 < len(ordered_specs):
                neighbors.append(log_gain[ordered_specs[index + 1].id])
            if not neighbors:
                next_log_gain[spec.id] = log_gain[spec.id]
                continue
            neighbor_avg = sum(neighbors) / len(neighbors)
            next_log_gain[spec.id] = (
                (1.0 - GAIN_SMOOTHING_LAMBDA) * log_gain[spec.id]
                + GAIN_SMOOTHING_LAMBDA * neighbor_avg
            )
        log_gain = next_log_gain

    smoothed: dict[str, float] = {}
    for sample_id, value in log_gain.items():
        gain = exp(value)
        smoothed[sample_id] = max(GAIN_CLAMP_MIN, min(GAIN_CLAMP_MAX, gain))
    return smoothed


def compute_gain_map_from_blended_rms(
    peak_map: dict[str, float],
    full_rms_map: dict[str, float],
    attack_rms_map: dict[str, float],
    mid_rms_map: dict[str, float],
    tail_rms_map: dict[str, float],
) -> tuple[dict[str, float], float, float]:
    blended_map: dict[str, float] = {}
    for spec in build_sample_specs("guitar"):
        full_rms = full_rms_map.get(spec.id, 0.0)
        attack_rms = attack_rms_map.get(spec.id, 0.0)
        mid_rms = mid_rms_map.get(spec.id, 0.0)
        # Prioritize whole-window loudness so 1.5s perceived level stays consistent,
        # with a light attack/mid influence to avoid flattening articulation.
        blended_map[spec.id] = (
            max(full_rms, 1e-12) ** 0.85
            * max(attack_rms, 1e-12) ** 0.10
            * max(mid_rms, 1e-12) ** 0.05
        )

    nonzero = [value for value in blended_map.values() if value > 0]
    if not nonzero:
        raise SystemExit("Cannot normalize guitar samples: all RMS values are zero")

    target_rms = median(nonzero)
    gain_map: dict[str, float] = {}
    max_predicted_peak = 0.0
    for spec in build_sample_specs("guitar"):
        blended = blended_map.get(spec.id, 0.0)
        if blended <= 0:
            gain = 1.0
        else:
            gain = target_rms / blended
        gain = max(GAIN_CLAMP_MIN, min(GAIN_CLAMP_MAX, gain))
        gain_map[spec.id] = gain

    gain_map = smooth_gain_map_by_neighbors(gain_map)

    ordered_specs = sorted(build_sample_specs("guitar"), key=lambda spec: spec.midi)
    max_step_ratio = pow(10.0, MAX_ADJACENT_GAIN_STEP_DB / 20.0)
    for index, spec in enumerate(ordered_specs):
        if index == 0:
            continue
        prev_spec = ordered_specs[index - 1]
        prev_gain = max(gain_map.get(prev_spec.id, 1.0), 1e-12)
        current_gain = max(gain_map.get(spec.id, 1.0), 1e-12)
        if current_gain > prev_gain * max_step_ratio:
            gain_map[spec.id] = prev_gain * max_step_ratio
        elif current_gain < prev_gain / max_step_ratio:
            gain_map[spec.id] = prev_gain / max_step_ratio

    max_predicted_peak = 0.0
    for spec in build_sample_specs("guitar"):
        predicted_peak = peak_map.get(spec.id, 0.0) * gain_map.get(spec.id, 1.0)
        if predicted_peak > max_predicted_peak:
            max_predicted_peak = predicted_peak

    global_peak_scale = 1.0
    if max_predicted_peak > TARGET_PEAK_LINEAR and max_predicted_peak > 0:
        global_peak_scale = TARGET_PEAK_LINEAR / max_predicted_peak
        for sample_id in list(gain_map):
            gain_map[sample_id] *= global_peak_scale

    return gain_map, target_rms, global_peak_scale


def encode_final_sample(temp_wav_path: Path, output_path: Path, bitrate: str, gain: float) -> None:
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(temp_wav_path),
        "-af",
        f"volume={gain:.8f}",
        "-c:a",
        "aac",
        "-b:a",
        bitrate,
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    subprocess.run(ffmpeg_cmd, check=True)


def collect_output_rms_maps(
    output_dir: Path,
    sample_rate: int,
    duration: float,
) -> tuple[dict[str, float], dict[str, float], dict[str, float], dict[str, float], dict[str, float], dict[str, float]]:
    output_paths = {
        spec.midi: output_dir / spec.output_filename
        for spec in build_sample_specs("guitar")
    }
    peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map = collect_temp_rms_maps(
        temp_paths=output_paths,
        sample_rate=sample_rate,
        duration=duration,
    )
    sustain_ratio_map = {
        spec.id: max(tail_rms_map.get(spec.id, 0.0), 0.0) / max(attack_rms_map.get(spec.id, 1e-12), 1e-12)
        for spec in build_sample_specs("guitar")
    }
    return peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map, sustain_ratio_map


def assert_alignment_quality(
    full_rms_map: dict[str, float],
    attack_rms_map: dict[str, float],
    mid_rms_map: dict[str, float],
    sustain_ratio_map: dict[str, float],
    gain_map: dict[str, float],
) -> None:
    issues: list[str] = []
    full_spread = _spread_db_percentile(
        list(full_rms_map.values()),
        QUALITY_SPREAD_LOW_PERCENTILE,
        QUALITY_SPREAD_HIGH_PERCENTILE,
    )
    attack_spread = _spread_db_percentile(
        list(attack_rms_map.values()),
        QUALITY_SPREAD_LOW_PERCENTILE,
        QUALITY_SPREAD_HIGH_PERCENTILE,
    )
    mid_spread = _spread_db_percentile(
        list(mid_rms_map.values()),
        QUALITY_SPREAD_LOW_PERCENTILE,
        QUALITY_SPREAD_HIGH_PERCENTILE,
    )
    sustain_spread = _spread_db_percentile(
        list(sustain_ratio_map.values()),
        SUSTAIN_SPREAD_LOW_PERCENTILE,
        SUSTAIN_SPREAD_HIGH_PERCENTILE,
    )

    if full_spread > MAX_FULL_RMS_SPREAD_DB:
        issues.append(f"full RMS spread {full_spread:.2f}dB > {MAX_FULL_RMS_SPREAD_DB:.2f}dB")
    if attack_spread > MAX_ATTACK_RMS_SPREAD_DB:
        issues.append(f"attack RMS spread {attack_spread:.2f}dB > {MAX_ATTACK_RMS_SPREAD_DB:.2f}dB")
    if mid_spread > MAX_MID_RMS_SPREAD_DB:
        issues.append(f"mid RMS spread {mid_spread:.2f}dB > {MAX_MID_RMS_SPREAD_DB:.2f}dB")
    if sustain_spread > MAX_SUSTAIN_SPREAD_DB:
        issues.append(f"sustain spread {sustain_spread:.2f}dB > {MAX_SUSTAIN_SPREAD_DB:.2f}dB")

    ordered_specs = sorted(build_sample_specs("guitar"), key=lambda spec: spec.midi)
    max_adjacent_step = 0.0
    for index in range(1, len(ordered_specs)):
        prev_gain = max(gain_map.get(ordered_specs[index - 1].id, 1.0), 1e-12)
        current_gain = max(gain_map.get(ordered_specs[index].id, 1.0), 1e-12)
        step_db = abs(20.0 * log10(current_gain / prev_gain))
        if step_db > max_adjacent_step:
            max_adjacent_step = step_db
    if max_adjacent_step > MAX_ADJACENT_GAIN_STEP_DB + 1e-6:
        issues.append(
            f"adjacent gain step {max_adjacent_step:.2f}dB > {MAX_ADJACENT_GAIN_STEP_DB:.2f}dB",
        )

    print(
        "Quality summary:",
        f"full_spread_p10_p90={full_spread:.2f}dB",
        f"attack_spread_p10_p90={attack_spread:.2f}dB",
        f"mid_spread_p10_p90={mid_spread:.2f}dB",
        f"sustain_spread_p15_p85={sustain_spread:.2f}dB",
        f"max_adjacent_gain_step={max_adjacent_step:.2f}dB",
    )

    if issues:
        raise SystemExit("Guitar alignment quality gate failed: " + "; ".join(issues))


def build_audio_assets(
    output_dir: Path,
    cache_dir: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    refresh_sources: bool,
) -> tuple[
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    dict[str, float],
    float,
    float,
    dict[int, NativeSelection],
]:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_sources(cache_dir, refresh_sources=refresh_sources)

    native = collect_native_selections(cache_dir=cache_dir, sample_rate=sample_rate)

    peak_map: dict[str, float] = {}
    full_rms_map: dict[str, float] = {}
    attack_rms_map: dict[str, float] = {}
    mid_rms_map: dict[str, float] = {}
    tail_rms_map: dict[str, float] = {}
    sustain_ratio_map: dict[str, float] = {}
    gain_map: dict[str, float] = {}
    target_rms = 0.0
    global_peak_scale = 1.0

    with tempfile.TemporaryDirectory(prefix="tonic_ear_guitar_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)

        temp_paths = render_native_temp_wavs(
            cache_dir=cache_dir,
            native=native,
            temp_dir=temp_dir,
            duration=duration,
            sample_rate=sample_rate,
        )
        render_edge_fill_temp_wavs(temp_paths=temp_paths, duration=duration, sample_rate=sample_rate)

        for spec in build_sample_specs("guitar"):
            wav_path = temp_paths.get(spec.midi)
            if wav_path is None or not wav_path.exists():
                raise SystemExit(f"Missing temp wav for MIDI {spec.midi} ({spec.id})")

        peak_map, full_rms_map, attack_rms_map, mid_rms_map, tail_rms_map, sustain_ratio_map = repair_low_sustain_temp_wavs(
            temp_paths=temp_paths,
            sample_rate=sample_rate,
            duration=duration,
        )
        gain_map, target_rms, global_peak_scale = compute_gain_map_from_blended_rms(
            peak_map=peak_map,
            full_rms_map=full_rms_map,
            attack_rms_map=attack_rms_map,
            mid_rms_map=mid_rms_map,
            tail_rms_map=tail_rms_map,
        )

        for spec in build_sample_specs("guitar"):
            output_path = output_dir / spec.output_filename
            encode_final_sample(
                temp_wav_path=temp_paths[spec.midi],
                output_path=output_path,
                bitrate=bitrate,
                gain=gain_map.get(spec.id, 1.0),
            )

    (
        peak_map,
        full_rms_map,
        attack_rms_map,
        mid_rms_map,
        tail_rms_map,
        sustain_ratio_map,
    ) = collect_output_rms_maps(
        output_dir=output_dir,
        sample_rate=sample_rate,
        duration=duration,
    )
    assert_alignment_quality(
        full_rms_map=full_rms_map,
        attack_rms_map=attack_rms_map,
        mid_rms_map=mid_rms_map,
        sustain_ratio_map=sustain_ratio_map,
        gain_map=gain_map,
    )

    return (
        peak_map,
        full_rms_map,
        attack_rms_map,
        mid_rms_map,
        tail_rms_map,
        sustain_ratio_map,
        gain_map,
        target_rms,
        global_peak_scale,
        native,
    )


def write_manifest(
    output_dir: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    peak_map: dict[str, float],
    full_rms_map: dict[str, float],
    attack_rms_map: dict[str, float],
    mid_rms_map: dict[str, float],
    tail_rms_map: dict[str, float],
    sustain_ratio_map: dict[str, float],
    gain_map: dict[str, float],
    target_rms: float,
    global_peak_scale: float,
    native: dict[int, NativeSelection],
) -> dict:
    sample_specs = build_sample_specs("guitar")
    equal_targets = get_unique_equal_temperament_targets()
    max_error_cents, worst = worst_mapping_error(equal_targets, instrument="guitar")

    peak_values = [value for value in peak_map.values() if value > 0]
    full_rms_values = [value for value in full_rms_map.values() if value > 0]
    attack_rms_values = [value for value in attack_rms_map.values() if value > 0]
    mid_rms_values = [value for value in mid_rms_map.values() if value > 0]
    tail_rms_values = [value for value in tail_rms_map.values() if value > 0]
    sustain_values = [value for value in sustain_ratio_map.values() if value > 0]
    gain_values = [value for value in gain_map.values() if value > 0]
    quality = {
        "spreadMethod": {
            "fullRms": f"p{int(QUALITY_SPREAD_LOW_PERCENTILE * 100)}_p{int(QUALITY_SPREAD_HIGH_PERCENTILE * 100)}",
            "attackRms": f"p{int(QUALITY_SPREAD_LOW_PERCENTILE * 100)}_p{int(QUALITY_SPREAD_HIGH_PERCENTILE * 100)}",
            "midRms": f"p{int(QUALITY_SPREAD_LOW_PERCENTILE * 100)}_p{int(QUALITY_SPREAD_HIGH_PERCENTILE * 100)}",
            "sustainRatio": f"p{int(SUSTAIN_SPREAD_LOW_PERCENTILE * 100)}_p{int(SUSTAIN_SPREAD_HIGH_PERCENTILE * 100)}",
        },
        "fullRmsSpreadDb": round(
            _spread_db_percentile(full_rms_values, QUALITY_SPREAD_LOW_PERCENTILE, QUALITY_SPREAD_HIGH_PERCENTILE),
            4,
        ),
        "attackRmsSpreadDb": round(
            _spread_db_percentile(attack_rms_values, QUALITY_SPREAD_LOW_PERCENTILE, QUALITY_SPREAD_HIGH_PERCENTILE),
            4,
        ),
        "midRmsSpreadDb": round(
            _spread_db_percentile(mid_rms_values, QUALITY_SPREAD_LOW_PERCENTILE, QUALITY_SPREAD_HIGH_PERCENTILE),
            4,
        ),
        "sustainSpreadDb": round(
            _spread_db_percentile(sustain_values, SUSTAIN_SPREAD_LOW_PERCENTILE, SUSTAIN_SPREAD_HIGH_PERCENTILE),
            4,
        ),
        "thresholdsDb": {
            "full": MAX_FULL_RMS_SPREAD_DB,
            "attack": MAX_ATTACK_RMS_SPREAD_DB,
            "mid": MAX_MID_RMS_SPREAD_DB,
            "sustain": MAX_SUSTAIN_SPREAD_DB,
            "adjacentGainStep": MAX_ADJACENT_GAIN_STEP_DB,
        },
    }
    selection_metadata = {
        str(midi): {
            "source": selection.source_filename,
            "onsetSec": round(selection.onset_sec, 6),
            "estimatedMidi": round(selection.estimated_midi, 6),
            "rms": round(selection.rms, 8),
        }
        for midi, selection in native.items()
    }

    manifest = {
        "version": 1,
        "instrument": "guitar",
        "buildId": int(time.time()),
        "source": "University of Iowa MIS Guitar (ff mono ranges)",
        "sourceUrl": SOURCE_BASE_URL,
        "sourceFiles": RANGE_FILENAMES,
        "durationMs": int(round(duration * 1000)),
        "sampleRate": sample_rate,
        "codec": "aac",
        "bitrate": bitrate,
        "sampleHzRange": [SAMPLE_MIN_HZ, SAMPLE_MAX_HZ],
        "alignment": {
            "method": "aubio_onset_median_pitch",
            "onsetMethod": AUBIO_ONSET_METHOD,
            "pitchMethod": AUBIO_PITCH_METHOD,
            "pitchWindowMs": [int(round(PITCH_WINDOW_START_SEC * 1000)), int(round(PITCH_WINDOW_END_SEC * 1000))],
            "startPrerollMs": int(round(START_PREROLL_SEC * 1000)),
        },
        "normalization": {
            "method": "full_window_dominant_rms_with_neighbor_smoothing_and_peak_guard",
            "targetBlendedRms": round(target_rms, 8),
            "targetPeakLinear": TARGET_PEAK_LINEAR,
            "globalPeakScale": round(global_peak_scale, 8),
            "peakRange": [round(min(peak_values), 6), round(max(peak_values), 6)] if peak_values else [0.0, 0.0],
            "fullWindowRmsMs": int(round(duration * 1000)),
            "fullWindowRmsRange": [round(min(full_rms_values), 8), round(max(full_rms_values), 8)]
            if full_rms_values
            else [0.0, 0.0],
            "attackWindowRmsMs": int(round(min(ATTACK_ANALYSIS_SEC, duration) * 1000)),
            "attackWindowRmsRange": [round(min(attack_rms_values), 8), round(max(attack_rms_values), 8)]
            if attack_rms_values
            else [0.0, 0.0],
            "midWindowStartMs": int(round(min(MID_WINDOW_START_SEC, duration) * 1000)),
            "midWindowRmsMs": int(round(min(MID_WINDOW_DURATION_SEC, duration) * 1000)),
            "midWindowRmsRange": [round(min(mid_rms_values), 8), round(max(mid_rms_values), 8)]
            if mid_rms_values
            else [0.0, 0.0],
            "tailWindowRmsMs": int(round(min(TAIL_ANALYSIS_SEC, duration) * 1000)),
            "tailWindowRmsRange": [round(min(tail_rms_values), 8), round(max(tail_rms_values), 8)]
            if tail_rms_values
            else [0.0, 0.0],
            "sustainRatioRange": [round(min(sustain_values), 8), round(max(sustain_values), 8)]
            if sustain_values
            else [0.0, 0.0],
            "sustainRepair": {
                "ratioFloor": SUSTAIN_RATIO_FLOOR,
                "donorRatio": SUSTAIN_DONOR_RATIO,
                "maxSemitoneDistance": SUSTAIN_REPAIR_MAX_SEMITONES,
                "maxPasses": SUSTAIN_REPAIR_MAX_PASSES,
            },
            "gainSmoothing": {
                "lambda": GAIN_SMOOTHING_LAMBDA,
                "passes": GAIN_SMOOTHING_PASSES,
            },
            "gainClamp": [GAIN_CLAMP_MIN, GAIN_CLAMP_MAX],
            "gainRange": [round(min(gain_values), 8), round(max(gain_values), 8)] if gain_values else [1.0, 1.0],
        },
        "quality": quality,
        "fillEdges": {
            "strategy": "offline_pitch_shift_from_nearest_native",
            "mapping": {str(target): source for target, source in FILL_EDGE_MAP.items()},
        },
        "sampleCount": len(sample_specs),
        "targetFrequencyCount": len(equal_targets),
        "maxMappingErrorCents": round(max_error_cents, 6),
        "worstMapping": {
            "targetHz": round(worst.target_hz, 6),
            "sampleId": worst.sample_id,
            "midi": worst.midi,
            "sampleHz": round(worst.sample_hz, 6),
            "centsError": round(worst.cents_error, 6),
        },
        "nativeSelections": selection_metadata,
        "samples": [
            {
                "id": spec.id,
                "midi": spec.midi,
                "note": spec.note,
                "hz": round(spec.hz, 6),
                "durationMs": int(round(duration * 1000)),
                "gainApplied": round(gain_map.get(spec.id, 1.0), 8),
                "windowRms": round(full_rms_map.get(spec.id, 0.0), 8),
                "attackRms": round(attack_rms_map.get(spec.id, 0.0), 8),
                "midRms": round(mid_rms_map.get(spec.id, 0.0), 8),
                "tailRms": round(tail_rms_map.get(spec.id, 0.0), 8),
                "sustainRatio": round(sustain_ratio_map.get(spec.id, 0.0), 8),
                "file": f"/assets/audio/guitar/{spec.output_filename}",
            }
            for spec in sample_specs
        ],
    }

    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def enforce_size_budget(output_dir: Path, target_mb: float, max_total_mb: float) -> tuple[int, float]:
    audio_files = sorted(output_dir.glob("*.m4a"))
    total_bytes = sum(path.stat().st_size for path in audio_files)
    total_mb = total_bytes / (1024 * 1024)

    if total_mb > max_total_mb:
        raise SystemExit(
            f"Audio package is {total_mb:.2f}MB which exceeds hard cap {max_total_mb:.2f}MB",
        )

    if total_mb > target_mb:
        print(
            f"WARNING: audio package is {total_mb:.2f}MB, above target {target_mb:.2f}MB "
            f"but within hard cap {max_total_mb:.2f}MB",
        )

    return total_bytes, total_mb


def main() -> None:
    args = parse_args()
    require_tools()

    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    (
        peak_map,
        full_rms_map,
        attack_rms_map,
        mid_rms_map,
        tail_rms_map,
        sustain_ratio_map,
        gain_map,
        target_rms,
        global_peak_scale,
        native,
    ) = build_audio_assets(
        output_dir=output_dir,
        cache_dir=cache_dir,
        duration=args.duration,
        sample_rate=args.sample_rate,
        bitrate=args.bitrate,
        refresh_sources=args.refresh_sources,
    )

    manifest = write_manifest(
        output_dir=output_dir,
        duration=args.duration,
        sample_rate=args.sample_rate,
        bitrate=args.bitrate,
        peak_map=peak_map,
        full_rms_map=full_rms_map,
        attack_rms_map=attack_rms_map,
        mid_rms_map=mid_rms_map,
        tail_rms_map=tail_rms_map,
        sustain_ratio_map=sustain_ratio_map,
        gain_map=gain_map,
        target_rms=target_rms,
        global_peak_scale=global_peak_scale,
        native=native,
    )

    total_bytes, total_mb = enforce_size_budget(
        output_dir=output_dir,
        target_mb=args.target_mb,
        max_total_mb=args.max_total_mb,
    )

    print(
        "Built guitar samples:",
        f"{manifest['sampleCount']} files in {manifest['sampleHzRange'][0]:.1f}-{manifest['sampleHzRange'][1]:.1f}Hz, "
        f"{manifest['targetFrequencyCount']} equal targets, max mapping error {manifest['maxMappingErrorCents']:.6f} cents, "
        f"total {total_mb:.2f}MB ({total_bytes} bytes).",
    )


if __name__ == "__main__":
    main()
