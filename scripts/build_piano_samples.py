#!/usr/bin/env python3
"""Download and rebuild aligned piano samples for fast browser playback."""

from __future__ import annotations

import argparse
from array import array
from math import sqrt
import json
from pathlib import Path
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

from app.domain.audio_samples import (
    SAMPLE_MAX_HZ,
    SAMPLE_MIN_HZ,
    build_sample_specs,
    get_unique_equal_temperament_targets,
    worst_mapping_error,
)

SOURCE_BASE_URL = "https://theremin.music.uiowa.edu/sound%20files/MIS/Piano_Other/piano"

SILENCE_THRESHOLD_DB = -50
START_SILENCE_KEEP_SEC = 0.003

RMS_WINDOW_SEC = 0.300
TARGET_PEAK_LINEAR = 0.90
GAIN_CLAMP_MIN = 0.60
GAIN_CLAMP_MAX = 3.00


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="docs/assets/audio/piano", help="Output directory")
    parser.add_argument("--cache-dir", default=".cache/piano_mis_ff", help="Source cache directory")
    parser.add_argument("--duration", type=float, default=1.0, help="Output duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Output sample rate")
    parser.add_argument("--bitrate", default="160k", help="AAC bitrate, for example 128k/160k")
    parser.add_argument("--target-mb", type=float, default=10.0, help="Soft package-size target")
    parser.add_argument("--max-total-mb", type=float, default=20.0, help="Hard package-size cap")
    parser.add_argument("--clean", action="store_true", help="Remove output dir before build")
    parser.add_argument(
        "--refresh-sources",
        action="store_true",
        help="Force re-download of all source files before processing",
    )
    return parser.parse_args()


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required but not found in PATH")


def source_url_for_filename(filename: str) -> str:
    return f"{SOURCE_BASE_URL}/{quote(filename)}"


def download_sources(cache_dir: Path, refresh_sources: bool) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)

    for spec in build_sample_specs():
        source_path = cache_dir / spec.source_filename
        if refresh_sources and source_path.exists():
            source_path.unlink()

        if source_path.exists():
            continue

        source_url = source_url_for_filename(spec.source_filename)
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


def render_trimmed_wav(
    input_path: Path,
    temp_wav_path: Path,
    duration: float,
    sample_rate: int,
) -> None:
    filter_chain = ",".join(
        [
            (
                "silenceremove="
                "start_periods=1:"
                f"start_threshold={SILENCE_THRESHOLD_DB}dB:"
                f"start_silence={START_SILENCE_KEEP_SEC:.3f}"
            ),
            "asetpts=PTS-STARTPTS",
            f"atrim=end={duration:.6f}",
            f"apad=pad_dur={duration:.6f}",
            f"atrim=end={duration:.6f}",
        ]
    )

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
        filter_chain,
        "-c:a",
        "pcm_f32le",
        str(temp_wav_path),
    ]
    subprocess.run(ffmpeg_cmd, check=True)


def measure_peak_and_window_rms(input_path: Path, sample_rate: int) -> tuple[float, float]:
    samples = decode_mono_float_samples(input_path, sample_rate=sample_rate)
    if not samples:
        return 0.0, 0.0

    peak = max(abs(value) for value in samples)

    end_index = min(len(samples), int(round(RMS_WINDOW_SEC * sample_rate)))
    window = samples[:end_index] if end_index > 0 else samples
    if not window:
        return peak, 0.0

    energy = 0.0
    for value in window:
        energy += value * value

    rms = sqrt(energy / len(window))
    return peak, rms


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
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_sources(cache_dir, refresh_sources=refresh_sources)

    peak_map: dict[str, float] = {}
    rms_map: dict[str, float] = {}
    gain_map: dict[str, float] = {}

    with tempfile.TemporaryDirectory(prefix="tonic_ear_samples_") as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        temp_wavs: dict[str, Path] = {}

        for spec in build_sample_specs():
            source_path = cache_dir / spec.source_filename
            temp_wav_path = temp_dir / f"{spec.id}.wav"

            render_trimmed_wav(
                source_path,
                temp_wav_path,
                duration=duration,
                sample_rate=sample_rate,
            )

            peak, rms = measure_peak_and_window_rms(temp_wav_path, sample_rate=sample_rate)
            peak_map[spec.id] = peak
            rms_map[spec.id] = rms
            temp_wavs[spec.id] = temp_wav_path

        for spec in build_sample_specs():
            peak = peak_map.get(spec.id, 0.0)
            if peak <= 0:
                gain = 1.0
            else:
                gain = TARGET_PEAK_LINEAR / peak

            gain = max(GAIN_CLAMP_MIN, min(GAIN_CLAMP_MAX, gain))
            gain_map[spec.id] = gain

            output_path = output_dir / spec.output_filename
            encode_final_sample(temp_wavs[spec.id], output_path, bitrate=bitrate, gain=gain)

    return peak_map, rms_map, gain_map


