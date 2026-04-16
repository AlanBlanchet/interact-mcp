import asyncio
import json
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

_KEY_MAP = {
    "Enter": "Return",
    "ArrowDown": "Down",
    "ArrowUp": "Up",
    "ArrowLeft": "Left",
    "ArrowRight": "Right",
    "Backspace": "BackSpace",
    "Delete": "Delete",
    "Escape": "Escape",
    "Tab": "Tab",
    "Control": "ctrl",
    "Shift": "shift",
    "Alt": "alt",
    "Meta": "super",
}

_SCROLL_BUTTON = {"down": 5, "up": 4, "left": 6, "right": 7}


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


def find_window(
    title: str, windows: list[DesktopWindow] | None = None
) -> DesktopWindow | None:
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
        text=True,
        timeout=5,
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
                "ffmpeg",
                "-y",
                "-f",
                "x11grab",
                "-video_size",
                f"{props['WIDTH']}x{props['HEIGHT']}",
                "-framerate",
                str(fps),
                "-i",
                f":0+{props['X']},{props['Y']}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-t",
                str(duration),
                "-pix_fmt",
                "yuv420p",
                str(output_path),
            ],
            check=True,
            capture_output=True,
            timeout=duration + 10,
        )
        return output_path.read_bytes()
    finally:
        output_path.unlink(missing_ok=True)


def window_listing(windows: list[DesktopWindow]) -> str:
    return "\n".join(
        f"  {w.name} ({w.w}x{w.h})" for w in sorted(windows, key=lambda w: w.name)
    )


class DesktopElement(BaseModel):
    index: int
    x: int
    y: int
    w: int
    h: int
    role: str
    name: str

    @computed_field
    @property
    def center_x(self) -> int:
        return self.x + self.w // 2

    @computed_field
    @property
    def center_y(self) -> int:
        return self.y + self.h // 2


_desktop_elements: dict[int, list[DesktopElement]] = {}


def store_elements(wid: int, elements: list[DesktopElement]):
    _desktop_elements[wid] = elements


def get_element(wid: int, index: int) -> DesktopElement | None:
    for el in _desktop_elements.get(wid, []):
        if el.index == index:
            return el
    return None


def ref_to_index(ref: str) -> int:
    return int(ref.removeprefix("e"))


def to_interactive_elements(
    elements: list[DesktopElement],
) -> list["InteractiveElement"]:
    from interact_mcp.state import InteractiveElement

    return [
        InteractiveElement(
            index=e.index, role=e.role, name=e.name, x=e.x, y=e.y, width=e.w, height=e.h
        )
        for e in elements
    ]


def map_key(key: str) -> str:
    parts = key.split("+")
    return "+".join(_KEY_MAP.get(p, p) for p in parts)


async def _run(*args: str):
    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(
            f"{args[0]} failed (rc={proc.returncode}): {stderr.decode().strip()}"
        )


async def _xdo(wid: int, subcmd: str, *args: str):
    await _run("xdotool", subcmd, "--window", str(wid), *args)


async def desktop_click(wid: int, x: int, y: int, button: int = 1):
    await _xdo(wid, "mousemove", str(x), str(y))
    await _xdo(wid, "click", str(button))


async def desktop_type(wid: int, text: str):
    await _xdo(wid, "type", "--delay", "12", "--", text)


async def desktop_key(wid: int, key: str):
    await _xdo(wid, "key", "--", map_key(key))


async def desktop_scroll(wid: int, x: int, y: int, direction: str, amount: int = 3):
    await _xdo(wid, "mousemove", str(x), str(y))
    button = str(_SCROLL_BUTTON[direction])
    for _ in range(amount):
        await _xdo(wid, "click", button)


async def desktop_drag(wid: int, fx: int, fy: int, tx: int, ty: int, steps: int = 10):
    steps = max(1, steps)
    await _xdo(wid, "mousemove", str(fx), str(fy))
    await _xdo(wid, "mousedown", "1")
    for i in range(1, steps + 1):
        ix = fx + (tx - fx) * i // steps
        iy = fy + (ty - fy) * i // steps
        await _xdo(wid, "mousemove", str(ix), str(iy))
    await _xdo(wid, "mouseup", "1")


async def desktop_hover(wid: int, x: int, y: int):
    await _xdo(wid, "mousemove", str(x), str(y))


def format_desktop_elements(elements: list[DesktopElement]) -> str:
    return "\n".join(
        f"  [{el.index}] {el.role}: {el.name!r} ({el.w}x{el.h} at {el.x},{el.y})"
        for el in elements
    )


def parse_elements_from_vlm(response: str) -> list[DesktopElement] | None:
    start = response.find("[")
    end = response.rfind("]")
    if start == -1 or end == -1:
        return None
    try:
        raw = json.loads(response[start : end + 1])
    except json.JSONDecodeError:
        return None
    elements = []
    for i, entry in enumerate(raw):
        try:
            elements.append(
                DesktopElement(
                    index=i + 1,
                    x=int(entry["x"]),
                    y=int(entry["y"]),
                    w=int(entry["w"]),
                    h=int(entry["h"]),
                    role=str(entry.get("role", "element")),
                    name=str(entry.get("name", "")),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return elements or None


def detect_motion(video_bytes: bytes, threshold: float = 0.01) -> bool:
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "input.mp4"
            video_path.write_bytes(video_bytes)
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(video_path),
                    "-vf",
                    "select='eq(n\\,0)+eq(n\\,5)+eq(n\\,10)+eq(n\\,15)'",
                    "-vsync",
                    "vfr",
                    str(Path(tmpdir) / "frame_%02d.png"),
                ],
                check=True,
                capture_output=True,
                timeout=15,
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
