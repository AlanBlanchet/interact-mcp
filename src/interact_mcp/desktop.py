import re
import subprocess

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


def window_listing(windows: list[DesktopWindow]) -> str:
    return "\n".join(
        f"  {w.name} ({w.w}x{w.h})" for w in sorted(windows, key=lambda w: w.name)
    )
