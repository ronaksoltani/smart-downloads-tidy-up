"""CLI and watchdog event handler for the downloads organizer."""

from __future__ import annotations

import argparse
import logging
import threading
from pathlib import Path

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .organizer import CATEGORIES, organize

LOG = logging.getLogger("downloads-tidy-up")
TEMP_SUFFIXES = {".crdownload", ".part", ".tmp", ".download", ".partial"}


class DownloadHandler(FileSystemEventHandler):
    def __init__(self, root: Path, timeout: float) -> None:
        self.root = root.resolve()
        self.timeout = timeout
        self._pending: set[Path] = set()
        self._lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        self._schedule(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._schedule(event, destination=True)

    def _schedule(self, event: FileSystemEvent, destination: bool = False) -> None:
        if event.is_directory:
            return
        raw_path = event.dest_path if destination else event.src_path
        file_path = Path(raw_path).resolve()
        if file_path.parent != self.root or file_path.suffix.lower() in TEMP_SUFFIXES:
            return
        with self._lock:
            if file_path in self._pending:
                return
            self._pending.add(file_path)
        threading.Thread(target=self._process, args=(file_path,), daemon=True).start()

    def _process(self, file_path: Path) -> None:
        try:
            moved = organize(file_path, self.root, self.timeout)
            if moved:
                LOG.info("Moved %s -> %s", file_path.name, moved.relative_to(self.root))
            elif file_path.exists():
                LOG.warning("Skipped unstable file: %s", file_path.name)
        except OSError:
            LOG.exception("Could not organize %s", file_path)
        finally:
            with self._lock:
                self._pending.discard(file_path)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sort completed downloads by file type.")
    result.add_argument("--downloads", type=Path, default=Path.home() / "Downloads")
    result.add_argument("--once", action="store_true", help="Sort current top-level files and exit")
    result.add_argument("--settle-timeout", type=float, default=120,
                        help="Seconds to wait for each file to stop changing")
    result.add_argument("--log-file", type=Path, default=Path("downloads-tidy-up.log"))
    return result


def main() -> int:
    args = parser().parse_args()
    root = args.downloads.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"Downloads directory does not exist: {root}")
    if args.settle_timeout <= 0:
        raise SystemExit("--settle-timeout must be greater than zero.")
    logging.basicConfig(filename=args.log_file, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if args.once:
        for file_path in sorted(root.iterdir()):
            moved = organize(file_path, root, args.settle_timeout)
            if moved:
                print(f"{file_path.name} -> {moved.relative_to(root)}")
        return 0

    observer = Observer()
    observer.schedule(DownloadHandler(root, args.settle_timeout), str(root), recursive=False)
    observer.start()
    print(f"Watching {root}. Press Ctrl+C to stop.")
    try:
        observer.join()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
