"""SQLite persistence for Phase 5 jobs and packages."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _migrate_packages_columns(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(packages)").fetchall()
    names = {str(r[1]) for r in rows}
    if "validation_passed" not in names:
        conn.execute("ALTER TABLE packages ADD COLUMN validation_passed INTEGER")
    if "validation_summary" not in names:
        conn.execute("ALTER TABLE packages ADD COLUMN validation_summary TEXT")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL,
            mode TEXT NOT NULL,
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            error_message TEXT,
            exit_code INTEGER,
            workspace_relpath TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_user_created ON jobs(user_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);

        CREATE TABLE IF NOT EXISTS packages (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            label TEXT,
            published INTEGER NOT NULL DEFAULT 0,
            created_at REAL NOT NULL,
            bundle_relpath TEXT NOT NULL,
            manifest_summary TEXT,
            validation_passed INTEGER,
            validation_summary TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_packages_user ON packages(user_id);
        """
    )
    _migrate_packages_columns(conn)
    conn.commit()


def _with_conn(db_path: Path, fn: Any) -> Any:
    with _lock:
        conn = connect(db_path)
        try:
            return fn(conn)
        finally:
            conn.close()


def job_insert(
    db_path: Path,
    *,
    job_id: str,
    user_id: str,
    status: str,
    mode: str,
    workspace_relpath: str,
) -> None:
    def op(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO jobs (id, user_id, status, mode, created_at, workspace_relpath)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, user_id, status, mode, time.time(), workspace_relpath),
        )
        conn.commit()

    _with_conn(db_path, op)


def job_get(db_path: Path, job_id: str) -> dict[str, Any] | None:
    def op(conn: sqlite3.Connection) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    return _with_conn(db_path, op)


def job_list_for_user(db_path: Path, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    def op(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT * FROM jobs WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    return _with_conn(db_path, op)


def job_count_running_for_user(db_path: Path, user_id: str) -> int:
    def op(conn: sqlite3.Connection) -> int:
        row = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE user_id = ? AND status = 'running'",
            (user_id,),
        ).fetchone()
        return int(row[0]) if row else 0

    return _with_conn(db_path, op)


def job_list_queued_ordered(db_path: Path) -> list[tuple[str, str]]:
    def op(conn: sqlite3.Connection) -> list[tuple[str, str]]:
        rows = conn.execute(
            "SELECT id, user_id FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"
        ).fetchall()
        return [(str(r["id"]), str(r["user_id"])) for r in rows]

    return _with_conn(db_path, op)


def job_try_claim(db_path: Path, job_id: str, started_at: float) -> bool:
    def op(conn: sqlite3.Connection) -> bool:
        cur = conn.execute(
            "UPDATE jobs SET status = 'running', started_at = ? WHERE id = ? AND status = 'queued'",
            (started_at, job_id),
        )
        conn.commit()
        return cur.rowcount == 1

    return _with_conn(db_path, op)


def job_finish(
    db_path: Path,
    job_id: str,
    *,
    status: str,
    exit_code: int | None = None,
    error_message: str | None = None,
) -> None:
    def op(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            UPDATE jobs SET status = ?, finished_at = ?, exit_code = ?, error_message = ?
            WHERE id = ?
            """,
            (status, time.time(), exit_code, error_message, job_id),
        )
        conn.commit()

    _with_conn(db_path, op)


def package_insert(
    db_path: Path,
    *,
    package_id: str,
    user_id: str,
    label: str | None,
    published: bool,
    bundle_relpath: str,
    manifest_summary: str | None,
    validation_passed: int | None = None,
    validation_summary: str | None = None,
) -> None:
    def op(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            INSERT INTO packages (
                id, user_id, label, published, created_at, bundle_relpath, manifest_summary,
                validation_passed, validation_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                package_id,
                user_id,
                label,
                1 if published else 0,
                time.time(),
                bundle_relpath,
                manifest_summary,
                validation_passed,
                validation_summary,
            ),
        )
        conn.commit()

    _with_conn(db_path, op)


def package_get(db_path: Path, package_id: str) -> dict[str, Any] | None:
    def op(conn: sqlite3.Connection) -> dict[str, Any] | None:
        row = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
        return dict(row) if row else None

    return _with_conn(db_path, op)


def package_list_visible(db_path: Path, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
    def op(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT * FROM packages
            WHERE user_id = ? OR published = 1
            ORDER BY created_at DESC LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    return _with_conn(db_path, op)


def package_set_published(db_path: Path, package_id: str, user_id: str, published: bool) -> bool:
    def op(conn: sqlite3.Connection) -> bool:
        cur = conn.execute(
            """
            UPDATE packages SET published = ? WHERE id = ? AND user_id = ?
            """,
            (1 if published else 0, package_id, user_id),
        )
        conn.commit()
        return cur.rowcount == 1

    return _with_conn(db_path, op)
