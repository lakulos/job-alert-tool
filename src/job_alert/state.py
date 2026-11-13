from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path


class StateStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sent_jobs (
                url TEXT PRIMARY KEY,
                sent_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS processed_messages (
                message_id TEXT PRIMARY KEY,
                processed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                finished_at TEXT NOT NULL,
                job_count INTEGER NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> StateStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def sent_urls(self) -> set[str]:
        return {row[0] for row in self.connection.execute("SELECT url FROM sent_jobs")}

    def processed_message_ids(self) -> set[str]:
        return {row[0] for row in self.connection.execute("SELECT message_id FROM processed_messages")}

    def mark_delivered(self, urls: Iterable[str], message_ids: Iterable[str]) -> None:
        when = datetime.now(UTC).isoformat()
        url_rows = [(url, when) for url in set(urls)]
        message_rows = [(message_id, when) for message_id in set(message_ids) if message_id]
        with self.connection:
            self.connection.executemany(
                "INSERT OR IGNORE INTO sent_jobs(url, sent_at) VALUES (?, ?)", url_rows
            )
            self.connection.executemany(
                "INSERT OR IGNORE INTO processed_messages(message_id, processed_at) VALUES (?, ?)",
                message_rows,
            )
            self.connection.execute(
                "INSERT INTO runs(finished_at, job_count) VALUES (?, ?)",
                (when, len(url_rows)),
            )
