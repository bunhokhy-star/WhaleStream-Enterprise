from __future__ import annotations

from recovery.crash_detector import CrashDetector


class RestartManager:
    def __init__(self, crash_detector: CrashDetector = None) -> None:
        self.crash_detector = crash_detector or CrashDetector()

    def startup_check(self) -> bool:
        return self.crash_detector.detected_unclean_shutdown()

    def mark_started(self) -> None:
        self.crash_detector.mark_running()

    def mark_stopped(self) -> None:
        self.crash_detector.mark_clean_shutdown()
