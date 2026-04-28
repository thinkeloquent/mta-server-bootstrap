from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi_server.bootstrap.contract import LoaderReport, report_error
from fastapi_server.bootstrap.registry.ctx import Logger


@dataclass
class LoaderLogger:
    addon_name: str
    logger: Logger
    report: LoaderReport

    @property
    def _tag(self) -> str:
        return f"[{self.addon_name}]"

    def scan_dir(self, directory: str, matched: int, ignored: int) -> None:
        self.logger.debug(f"{self._tag} scan {directory}: matched={matched} ignored={ignored}")

    def ignored(self, path: str) -> None:
        self.logger.debug(f"{self._tag} ignored {path}")

    def loaded(self, path: str) -> None:
        self.logger.debug(f"{self._tag} loaded {path}")

    def registered(self, path: str, kind: Optional[str] = None) -> None:
        suffix = f" ({kind})" if kind else ""
        self.logger.debug(f"{self._tag} registered {path}{suffix}")

    def skipped(self, path: str, reason: str) -> None:
        self.logger.info(f"{self._tag} skipped {path}: {reason}")

    def failed(self, step: str, target: Optional[str], err: object) -> None:
        msg = str(err) if not isinstance(err, BaseException) else (str(err) or err.__class__.__name__)
        target_part = f" {target}" if target else ""
        # error() so the addon's swallowed failures land on stderr — without
        # this, ImportError-level breakage looks like normal stdout output.
        self.logger.error(f"{self._tag} FAIL [{step}]{target_part}: {msg}")
        report_error(self.report, step, err, target)


def create_loader_logger(
    addon_name: str,
    logger: Logger,
    report: LoaderReport,
) -> LoaderLogger:
    return LoaderLogger(addon_name=addon_name, logger=logger, report=report)
