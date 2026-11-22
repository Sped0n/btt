import io
import json
import re
import select
import subprocess
from base64 import b64encode
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

from PIL import Image, ImageOps

from .video import panel_has_motion, read_frame, write_panel_clip

Box = tuple[int, int, int, int]
HEADER = re.compile(r"QUESTION\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
LETTERS = "ABC"


class Line(TypedDict):
    text: str
    confidence: float
    x: float
    y: float


class Choice(TypedDict, total=False):
    text: str
    image: str


class Card(TypedDict):
    id: str
    time: float
    number: int | None
    total: int | None
    prompt: str
    choices: list[Choice]
    answer: int | None
    image: str | None
    clip: str | None
    issues: list[str]
    evidence: str | None


Recognizer = Callable[[Image.Image], list[Line]]


@contextmanager
def vision() -> Iterator[Recognizer]:
    helper = Path(__file__).with_name("ocr.swift")

    process: subprocess.Popen[str] | None = None
    requests = 0

    def stop() -> None:
        nonlocal process, requests
        if process is not None:
            if process.poll() is None:
                process.kill()
            with process:
                pass
            process = None
        requests = 0

    def recognize(image: Image.Image) -> list[Line]:
        nonlocal process, requests
        with io.BytesIO() as buffer:
            image.save(buffer, "JPEG", quality=94)
            request = b64encode(buffer.getvalue()).decode("ascii") + "\n"
        for fast in (False, True):
            if process is None:
                command = ["swift", str(helper)]
                if fast:
                    command.append("--fast")
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
                )
            assert process.stdin is not None and process.stdout is not None
            process.stdin.write(request)
            process.stdin.flush()
            if not select.select([process.stdout], [], [], 12 if requests else 35)[0]:
                stop()
                continue
            response = process.stdout.readline()
            if not response:
                raise ValueError("Apple Vision stopped without returning an OCR result")
            requests += 1
            # Recycle Vision's worker rather than sharing its state for a whole deck.
            if fast or requests == 32:
                stop()
            return json.loads(response)
        raise TimeoutError("Apple Vision OCR timed out")

    try:
        yield recognize
    finally:
        stop()


def text_in(lines: list[Line], box: Box) -> list[Line]:
    x0, y0, x1, y1 = box
    return sorted(
        (
            line
            for line in lines
            if x0 <= line["x"] * 1280 < x1 and y0 <= line["y"] * 720 < y1
        ),
        key=lambda line: (round(line["y"] * 72), line["x"]),
    )


def text_of(lines: list[Line]) -> str:
    return " ".join(line["text"] for line in lines)


def panel_box(image: Image.Image) -> Box | None:
    # A thin dark divider is present even when the picture itself has white regions.
    if sum(max(image.getpixel((844, y))) < 110 for y in range(72, 300, 8)) < 24:
        return None
    if max(image.getpixel((1000, 33))) < 195 or max(image.getpixel((844, 28))) < 110:
        return (858, 22, 1254, 320)
    return (852, 64, 1250, 364)


