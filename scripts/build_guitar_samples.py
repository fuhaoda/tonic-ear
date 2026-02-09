#!/usr/bin/env python3
"""Download and rebuild aligned guitar samples that match piano sample ordering."""

from __future__ import annotations

import argparse
from array import array
from dataclasses import dataclass
import json
from math import log2, sqrt
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

TARGET_PEAK_LINEAR = 0.90
GAIN_CLAMP_MIN = 0.10
GAIN_CLAMP_MAX = 5.00
LOW_RMS_FLOOR_RATIO = 0.25
LOW_RMS_DONOR_RATIO = 0.70
TONAL_HIGHPASS_HZ = 80.0
TONAL_RATIO_FLOOR = 0.25
TONAL_DONOR_RATIO = 0.70

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


def collect_native_selections(cache_dir: Path, sample_rate: int) -> dict[int, NativeSelection]:
    global_best: dict[int, NativeSelection] = {}

    for filename in RANGE_FILENAMES:
        expected_midis = parse_filename_expected_midis(filename)
        source_path = cache_dir / filename
        file_best = detect_candidates_for_file(
            source_path=source_path,
            expected_midis=expected_midis,
            sample_rate=sample_rate,
        )

        missing = [midi for midi in expected_midis if midi not in file_best]
        if missing:
            print(f"WARNING: {filename} missing candidate MIDI values: {missing}")

        for midi, candidate in file_best.items():
            selection = NativeSelection(
                midi=midi,
                source_filename=filename,
                onset_sec=candidate.onset_sec,
                estimated_midi=candidate.estimated_midi,
                rms=candidate.rms,
            )
            previous = global_best.get(midi)
            if previous is None or selection.rms > previous.rms:
                global_best[midi] = selection

    required = list(range(NATIVE_MIN_MIDI, NATIVE_MAX_MIDI + 1))
    missing_global = [midi for midi in required if midi not in global_best]
    if missing_global:
        raise SystemExit(
            "Failed to detect full native guitar MIDI range "
            f"{NATIVE_MIN_MIDI}-{NATIVE_MAX_MIDI}; missing {missing_global}",
        )

    return global_best


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


def measure_highpass_rms(input_path: Path, sample_rate: int, cutoff_hz: float) -> float:
    ffmpeg_cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-vn",
        "-af",
        f"highpass=f={cutoff_hz:.3f}",
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
    if not samples:
        return 0.0
    energy = 0.0
    for value in samples:
        energy += value * value
    return sqrt(energy / len(samples))


def repair_low_energy_temp_wavs(
    temp_paths: dict[int, Path],
    sample_rate: int,
    duration: float,
) -> tuple[dict[str, float], dict[str, float], float]:
    """Repair near-silent extracted notes by regenerating from nearby robust donors."""

    peak_map: dict[str, float] = {}
    rms_map: dict[str, float] = {}
    for spec in build_sample_specs("guitar"):
        peak, rms = measure_peak_and_window_rms(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            analysis_duration_sec=duration,
        )
        peak_map[spec.id] = peak
        rms_map[spec.id] = rms

    nonzero_rms = [value for value in rms_map.values() if value > 0]
    if not nonzero_rms:
        raise SystemExit("All extracted guitar samples are silent")

    rms_target = median(nonzero_rms)
    low_floor = rms_target * LOW_RMS_FLOOR_RATIO
    donor_floor = rms_target * LOW_RMS_DONOR_RATIO

    def donor_midis() -> list[int]:
        mids: list[int] = []
        for spec in build_sample_specs("guitar"):
            if rms_map.get(spec.id, 0.0) >= donor_floor:
                mids.append(spec.midi)
        return mids

    donors = donor_midis()
    if not donors:
        raise SystemExit("No robust donor notes found for low-energy guitar repair")

    repaired_any = False
    for spec in build_sample_specs("guitar"):
        rms_value = rms_map.get(spec.id, 0.0)
        if rms_value >= low_floor:
            continue

        donor_midi = min(donors, key=lambda midi: abs(midi - spec.midi))
        if donor_midi == spec.midi:
            continue

        repaired_any = True
        pitch_shift_wav_to_midi(
            input_path=temp_paths[donor_midi],
            output_path=temp_paths[spec.midi],
            source_midi=donor_midi,
            target_midi=spec.midi,
            duration=duration,
            sample_rate=sample_rate,
        )
        peak, rms = measure_peak_and_window_rms(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            analysis_duration_sec=duration,
        )
        peak_map[spec.id] = peak
        rms_map[spec.id] = rms
        donors = donor_midis()

    if repaired_any:
        nonzero_rms = [value for value in rms_map.values() if value > 0]
        rms_target = median(nonzero_rms)

    return peak_map, rms_map, rms_target


