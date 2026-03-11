from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, TextIO


LevelName = str
MessageSupplier = str | Callable[[], str]

_LEVELS: dict[LevelName, int] = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "error": 40,
    "off": 100,
}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_level(level: str | None) -> str:
    if not level:
        return "info"
    lv = level.strip().lower()
    return lv if lv in _LEVELS else "info"


@dataclass(slots=True)
class RunLogger:
    enabled: bool
    level: str
    log_path: Path | None
    _threshold: int = field(init=False, repr=False)
    _fh: TextIO | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        self.level = _normalize_level(self.level)
        self._threshold = _LEVELS[self.level]

        if not self.enabled or self.log_path is None:
            return

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.log_path.open("a", encoding="utf-8")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._fh.close()
            self._fh = None

    def is_enabled_for(self, level: str) -> bool:
        if not self.enabled or self._fh is None:
            return False
        return _LEVELS[_normalize_level(level)] >= self._threshold

    def debug(self, msg: MessageSupplier) -> None:
        self._log("debug", msg)

    def info(self, msg: MessageSupplier) -> None:
        self._log("info", msg)

    def warning(self, msg: MessageSupplier) -> None:
        self._log("warning", msg)

    def error(self, msg: MessageSupplier) -> None:
        self._log("error", msg)

    def _log(self, level: str, msg: MessageSupplier) -> None:
        if not self.is_enabled_for(level):
            return

        if callable(msg):
            try:
                text = msg()
            except Exception as exc:
                text = f"<log supplier failed: {type(exc).__name__}: {exc}>"
        else:
            text = msg

        assert self._fh is not None
        self._fh.write(f"{_now_iso()} [{level.upper()}] {text}\n")
        self._fh.flush()


def build_logger(root: Path, crawl_cfg: dict) -> RunLogger:
    logging_cfg = crawl_cfg.get("logging", {}) or {}
    enabled = bool(logging_cfg.get("enabled", True))
    level = str(logging_cfg.get("level", "info"))
    rel_path = str(logging_cfg.get("file", "logs/step1_crawler.log"))
    log_path = root / rel_path if enabled else None
    return RunLogger(enabled=enabled, level=level, log_path=log_path)