def write_manifest(
    output_dir: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    peak_map: dict[str, float],
    rms_map: dict[str, float],
    gain_map: dict[str, float],
) -> dict:
    sample_specs = build_sample_specs()
    equal_targets = get_unique_equal_temperament_targets()
    max_error_cents, worst = worst_mapping_error(equal_targets)

    peak_values = [value for value in peak_map.values() if value > 0]
    rms_values = [value for value in rms_map.values() if value > 0]
    gain_values = [value for value in gain_map.values() if value > 0]

    manifest = {
        "version": 4,
        "instrument": "piano",
        "buildId": int(time.time()),
        "source": "University of Iowa MIS Piano (ff)",
        "sourceUrl": SOURCE_BASE_URL,
        "durationMs": int(round(duration * 1000)),
        "sampleRate": sample_rate,
        "codec": "aac",
        "bitrate": bitrate,
        "sampleHzRange": [SAMPLE_MIN_HZ, SAMPLE_MAX_HZ],
        "alignment": {
            "method": "silenceremove_start",
            "startThresholdDb": SILENCE_THRESHOLD_DB,
            "startSilenceKeepMs": int(round(START_SILENCE_KEEP_SEC * 1000)),
        },
        "normalization": {
            "method": "peak_normalize",
            "targetPeakLinear": TARGET_PEAK_LINEAR,
            "gainClamp": [GAIN_CLAMP_MIN, GAIN_CLAMP_MAX],
            "gainRange": [round(min(gain_values), 6), round(max(gain_values), 6)] if gain_values else [1.0, 1.0],
            "peakRange": [round(min(peak_values), 6), round(max(peak_values), 6)] if peak_values else [0.0, 0.0],
            "windowRmsMs": int(round(RMS_WINDOW_SEC * 1000)),
            "windowRmsRange": [round(min(rms_values), 8), round(max(rms_values), 8)] if rms_values else [0.0, 0.0],
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
        "samples": [
            {
                "id": spec.id,
                "midi": spec.midi,
                "note": spec.note,
                "hz": round(spec.hz, 6),
                "durationMs": int(round(duration * 1000)),
                "gainApplied": round(gain_map.get(spec.id, 1.0), 6),
                "file": f"/assets/audio/piano/{spec.output_filename}",
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
    require_ffmpeg()

    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    peak_map, rms_map, gain_map = build_audio_assets(
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
        gain_map=gain_map,
    )

    total_bytes, total_mb = enforce_size_budget(
        output_dir=output_dir,
        target_mb=args.target_mb,
        max_total_mb=args.max_total_mb,
    )

    print(
        "Built piano samples:",
        f"{manifest['sampleCount']} files in {manifest['sampleHzRange'][0]:.1f}-{manifest['sampleHzRange'][1]:.1f}Hz, "
        f"{manifest['targetFrequencyCount']} equal targets, max mapping error {manifest['maxMappingErrorCents']:.6f} cents, "
        f"total {total_mb:.2f}MB ({total_bytes} bytes).",
    )


if __name__ == "__main__":
    main()