def repair_low_tonal_ratio_temp_wavs(
    temp_paths: dict[int, Path],
    peak_map: dict[str, float],
    rms_map: dict[str, float],
    sample_rate: int,
    duration: float,
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """Repair muddy/near-DC notes by deriving from nearby tonally strong notes."""

    ratio_map: dict[str, float] = {}
    for spec in build_sample_specs("guitar"):
        hrms = measure_highpass_rms(temp_paths[spec.midi], sample_rate=sample_rate, cutoff_hz=TONAL_HIGHPASS_HZ)
        rms = max(rms_map.get(spec.id, 0.0), 1e-12)
        ratio_map[spec.id] = hrms / rms

    def donor_midis() -> list[int]:
        mids: list[int] = []
        for spec in build_sample_specs("guitar"):
            if ratio_map.get(spec.id, 0.0) >= TONAL_DONOR_RATIO:
                mids.append(spec.midi)
        return mids

    donors = donor_midis()
    if not donors:
        return peak_map, rms_map, ratio_map

    repaired_any = False
    for spec in build_sample_specs("guitar"):
        ratio = ratio_map.get(spec.id, 0.0)
        if ratio >= TONAL_RATIO_FLOOR:
            continue

        donor_midi = min(donors, key=lambda midi: abs(midi - spec.midi))
        if donor_midi == spec.midi:
            continue

        repaired_any = True
        pitch_shift_wav_to_midi(
            input_path=temp_paths[donor_midi],
            output_path=temp_paths[spec.midi],
            source_midi=donor_midi,
            target_midi=spec.midi,
            duration=duration,
            sample_rate=sample_rate,
        )
        peak, rms = measure_peak_and_window_rms(
            temp_paths[spec.midi],
            sample_rate=sample_rate,
            analysis_duration_sec=duration,
        )
        peak_map[spec.id] = peak
        rms_map[spec.id] = rms
        hrms = measure_highpass_rms(temp_paths[spec.midi], sample_rate=sample_rate, cutoff_hz=TONAL_HIGHPASS_HZ)
        ratio_map[spec.id] = hrms / max(rms, 1e-12)
        donors = donor_midis()
        if not donors:
            break

    if repaired_any:
        for spec in build_sample_specs("guitar"):
            hrms = measure_highpass_rms(temp_paths[spec.midi], sample_rate=sample_rate, cutoff_hz=TONAL_HIGHPASS_HZ)
            ratio_map[spec.id] = hrms / max(rms_map.get(spec.id, 0.0), 1e-12)

    return peak_map, rms_map, ratio_map


def compute_gain_map_from_full_rms(
    peak_map: dict[str, float],
    rms_map: dict[str, float],
) -> tuple[dict[str, float], float, float]:
    nonzero = [value for value in rms_map.values() if value > 0]
    if not nonzero:
        raise SystemExit("Cannot normalize guitar samples: all RMS values are zero")

    target_rms = median(nonzero)
    gain_map: dict[str, float] = {}
    max_predicted_peak = 0.0
    for spec in build_sample_specs("guitar"):
        rms = rms_map.get(spec.id, 0.0)
        if rms <= 0:
            gain = 1.0
        else:
            gain = target_rms / rms
        gain = max(GAIN_CLAMP_MIN, min(GAIN_CLAMP_MAX, gain))
        gain_map[spec.id] = gain
        predicted_peak = peak_map.get(spec.id, 0.0) * gain
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
    float,
    float,
    dict[int, NativeSelection],
]:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_sources(cache_dir, refresh_sources=refresh_sources)

    native = collect_native_selections(cache_dir=cache_dir, sample_rate=sample_rate)

    peak_map: dict[str, float] = {}
    rms_map: dict[str, float] = {}
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

        peak_map, rms_map, _target_rms = repair_low_energy_temp_wavs(
            temp_paths=temp_paths,
            sample_rate=sample_rate,
            duration=duration,
        )
        peak_map, rms_map, tonal_ratio_map = repair_low_tonal_ratio_temp_wavs(
            temp_paths=temp_paths,
            peak_map=peak_map,
            rms_map=rms_map,
            sample_rate=sample_rate,
            duration=duration,
        )

        gain_map, target_rms, global_peak_scale = compute_gain_map_from_full_rms(
            peak_map=peak_map,
            rms_map=rms_map,
        )

        for spec in build_sample_specs("guitar"):
            output_path = output_dir / spec.output_filename
            encode_final_sample(
                temp_wav_path=temp_paths[spec.midi],
                output_path=output_path,
                bitrate=bitrate,
                gain=gain_map.get(spec.id, 1.0),
            )

    return peak_map, rms_map, tonal_ratio_map, gain_map, target_rms, global_peak_scale, native


