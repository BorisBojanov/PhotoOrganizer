"""
progress.py
Progress + ETA reporting for the parallel phases.

Two things make an ETA actually usable on a 30k-file library:

  * It is throttled by time, not by count. One line every 15 seconds is
    readable; one line per file is 30,000 lines of noise.
  * When byte totals are known the ETA is computed from bytes finished
    rather than files finished. These phases are I/O bound, and a 4 GB
    video is not "one file" worth of work next to a 2 MB jpg. Counting
    files makes the ETA lurch every time a video comes up.

Counters are mutated from worker threads, so every update takes a lock.
"""

import logging
import threading
import time


def format_duration(seconds: float) -> str:
    """Human-readable duration: '45s', '12m 30s', '2h 05m'."""
    if seconds < 0 or seconds != seconds:      # negative or NaN
        return "?"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"


def format_bytes(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} PB"


class Progress:
    """
    Count completed work from many threads and log an ETA on an interval.

    Usage:
        progress = Progress("Integrity", len(todo), sum(r.size_bytes for r in todo))
        ...  progress.advance(record.size_bytes)   # once per finished item
        progress.finish()
    """

    def __init__(self, label: str, total_items: int,
                 total_bytes: int = 0, interval_s: float = 15.0):
        self.label = label
        self.total_items = max(total_items, 0)
        self.total_bytes = max(total_bytes, 0)
        self.interval_s = interval_s

        self._lock = threading.Lock()
        self._done_items = 0
        self._done_bytes = 0
        self._start = time.monotonic()
        self._last_log = self._start

    def advance(self, size_bytes: int = 0) -> None:
        """Record one finished item. Safe to call from any thread."""
        with self._lock:
            self._done_items += 1
            self._done_bytes += size_bytes

            now = time.monotonic()
            due = now - self._last_log >= self.interval_s
            last = self._done_items >= self.total_items
            if not (due or last):
                return
            self._last_log = now
            message = self._render(now)

        # Log outside the lock: logging does I/O and can block.
        logging.info(message)

    def _render(self, now: float) -> str:
        elapsed = now - self._start

        # Fraction complete drives the ETA. Bytes track the real work when
        # we know them; fall back to file count when we don't.
        if self.total_bytes > 0:
            fraction = self._done_bytes / self.total_bytes
        elif self.total_items > 0:
            fraction = self._done_items / self.total_items
        else:
            fraction = 0.0
        fraction = min(fraction, 1.0)

        rate = self._done_items / elapsed if elapsed > 0 else 0.0
        # total_estimated - elapsed, without needing total_estimated by name
        eta = (elapsed / fraction - elapsed) if fraction > 0 else float("nan")

        parts = [f"{self.label}: {self._done_items}/{self.total_items} "
                 f"({fraction * 100:.1f}%)"]
        if self.total_bytes > 0:
            parts.append(f"{format_bytes(self._done_bytes)} of "
                         f"{format_bytes(self.total_bytes)}")
        parts.append(f"{rate:.1f} files/s")
        parts.append(f"elapsed {format_duration(elapsed)}")
        parts.append(f"ETA {format_duration(eta)}")
        return " | ".join(parts)

    def finish(self) -> None:
        elapsed = time.monotonic() - self._start
        rate = self._done_items / elapsed if elapsed > 0 else 0.0
        logging.info(
            f"{self.label}: finished {self._done_items} files in "
            f"{format_duration(elapsed)} ({rate:.1f} files/s)"
        )
