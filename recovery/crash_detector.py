from __future__ import annotations

from pathlib import Path


class CrashDetector:
    def __init__(self, lock_path: str = "history/runtime.lock") -> None:
        self.lock_path = Path(lock_path)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

    def mark_running(self) -> None:
        self.lock_path.write_text("RUNNING", encoding="utf-8")

    def mark_clean_shutdown(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def detected_unclean_shutdown(self) -> bool:
        return self.lock_path.exists()