def write_manifest(
    output_dir: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    peak_map: dict[str, float],
    rms_map: dict[str, float],
    tonal_ratio_map: dict[str, float],
    gain_map: dict[str, float],
    target_rms: float,
    global_peak_scale: float,
    native: dict[int, NativeSelection],
) -> dict:
    sample_specs = build_sample_specs("guitar")
    equal_targets = get_unique_equal_temperament_targets()
    max_error_cents, worst = worst_mapping_error(equal_targets, instrument="guitar")

    peak_values = [value for value in peak_map.values() if value > 0]
    rms_values = [value for value in rms_map.values() if value > 0]
    gain_values = [value for value in gain_map.values() if value > 0]
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
            "method": "full_window_rms_with_global_peak_guard",
            "targetRms": round(target_rms, 8),
            "targetPeakLinear": TARGET_PEAK_LINEAR,
            "globalPeakScale": round(global_peak_scale, 8),
            "peakRange": [round(min(peak_values), 6), round(max(peak_values), 6)] if peak_values else [0.0, 0.0],
            "windowRmsMs": int(round(duration * 1000)),
            "windowRmsRange": [round(min(rms_values), 8), round(max(rms_values), 8)] if rms_values else [0.0, 0.0],
            "gainClamp": [GAIN_CLAMP_MIN, GAIN_CLAMP_MAX],
            "gainRange": [round(min(gain_values), 8), round(max(gain_values), 8)] if gain_values else [1.0, 1.0],
            "lowRmsRepairFloorRatio": LOW_RMS_FLOOR_RATIO,
            "lowRmsDonorRatio": LOW_RMS_DONOR_RATIO,
            "tonalRepairHighpassHz": TONAL_HIGHPASS_HZ,
            "tonalRatioFloor": TONAL_RATIO_FLOOR,
            "tonalDonorRatio": TONAL_DONOR_RATIO,
            "tonalRatioRange": [
                round(min(tonal_ratio_map.values()), 6),
                round(max(tonal_ratio_map.values()), 6),
            ]
            if tonal_ratio_map
            else [0.0, 0.0],
        },
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
                "windowRms": round(rms_map.get(spec.id, 0.0), 8),
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

    peak_map, rms_map, tonal_ratio_map, gain_map, target_rms, global_peak_scale, native = build_audio_assets(
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
        rms_map=rms_map,
        tonal_ratio_map=tonal_ratio_map,
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
