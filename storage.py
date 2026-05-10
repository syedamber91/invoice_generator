"""Persistence for drafts and archived quotations.

Backend selection is automatic:
- If TURSO_DATABASE_URL and TURSO_AUTH_TOKEN are configured (env vars or
  Streamlit secrets), use Turso (cloud SQLite via libsql).
- Otherwise fall back to a local SQLite file. This keeps local dev frictionless
  while Streamlit Cloud uses a real persistent database.

A draft holds the in-progress form payload (header info + items) under a
user-given name. An archive entry holds both the rendered PDF bytes and the
form payload so the quotation can be re-downloaded or duplicated later.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable

try:
    import streamlit as st  # used only to read st.secrets when present
except Exception:  # pragma: no cover - storage works without streamlit
    st = None


SQLITE_DEFAULT_PATH = "quotation_store.db"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _secret(name: str) -> str | None:
    """Read a config value from env, falling back to st.secrets when available."""
    val = os.environ.get(name)
    if val:
        return val
    if st is not None:
        try:
            return st.secrets[name]  # type: ignore[index]
        except Exception:
            return None
    return None


class Storage:
    """Thin wrapper over Turso (libsql-client) or local sqlite3.

    The two clients have different APIs; this class normalises them to a
    common ``query`` (SELECT) and ``execute`` (INSERT/UPDATE/DELETE) surface
    so the rest of the app doesn't need to care which backend is in use.
    """

    def __init__(self, sqlite_path: str = SQLITE_DEFAULT_PATH):
        url = _secret("TURSO_DATABASE_URL")
        token = _secret("TURSO_AUTH_TOKEN")

        if url and token:
            # libsql-client picks WebSocket transport for libsql:// URLs, which
            # Streamlit Cloud rejects with WSServerHandshakeError. Rewriting
            # the scheme to https:// switches the same client to Hrana-over-HTTP.
            if url.startswith("libsql://"):
                url = "https://" + url[len("libsql://"):]
            from libsql_client import create_client_sync  # type: ignore
            self._turso = create_client_sync(url=url, auth_token=token)
            self.backend = "turso"
        else:
            self._sqlite = sqlite3.connect(sqlite_path, check_same_thread=False)
            self._sqlite.execute("PRAGMA journal_mode=WAL")
            self.backend = "sqlite"

        self._init_schema()

    # ----- low-level ops -----

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[tuple]:
        if self.backend == "turso":
            result = self._turso.execute(sql, list(params))
            return [tuple(row) for row in result.rows]
        cur = self._sqlite.execute(sql, tuple(params))
        return cur.fetchall()

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int | None:
        """Run a write statement. Returns the inserted row id when applicable."""
        if self.backend == "turso":
            result = self._turso.execute(sql, list(params))
            return getattr(result, "last_insert_rowid", None)
        cur = self._sqlite.execute(sql, tuple(params))
        self._sqlite.commit()
        return cur.lastrowid

    # ----- schema -----

    def _init_schema(self) -> None:
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                author TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(name, author)
            )
            """
        )
        self.execute(
            """
            CREATE TABLE IF NOT EXISTS archive (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ref TEXT,
                q_ref TEXT,
                customer TEXT,
                author TEXT,
                payload_json TEXT NOT NULL,
                pdf_blob BLOB NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

    # ----- drafts -----

    def save_draft(self, name: str, author: str, payload: dict) -> int:
        """Insert a new draft, or update the existing one with the same (name, author)."""
        now = _utc_now_iso()
        payload_json = json.dumps(payload, default=str)
        existing = self.query(
            "SELECT id FROM drafts WHERE name = ? AND COALESCE(author, '') = COALESCE(?, '')",
            (name, author or ""),
        )
        if existing:
            draft_id = int(existing[0][0])
            self.execute(
                "UPDATE drafts SET payload_json = ?, updated_at = ? WHERE id = ?",
                (payload_json, now, draft_id),
            )
            return draft_id
        return int(self.execute(
            "INSERT INTO drafts (name, author, payload_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (name, author, payload_json, now, now),
        ) or 0)

    def list_drafts(self) -> list[dict]:
        rows = self.query(
            "SELECT id, name, author, updated_at FROM drafts ORDER BY updated_at DESC"
        )
        return [
            {"id": int(r[0]), "name": r[1], "author": r[2] or "", "updated_at": r[3]}
            for r in rows
        ]

    def load_draft(self, draft_id: int) -> dict | None:
        rows = self.query(
            "SELECT name, author, payload_json FROM drafts WHERE id = ?", (draft_id,)
        )
        if not rows:
            return None
        name, author, payload_json = rows[0]
        return {"name": name, "author": author or "", "payload": json.loads(payload_json)}

    def delete_draft(self, draft_id: int) -> None:
        self.execute("DELETE FROM drafts WHERE id = ?", (draft_id,))

    # ----- archive -----

    def archive_pdf(self, ref: str, q_ref: str, customer: str, author: str,
                    payload: dict, pdf_bytes: bytes) -> int:
        return int(self.execute(
            """
            INSERT INTO archive (ref, q_ref, customer, author, payload_json, pdf_blob, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ref, q_ref, customer, author, json.dumps(payload, default=str), pdf_bytes, _utc_now_iso()),
        ) or 0)

    def list_archive(self) -> list[dict]:
        rows = self.query(
            "SELECT id, ref, q_ref, customer, author, created_at FROM archive ORDER BY created_at DESC"
        )
        return [
            {
                "id": int(r[0]),
                "ref": r[1] or "",
                "q_ref": r[2] or "",
                "customer": r[3] or "",
                "author": r[4] or "",
                "created_at": r[5],
            }
            for r in rows
        ]

    def load_archive(self, archive_id: int) -> dict | None:
        rows = self.query(
            "SELECT ref, q_ref, customer, author, payload_json, pdf_blob, created_at FROM archive WHERE id = ?",
            (archive_id,),
        )
        if not rows:
            return None
        ref, q_ref, customer, author, payload_json, pdf_blob, created_at = rows[0]
        return {
            "ref": ref or "",
            "q_ref": q_ref or "",
            "customer": customer or "",
            "author": author or "",
            "payload": json.loads(payload_json),
            "pdf_bytes": bytes(pdf_blob),
            "created_at": created_at,
        }

    def delete_archive(self, archive_id: int) -> None:
        self.execute("DELETE FROM archive WHERE id = ?", (archive_id,))


_storage_singleton: Storage | None = None


def get_storage() -> Storage:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = Storage()
    return _storage_singleton
