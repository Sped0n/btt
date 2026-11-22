import io
import subprocess
from collections.abc import Iterable, Iterator
from pathlib import Path

from PIL import Image, ImageChops

SCAN_WIDTH = 320
SCAN_HEIGHT = 180
SCAN_FPS = 5


def ffmpeg(*args: str) -> list[str]:
    return ["ffmpeg", "-nostdin", "-v", "error", *args]


def scan_frames(video: Path) -> Iterator[Image.Image]:
    command = ffmpeg(
        "-i",
        str(video),
        "-an",
        "-vf",
        f"fps={SCAN_FPS}:start_time=0,scale={SCAN_WIDTH}:{SCAN_HEIGHT},format=gray",
        "-f",
        "rawvideo",
        "-threads:v",
        "1",
        "pipe:1",
    )
    with subprocess.Popen(command, stdout=subprocess.PIPE) as process:
        assert process.stdout is not None
        size = SCAN_WIDTH * SCAN_HEIGHT
        try:
            while data := process.stdout.read(size):
                if len(data) != size:
                    raise ValueError("Incomplete frame from FFmpeg")
                yield Image.frombytes("L", (SCAN_WIDTH, SCAN_HEIGHT), data)
            if process.wait():
                raise subprocess.CalledProcessError(process.returncode, command)
        finally:
            if process.poll() is None:
                process.kill()


def question_intervals(video: Path) -> list[tuple[float, float]]:
    return stable_intervals(scan_frames(video))


def stable_intervals(frames: Iterable[Image.Image]) -> list[tuple[float, float]]:
    # Ignore the right-hand panel so animation does not create extra questions.
    signature_boxes = [(4, 5, 58, 22), (12, 22, 205, 75), (7, 103, 160, 166)]
    thresholds = [12, 65, 45]
    intervals = []
    reference = None
    start = 0
    for index, frame in enumerate(frames):
        signature = [frame.crop(box) for box in signature_boxes]
        if reference is not None and any(
            sum(ImageChops.difference(old, new).histogram()[35:]) >= threshold
            for old, new, threshold in zip(
                reference, signature, thresholds, strict=True
            )
        ):
            if index - start >= 3:
                intervals.append((start / SCAN_FPS, index / SCAN_FPS))
            start = index
            reference = None
        if reference is None:
            reference = signature
    if reference is not None and index + 1 - start >= 3:
        intervals.append((start / SCAN_FPS, (index + 1) / SCAN_FPS))
    return intervals


def read_frame(video: Path, seconds: float) -> Image.Image:
    data = subprocess.check_output(
        ffmpeg(
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            "-vf",
            "scale=1280:-2",
            "-threads:v",
            "1",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "pipe:1",
        )
    )
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGB")


def panel_has_motion(
    video: Path, start: float, end: float, panel: tuple[int, int, int, int]
) -> bool:
    x0, y0, x1, y1 = panel
    inset = min(0.3, (end - start) / 4)
    size = 80 * 60
    data = subprocess.check_output(
        ffmpeg(
            "-ss",
            f"{start + inset:.3f}",
            "-t",
            f"{end - start - 2 * inset:.3f}",
            "-i",
            str(video),
            "-an",
            "-vf",
            f"fps=5,scale=1280:720,crop={x1 - x0}:{y1 - y0}:{x0}:{y0},scale=80:60,format=gray",
            "-f",
            "rawvideo",
            "-threads:v",
            "1",
            "pipe:1",
        )
    )
    if len(data) < 2 * size:
        return False
    first = Image.frombytes("L", (80, 60), data[:size])
    return any(
        sum(
            ImageChops.difference(
                first, Image.frombytes("L", (80, 60), data[i : i + size])
            ).histogram()[20:]
        )
        >= 30
        for i in range(size, len(data), size)
    )


def write_panel_clip(
    video: Path,
    start: float,
    end: float,
    panel: tuple[int, int, int, int],
    output: Path,
) -> None:
    x0, y0, x1, y1 = panel
    offset = min(0.2, (end - start) / 4)
    subprocess.run(
        ffmpeg(
            "-y",
            "-ss",
            f"{start + offset:.3f}",
            "-i",
            str(video),
            "-t",
            f"{end - start - 2 * offset:.3f}",
            "-an",
            "-vf",
            f"scale=1280:720,crop={x1 - x0}:{y1 - y0}:{x0}:{y0}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output),
        ),
        check=True,
    )
