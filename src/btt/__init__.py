import argparse
import json
import shutil
import subprocess
from pathlib import Path

from .extract import extract_card, vision
from .video import question_intervals


def extract(video: Path, output: Path) -> None:
    if not video.is_file():
        raise ValueError(f"Video not found: {video}")
    if output.exists():
        raise ValueError(f"Output already exists: {output}; choose a new directory")
    for command in ("ffmpeg", "swift"):
        if shutil.which(command) is None:
            raise ValueError(f"Required command not found: {command}")

    print("Scanning for question changes…", flush=True)
    intervals = question_intervals(video)
    if not intervals:
        raise ValueError("No stable question frames found")
    (output / "media").mkdir(parents=True)
    cards = []
    with vision() as recognize:
        for index, interval in enumerate(intervals, 1):
            cards.append(extract_card(video, interval, output, recognize))
            if index % 50 == 0 or index == len(intervals):
                print(f"Extracted {index}/{len(intervals)}", flush=True)

    deck = {"source": f"{video.name}:{video.stat().st_size}", "cards": cards}
    (output / "deck.json").write_text(
        json.dumps(deck, ensure_ascii=False, indent=2) + "\n"
    )
    review_count = sum(bool(card["issues"]) for card in cards)
    print(f"{output}: {len(cards)} cards ({review_count} flagged for review)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract BTT questions from a recording"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    extract_args = commands.add_parser(
        "extract", help="build a deck from a BTT recording"
    )
    extract_args.add_argument("video", type=Path)
    extract_args.add_argument(
        "output",
        type=Path,
        nargs="?",
        default=Path("build/candidate"),
        help="new output directory (default: %(default)s)",
    )
    args = parser.parse_args()
    try:
        extract(args.video.expanduser(), args.output.expanduser())
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"btt: {exc}\n")