def is_blue(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    return blue - red > 55 and blue - green > 25


def save_image(image: Image.Image, output: Path, name: str) -> str:
    relative = f"media/{name}.webp"
    image.save(output / relative, quality=92, method=6)
    return relative


def option_picture(image: Image.Image, row: Box, text: str) -> Image.Image | None:
    # In the source, sign choices sit directly after the printed A/B/C label.
    _, top, _, bottom = row
    color = image.crop((76, top + 3, 161, bottom - 3))
    # Averaging suppresses the colored fringes around italic text.
    averaged = color.resize((28, 26), Image.Resampling.BOX)
    pixels = averaged.load()
    assert pixels is not None
    count = 0
    for y in range(averaged.height):
        for x in range(averaged.width):
            rgb = pixels[x, y]
            count += max(rgb) - min(rgb) > 65 and min(rgb) < 135
    if count >= 45:
        return color
    if not text:
        # Preserve any non-text choice even if it has no saturated colors.
        full = image.crop((76, top + 3, 1087, bottom - 3))
        bounds = (
            full.convert("L").point(lambda pixel: 255 if pixel < 160 else 0).getbbox()
        )
        if bounds and bounds[2] - bounds[0] >= 10:
            return full.crop(bounds)
    return None


def recover_choice_text(picture: Image.Image, recognize: Recognizer) -> str | None:
    # Wide fallback crops can be text that Vision missed in the full frame.
    if picture.width < 2 * picture.height:
        return None
    enlarged = picture.resize(
        (picture.width * 2, picture.height * 2), Image.Resampling.LANCZOS
    )
    try:
        lines = recognize(ImageOps.expand(enlarged, border=24, fill="white"))
    except TimeoutError:
        return None
    if not lines or min(line["confidence"] for line in lines) < 0.85:
        return None
    text = text_of(sorted(lines, key=lambda line: (line["y"], line["x"])))
    if sum(any(char.isalnum() for char in word) for word in text.split()) < 2:
        return None
    return text


def extract_card(
    video: Path,
    interval: tuple[float, float],
    output: Path,
    recognize: Recognizer,
) -> Card:
    start, end = interval
    timestamp = round((start + end) / 2, 3)
    card_id = f"q{round(start * 1000):07d}"
    image = read_frame(video, timestamp)
    issues = []
    try:
        lines = recognize(image)
    except TimeoutError:
        lines = []
        issues.append("OCR timed out")
    header = HEADER.search(text_of(text_in(lines, (10, 15, 300, 74))))
    panel = panel_box(image)
    has_video = panel is not None and panel[1] == 22
    prompt_lines = text_in(
        lines, (30, 76, 835 if panel else 1245, 298 if has_video else 325)
    )
    prompt = text_of(prompt_lines)
    choices: list[Choice] = []
    answer_markers = []
    for index, letter in enumerate(LETTERS):
        top = (420 if has_video else 400) + index * 96
        bottom = top + 86
        row = (24, top, 1090, bottom)
        label = rf"^\(\s*{letter}\s*\)\s*"
        option_lines = text_in(lines, row)
        text = " ".join(
            re.sub(label, "", line["text"], flags=re.IGNORECASE)
            if line["x"] * 1280 < 73
            else line["text"]
            for line in option_lines
        ).strip()
        if not any(character.isalnum() for character in text):
            text = ""
        picture = option_picture(image, row, text)
        if picture is not None:
            recovered = recover_choice_text(picture, recognize) if not text else None
            if recovered is not None:
                choices.append({"text": recovered})
            else:
                choices.append(
                    {"image": save_image(picture, output, f"{card_id}-{letter}")}
                )
        else:
            choices.append({"text": text})
            if (
                not text
                or not option_lines
                or min(line["confidence"] for line in option_lines) < 0.6
            ):
                issues.append(f"Check choice {letter}")
        if all(is_blue(image.getpixel((x, top + 11))) for x in (1104, 1120, 1240)):
            answer_markers.append(index)

    answer = answer_markers[0] if len(answer_markers) == 1 else None
    if answer is None:
        issues.append("No unique blue answer marker")
    else:
        top = (420 if has_video else 400) + answer * 96
        if (
            "correct"
            not in text_of(text_in(lines, (1094, top, 1254, top + 86))).lower()
        ):
            issues.append("OCR did not confirm the blue answer marker")
    if header is None:
        issues.append("No question number detected")
    if not prompt or min(line["confidence"] for line in prompt_lines) < 0.6:
        issues.append("Check prompt text")

    picture = save_image(image.crop(panel), output, card_id) if panel else None
    clip = None
    if panel is not None and has_video and panel_has_motion(video, start, end, panel):
        clip = f"media/{card_id}.mp4"
        write_panel_clip(video, start, end, panel, output / clip)
    evidence = save_image(image, output, f"{card_id}-review") if issues else None
    return {
        "id": card_id,
        "time": timestamp,
        "number": int(header[1]) if header else None,
        "total": int(header[2]) if header else None,
        "prompt": prompt,
        "choices": choices,
        "answer": answer,
        "image": picture,
        "clip": clip,
        "issues": issues,
        "evidence": evidence,
    }
