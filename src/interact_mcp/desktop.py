import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageChops
from pydantic import BaseModel, computed_field

_MIN_AREA = 500
_LINE_RE = re.compile(
    r"(0x[0-9a-fA-F]+)\s+\"([^\"]+)\".*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)"
)


class DesktopWindow(BaseModel):
    name: str
    wid: int
    w: int
    h: int
    x: int
    y: int

    @computed_field
    @property
    def area(self) -> int:
        return self.w * self.h


def list_windows() -> list[DesktopWindow]:
    try:
        tree = subprocess.check_output(
            ["xwininfo", "-root", "-tree"], text=True, timeout=5
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []
    return [
        DesktopWindow(
            name=m.group(2),
            wid=int(m.group(1), 16),
            w=int(m.group(3)),
            h=int(m.group(4)),
            x=int(m.group(5)),
            y=int(m.group(6)),
        )
        for m in _LINE_RE.finditer(tree)
        if int(m.group(3)) * int(m.group(4)) >= _MIN_AREA
    ]


def find_window(title: str, windows: list[DesktopWindow] | None = None) -> DesktopWindow | None:
    if windows is None:
        windows = list_windows()
    hint = title.lower()
    matches = [w for w in windows if hint in w.name.lower()]
    if not matches:
        return None
    return max(matches, key=lambda w: w.area)


def capture_window(wid: int) -> bytes:
    return subprocess.check_output(["maim", "-u", "-i", str(wid)], timeout=10)


def capture_window_video(wid: int, duration: float = 3.0, fps: int = 10) -> bytes:
    geom = subprocess.check_output(
        ["xdotool", "getwindowgeometry", "--shell", str(wid)],
        text=True, timeout=5,
    )
    props = {}
    for line in geom.strip().splitlines():
        k, v = line.split("=")
        props[k] = v

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
        output_path = Path(f.name)

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "x11grab",
                "-video_size", f"{props['WIDTH']}x{props['HEIGHT']}",
                "-framerate", str(fps),
                "-i", f":0+{props['X']},{props['Y']}",
                "-c:v", "libx264", "-preset", "ultrafast",
                "-t", str(duration),
                "-pix_fmt", "yuv420p",
                str(output_path),
            ],
            check=True, capture_output=True, timeout=duration + 10,
        )
        return output_path.read_bytes()
    finally:
        output_path.unlink(missing_ok=True)


def window_listing(windows: list[DesktopWindow]) -> str:
    return "\n".join(
        f"  {w.name} ({w.w}x{w.h})" for w in sorted(windows, key=lambda w: w.name)
    )


def detect_motion(video_bytes: bytes, threshold: float = 0.01) -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "input.mp4"
            video_path.write_bytes(video_bytes)
            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(video_path),
                    "-vf", "select='eq(n\\,0)+eq(n\\,5)+eq(n\\,10)+eq(n\\,15)'",
                    "-vsync", "vfr",
                    str(Path(tmpdir) / "frame_%02d.png"),
                ],
                check=True, capture_output=True, timeout=15,
            )
            frames = sorted(Path(tmpdir).glob("frame_*.png"))
            if len(frames) < 2:
                return False
            images = [Image.open(f).convert("L") for f in frames]
            for a, b in zip(images, images[1:]):
                diff = ImageChops.difference(a, b)
                hist = diff.histogram()
                total = sum(i * count for i, count in enumerate(hist))
                mean_diff = total / (a.size[0] * a.size[1]) / 255.0
                if mean_diff > threshold:
                    return True
            return False
    except Exception:
        return True
