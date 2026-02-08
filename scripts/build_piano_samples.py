#!/usr/bin/env python3
"""Download and build compact piano samples for browser playback."""

from __future__ import annotations

import argparse
from array import array
import json
import shutil
import subprocess
from pathlib import Path
import sys
from urllib.request import urlretrieve

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domain.audio_samples import build_sample_specs, get_unique_target_frequencies, worst_mapping_error

SOURCE_BASE_URL = "https://theremin.music.uiowa.edu/sound%20files/MIS/Piano_Other/piano"
LOUDNESS_I_LUFS = -20.0
LOUDNESS_LRA = 7.0
LOUDNESS_TRUE_PEAK_DBTP = -2.0
PRE_ATTACK_MS = 5
ONSET_THRESHOLD_RATIO = 0.08
ONSET_THRESHOLD_FLOOR = 0.003
ONSET_MIN_STREAK = 96
FADE_IN_SEC = 0.003
FADE_OUT_SEC = 0.08


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        default="web/assets/audio/piano",
        help="Directory for generated m4a files and manifest.json",
    )
    parser.add_argument(
        "--cache-dir",
        default=".cache/piano_mis",
        help="Directory used to cache downloaded source aiff files",
    )
    parser.add_argument("--duration", type=float, default=2.0, help="Output duration in seconds")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Output sample rate")
    parser.add_argument("--bitrate", default="128k", help="AAC bitrate (e.g. 96k, 128k)")
    parser.add_argument(
        "--max-total-mb",
        type=float,
        default=20.0,
        help="Hard cap for total generated audio size in megabytes",
    )
    parser.add_argument(
        "--target-mb",
        type=float,
        default=10.0,
        help="Soft target size in megabytes (warning only)",
    )
    parser.add_argument("--clean", action="store_true", help="Remove existing output directory before build")
    return parser.parse_args()


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required but not found in PATH.")


def download_sources(cache_dir: Path) -> list[Path]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    source_paths: list[Path] = []

    for spec in build_sample_specs():
        source_path = cache_dir / spec.source_filename
        if not source_path.exists():
            source_url = f"{SOURCE_BASE_URL}/{spec.source_filename}"
            print(f"Downloading {source_url}")
            urlretrieve(source_url, source_path)
        source_paths.append(source_path)
    return source_paths


def detect_onset_seconds(input_path: Path, sample_rate: int) -> float:
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

    if not samples:
        return 0.0

    peak_abs = 0.0
    for value in samples:
        abs_value = abs(value)
        if abs_value > peak_abs:
            peak_abs = abs_value

    if peak_abs <= 0.0:
        return 0.0

    threshold = max(peak_abs * ONSET_THRESHOLD_RATIO, ONSET_THRESHOLD_FLOOR)
    streak = 0
    for index, value in enumerate(samples):
        if abs(value) >= threshold:
            streak += 1
            if streak >= ONSET_MIN_STREAK:
                onset_index = index - ONSET_MIN_STREAK + 1
                return onset_index / sample_rate
        else:
            streak = 0

    return 0.0


