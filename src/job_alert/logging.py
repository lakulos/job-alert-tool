from __future__ import annotations

import logging
from collections.abc import Iterable


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for value in self.secrets:
            message = message.replace(value, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def configure_logging(verbose: bool, secrets: Iterable[str] = ()) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(SecretRedactionFilter(secrets))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
        force=True,
    )
