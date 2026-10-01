"""Filesystem classification, stability checks, and collision-safe moves."""

from __future__ import annotations

import shutil
import time
from pathlib import Path

CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".ppt", ".pptx", ".xls", ".xlsx", ".csv"},
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".tif", ".tiff"},
    "Video": {".mp4", ".mkv", ".mov", ".avi", ".webm"},
    "Audio": {".mp3", ".wav", ".m4a", ".flac", ".ogg"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".yaml", ".yml", ".toml", ".ipynb"},
}
TEMP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".partial"}


def category_for(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    return next((name for name, suffixes in CATEGORIES.items() if suffix in suffixes), "Other")


def wait_until_stable(file_path: Path, timeout: float, interval: float = 0.5) -> bool:
    deadline = time.monotonic() + timeout
    previous_size = -1
    stable_samples = 0
    while time.monotonic() < deadline:
        if not file_path.exists():
            return False
        try:
            size = file_path.stat().st_size
        except OSError:
            stable_samples = 0
            time.sleep(interval)
            continue
        if size == previous_size:
            stable_samples += 1
            if stable_samples >= 3:
                return True
        else:
            stable_samples = 0
            previous_size = size
        time.sleep(interval)
    return False


def unique_destination(target: Path) -> Path:
    if not target.exists():
        return target
    for number in range(1, 10_000):
        candidate = target.with_name(f"{target.stem} ({number}){target.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Too many files with the same name: {target.name}")


def organize(file_path: Path, root: Path, timeout: float = 120) -> Path | None:
    file_path = file_path.resolve()
    root = root.resolve()
    if not file_path.is_file() or file_path.parent != root:
        return None
    if file_path.suffix.lower() in TEMP_SUFFIXES:
        return None
    if not wait_until_stable(file_path, timeout):
        return None
    destination_dir = root / category_for(file_path)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_destination(destination_dir / file_path.name)
    return Path(shutil.move(str(file_path), str(destination)))