def run_ffmpeg(
    input_path: Path,
    output_path: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    trim_start_sec: float,
) -> None:
    fade_out_start = max(duration - FADE_OUT_SEC, 0.01)
    filter_chain = ",".join(
        [
            "aformat=channel_layouts=mono",
            f"aresample={sample_rate}",
            f"atrim=start={trim_start_sec:.6f}",
            "asetpts=PTS-STARTPTS",
            (
                "loudnorm="
                f"I={LOUDNESS_I_LUFS:.1f}:"
                f"LRA={LOUDNESS_LRA:.1f}:"
                f"TP={LOUDNESS_TRUE_PEAK_DBTP:.1f}:"
                "linear=true:"
                "dual_mono=true"
            ),
            f"adelay={PRE_ATTACK_MS}:all=1",
            f"apad=pad_dur={duration:.3f}",
            f"atrim=start=0:end={duration:.3f}",
            f"afade=t=in:st=0:d={FADE_IN_SEC:.3f}",
            f"afade=t=out:st={fade_out_start:.3f}:d={FADE_OUT_SEC:.3f}",
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
) -> dict[str, float]:
    output_dir.mkdir(parents=True, exist_ok=True)
    download_sources(cache_dir)
    onset_map: dict[str, float] = {}

    for spec in build_sample_specs():
        source_path = cache_dir / spec.source_filename
        output_path = output_dir / spec.output_filename
        onset_sec = detect_onset_seconds(source_path, sample_rate=sample_rate)
        onset_map[spec.id] = onset_sec
        run_ffmpeg(
            source_path,
            output_path,
            duration=duration,
            sample_rate=sample_rate,
            bitrate=bitrate,
            trim_start_sec=onset_sec,
        )
    return onset_map


def write_manifest(
    output_dir: Path,
    duration: float,
    sample_rate: int,
    bitrate: str,
    onset_map: dict[str, float],
) -> dict:
    sample_specs = build_sample_specs()
    targets = get_unique_target_frequencies()
    max_error_cents, worst = worst_mapping_error(targets=targets, sample_specs=sample_specs)
    onset_values = list(onset_map.values())
    onset_min_ms = int(round(min(onset_values) * 1000)) if onset_values else 0
    onset_max_ms = int(round(max(onset_values) * 1000)) if onset_values else 0

    manifest = {
        "version": 1,
        "source": "University of Iowa MIS Piano (mf)",
        "sourceUrl": SOURCE_BASE_URL,
        "durationMs": int(round(duration * 1000)),
        "sampleRate": sample_rate,
        "codec": "aac",
        "bitrate": bitrate,
        "normalization": {
            "type": "loudnorm",
            "integratedLufs": LOUDNESS_I_LUFS,
            "lra": LOUDNESS_LRA,
            "truePeakDbtp": LOUDNESS_TRUE_PEAK_DBTP,
        },
        "preprocess": {
            "onsetDetection": {
                "thresholdRatio": ONSET_THRESHOLD_RATIO,
                "thresholdFloor": ONSET_THRESHOLD_FLOOR,
                "minStreakSamples": ONSET_MIN_STREAK,
            },
            "trimStartMsRangeBeforePadding": [onset_min_ms, onset_max_ms],
            "preAttackMs": PRE_ATTACK_MS,
            "fadeInMs": int(round(FADE_IN_SEC * 1000)),
            "fadeOutMs": int(round(FADE_OUT_SEC * 1000)),
        },
        "sampleCount": len(sample_specs),
        "targetFrequencyCount": len(targets),
        "maxMappingErrorCents": round(max_error_cents, 6),
        "worstMapping": {
            "targetHz": round(worst.target_hz, 6),
            "sampleId": worst.sample_id,
            "sampleHz": round(worst.sample_hz, 6),
            "playbackRate": round(worst.playback_rate, 8),
            "centsError": round(worst.cents_error, 6),
        },
        "samples": [
            {
                "id": spec.id,
                "semitoneOffset": spec.semitone_offset,
                "note": spec.note,
                "hz": round(spec.hz, 6),
                "file": f"/assets/audio/piano/{spec.output_filename}",
            }
            for spec in sample_specs
        ],
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def enforce_size_budget(output_dir: Path, target_mb: float, max_total_mb: float) -> tuple[int, float]:
    audio_files = sorted(output_dir.glob("*.m4a"))
    total_bytes = sum(path.stat().st_size for path in audio_files)
    total_mb = total_bytes / (1024 * 1024)

    if total_mb > max_total_mb:
        raise SystemExit(
            f"Audio package is {total_mb:.2f}MB which exceeds hard cap {max_total_mb:.2f}MB.",
        )

    if total_mb > target_mb:
        print(
            f"WARNING: audio package is {total_mb:.2f}MB, above target {target_mb:.2f}MB "
            f"but within hard cap {max_total_mb:.2f}MB.",
        )

    return total_bytes, total_mb


def main() -> None:
    args = parse_args()
    require_ffmpeg()

    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)

    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)

    onset_map = build_audio_assets(
        output_dir=output_dir,
        cache_dir=cache_dir,
        duration=args.duration,
        sample_rate=args.sample_rate,
        bitrate=args.bitrate,
    )
    manifest = write_manifest(
        output_dir=output_dir,
        duration=args.duration,
        sample_rate=args.sample_rate,
        bitrate=args.bitrate,
        onset_map=onset_map,
    )
    total_bytes, total_mb = enforce_size_budget(
        output_dir=output_dir,
        target_mb=args.target_mb,
        max_total_mb=args.max_total_mb,
    )

    print(
        "Built piano samples:",
        f"{manifest['sampleCount']} files, {manifest['targetFrequencyCount']} target frequencies, "
        f"max mapping error {manifest['maxMappingErrorCents']:.6f} cents, total {total_mb:.2f}MB "
        f"({total_bytes} bytes).",
    )


if __name__ == "__main__":
    main()
