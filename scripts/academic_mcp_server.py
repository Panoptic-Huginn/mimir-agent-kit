#!/usr/bin/env python3
"""Standalone Academic Corpus Model Context Protocol (MCP) Server.

Provides a zero-repo-dependency stdio MCP server exposing full-text search
(`search_academic_corpus`), chunk retrieval (`read_parsed_chunk`), and author
enumeration (`list_authors`) over a local SQLite FTS5 academic corpus database.

Schema-compatible with `heimdall-astro`'s `academic_corpus.db` while running
cleanly on any Ubuntu Linux or macOS machine without requiring a repository
checkout. If the configured SQLite file does not yet exist, parent directories
and the empty FTS5 schema are initialized automatically so MCP startup never fails.
"""

import argparse
import contextlib
import json
import logging
import os
import re
import sqlite3
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from mcp.server.mcpserver import MCPServer


if TYPE_CHECKING:
    from types import TracebackType


logger = logging.getLogger("academic_mcp")

DEFAULT_CORPUS_RELATIVE_PATH = (
    Path(".local") / "share" / "mimir-agent-kit" / "academic_corpus.db"
)
_UNEXPANDED_PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z0-9_]+\}$")

_SCHEMA_SQL: str = """
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    size_bytes INTEGER,
    sha256 TEXT,
    acquisition_source TEXT,
    title TEXT,
    authors TEXT,
    abstract TEXT,
    tldr TEXT,
    parsed_dir TEXT,
    is_parsed BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    paper_id TEXT,
    section_title TEXT,
    page_start INTEGER,
    page_end INTEGER,
    markdown_content TEXT,
    contains_math BOOLEAN DEFAULT 0,
    FOREIGN KEY (paper_id) REFERENCES papers (id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    paper_id UNINDEXED,
    section_title,
    markdown_content,
    content='chunks',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, paper_id, section_title, markdown_content)
    VALUES (new.id, new.paper_id, new.section_title, new.markdown_content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, paper_id, section_title, markdown_content)
    VALUES ('delete', old.id, old.paper_id, old.section_title, old.markdown_content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, paper_id, section_title, markdown_content)
    VALUES ('delete', old.id, old.paper_id, old.section_title, old.markdown_content);
    INSERT INTO chunks_fts(rowid, paper_id, section_title, markdown_content)
    VALUES (new.id, new.paper_id, new.section_title, new.markdown_content);
END;

CREATE INDEX IF NOT EXISTS idx_papers_is_parsed ON papers(is_parsed);
CREATE INDEX IF NOT EXISTS idx_chunks_paper_id ON chunks(paper_id);
"""

_JOINED_FTS_SEARCH_SQL: str = """
SELECT
    c.id AS chunk_id,
    c.paper_id,
    c.section_title,
    c.page_start,
    c.page_end,
    p.title AS paper_title,
    p.authors,
    snippet(chunks_fts, -1, '<b>', '</b>', '...', 25) AS snippet,
    chunks_fts.rank
FROM chunks_fts
JOIN chunks c ON c.id = chunks_fts.rowid
JOIN papers p ON p.id = c.paper_id
WHERE chunks_fts MATCH ?
ORDER BY chunks_fts.rank ASC
LIMIT ?;
"""

_READ_CHUNK_SQL: str = """
SELECT
    c.id AS chunk_id,
    c.paper_id,
    c.section_title,
    c.page_start,
    c.page_end,
    c.markdown_content,
    c.contains_math,
    p.title AS paper_title,
    p.authors
FROM chunks c
JOIN papers p ON p.id = c.paper_id
WHERE c.id = ?;
"""

_LIST_AUTHORS_SQL: str = """
SELECT DISTINCT authors
FROM papers
WHERE authors IS NOT NULL AND trim(authors) != '';
"""


def resolve_db_path(db_path: Path | str | None = None) -> Path:
    """Resolve the target SQLite corpus path, expanding `~` and handling placeholders.

    Falls back to `~/.local/share/mimir-agent-kit/academic_corpus.db` when `db_path`
    (and `ACADEMIC_CORPUS_DB_PATH`) is unset, empty, or an unexpanded `${VAR}`
    plugin variable placeholder.

    Args:
        db_path: Explicit path string/object, `':memory:'`, or `None`.

    Returns:
        Resolved `Path` to the SQLite database (or `Path(':memory:')`).
    """
    candidate = (
        str(db_path).strip()
        if db_path is not None
        else os.environ.get("ACADEMIC_CORPUS_DB_PATH", "").strip()
    )
    if not candidate or _UNEXPANDED_PLACEHOLDER_RE.match(candidate):
        return (Path.home() / DEFAULT_CORPUS_RELATIVE_PATH).resolve()
    if candidate == ":memory:":
        return Path(":memory:")
    return Path(candidate).expanduser().resolve()


def parse_authors_field(raw_text: str) -> list[str]:
    """Parse and normalize author names from a database `authors` column value.

    Handles JSON arrays (e.g., `'["Author A", "Author B"]'`), semicolon/BibTeX
    `'Last, First'` lists, and comma- or `'and'`-delimited `'First Last'` lists.

    Args:
        raw_text: Raw string value from `papers.authors`.

    Returns:
        List of stripped, non-empty author names.
    """
    cleaned = raw_text.strip()
    if not cleaned:
        return []

    if cleaned.startswith("[") and cleaned.endswith("]"):
        with contextlib.suppress(json.JSONDecodeError, ValueError):
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]

    if ";" in cleaned:
        parts = re.split(r";|\band\b", cleaned)
    elif (
        re.search(r"\band\b", cleaned)
        and cleaned.count(",") == len(re.findall(r"\band\b", cleaned)) + 1
    ):
        parts = re.split(r"\band\b", cleaned)
    else:
        parts = re.split(r"[,;]|\band\b", cleaned)
    return [part.strip() for part in parts if part.strip()]


class StandaloneCorpusDB:
    """Thread-safe SQLite FTS5 wrapper for the academic paper corpus."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Open (and initialize if needed) the SQLite academic corpus database.

        Args:
            db_path: Path to SQLite database file, `':memory:'`, or `None` for default.
        """
        resolved = resolve_db_path(db_path)
        self.is_memory = str(resolved) == ":memory:"
        self.db_path = resolved
        self.raw_path = ":memory:" if self.is_memory else str(resolved)
        self._lock = threading.RLock()

        if not self.is_memory:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(
            self.raw_path,
            timeout=5.0,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_pragmas_and_schema()

    def _init_pragmas_and_schema(self) -> None:
        """Configure WAL/foreign-key pragmas and ensure tables/FTS5 triggers exist."""
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON;")
            self._conn.execute("PRAGMA busy_timeout = 5000;")
            if not self.is_memory:
                self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.executescript(_SCHEMA_SQL)

    def search_chunks(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search indexed chunks via FTS5 BM25 ranking with syntax-error fallback.

        Args:
            query: Keyword search expression or phrase.
            limit: Maximum number of results to return.

        Returns:
            List of matched chunk metadata dictionaries ordered by BM25 rank.
        """
        trimmed = query.strip()
        if not trimmed or limit <= 0:
            return []

        with self._lock:
            try:
                cursor = self._conn.execute(_JOINED_FTS_SEARCH_SQL, (trimmed, limit))
                rows = cursor.fetchall()
            except sqlite3.OperationalError:
                fts_operators = {"AND", "OR", "NOT", "NEAR"}
                tokens = [
                    tok
                    for tok in re.findall(r'"[^"]*"|\b\w+\b', trimmed)
                    if tok not in fts_operators
                ]
                if not tokens:
                    return []
                safe_tokens = [
                    tok if (tok.startswith('"') and tok.endswith('"')) else f'"{tok}"'
                    for tok in tokens
                ]
                safe_query = " ".join(safe_tokens)
                try:
                    cursor = self._conn.execute(
                        _JOINED_FTS_SEARCH_SQL, (safe_query, limit)
                    )
                    rows = cursor.fetchall()
                except sqlite3.OperationalError:
                    return []

        return [
            {
                "chunk_id": int(row["chunk_id"])
                if row["chunk_id"] is not None
                else None,
                "paper_id": str(row["paper_id"]),
                "paper_title": str(row["paper_title"])
                if row["paper_title"] is not None
                else None,
                "authors": str(row["authors"]) if row["authors"] is not None else None,
                "section_title": str(row["section_title"])
                if row["section_title"] is not None
                else None,
                "page_start": int(row["page_start"])
                if row["page_start"] is not None
                else None,
                "page_end": int(row["page_end"])
                if row["page_end"] is not None
                else None,
                "snippet": str(row["snippet"]),
                "rank": float(row["rank"]),
            }
            for row in rows
        ]

    def read_chunk(self, chunk_id: int) -> dict[str, Any]:
        """Fetch full Markdown content and paper metadata for a single chunk ID.

        Args:
            chunk_id: Integer primary key in `chunks.id`.

        Returns:
            Chunk dictionary, or `{'error': ...}` if `chunk_id` does not exist.
        """
        with self._lock:
            cursor = self._conn.execute(_READ_CHUNK_SQL, (chunk_id,))
            row = cursor.fetchone()

        if row is None:
            return {"error": f"Chunk with ID {chunk_id} not found."}

        return {
            "chunk_id": int(row["chunk_id"]),
            "paper_id": str(row["paper_id"]),
            "paper_title": str(row["paper_title"])
            if row["paper_title"] is not None
            else None,
            "authors": str(row["authors"]) if row["authors"] is not None else None,
            "section_title": str(row["section_title"])
            if row["section_title"] is not None
            else None,
            "page_start": int(row["page_start"])
            if row["page_start"] is not None
            else None,
            "page_end": int(row["page_end"]) if row["page_end"] is not None else None,
            "contains_math": bool(row["contains_math"]),
            "markdown_content": str(row["markdown_content"]),
        }

    def list_unique_authors(self) -> list[str]:
        """Return a case-insensitively sorted list of unique authors in the corpus.

        Returns:
            Sorted list of deduplicated author names.
        """
        with self._lock:
            cursor = self._conn.execute(_LIST_AUTHORS_SQL)
            raw_rows = cursor.fetchall()

        authors_set: set[str] = set()
        for (raw_entry,) in raw_rows:
            if raw_entry:
                authors_set.update(parse_authors_field(str(raw_entry)))

        return sorted(authors_set, key=str.casefold)

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Self:
        """Enter context manager.

        Returns:
            Active `StandaloneCorpusDB` instance.
        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the SQLite connection on context exit."""
        self.close()


def create_academic_mcp_server(
    db_path: Path | str | None = None,
    server_name: str = "academic-corpus",
) -> tuple[MCPServer, StandaloneCorpusDB]:
    """Create and configure the Academic Corpus `MCPServer` and backing database.

    Args:
        db_path: Optional path to SQLite database (or `':memory:'` for tests).
        server_name: Identifier for the MCP server instance.

    Returns:
        Tuple of `(MCPServer, StandaloneCorpusDB)`.
    """
    db = StandaloneCorpusDB(db_path)

    app = MCPServer(
        name=server_name,
        version="1.0.0",
        instructions=(
            "Provides full-text FTS5 BM25 search, chunk Markdown retrieval, and author lookup over locally indexed academic and engineering papers."
        ),
    )

    @app.tool()
    def search_academic_corpus(query: str, limit: int = 10) -> str:
        """Search academic paper chunks using FTS5 full-text search with BM25 ranking.

        Args:
            query: Keyword search expression or phrase.
            limit: Maximum number of search results to return (default 10).

        Returns:
            Formatted JSON string containing matched chunk metadata and snippets.
        """
        return json.dumps(db.search_chunks(query=query, limit=limit), indent=2)

    @app.tool()
    def read_parsed_chunk(chunk_id: int) -> str:
        """Retrieve complete parsed Markdown content and metadata for a specific chunk.

        Args:
            chunk_id: Database integer primary key of the target chunk.

        Returns:
            JSON string containing chunk metadata and Markdown content, or an error object.
        """
        return json.dumps(db.read_chunk(chunk_id=chunk_id), indent=2)

    @app.tool()
    def list_authors() -> list[str]:
        """List all unique authors across registered papers in the academic corpus.

        Returns:
            Alphabetically sorted list of deduplicated author names.
        """
        return db.list_unique_authors()

    return (app, db)


def main(argv: list[str] | None = None) -> None:
    """Run the Academic Corpus MCP server over standard I/O (`stdio`).

    All diagnostics are routed strictly to `sys.stderr` to preserve JSON-RPC frames
    on `sys.stdout`.

    Args:
        argv: Optional CLI argument list (defaults to `sys.argv[1:]`).
    """
    parser = argparse.ArgumentParser(
        prog="academic_mcp_server",
        description="Standalone Academic Corpus MCP Server (SQLite FTS5)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite academic corpus database (falls back to ACADEMIC_CORPUS_DB_PATH or ~/.local/share/mimir-agent-kit/academic_corpus.db)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Diagnostic logging level (routed strictly to stderr)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper()),
        stream=sys.stderr,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app, db = create_academic_mcp_server(db_path=args.db)
    logger.info("Starting Academic Corpus MCP Server with db_path=%s", db.db_path)
    try:
        app.run(transport="stdio")
    finally:
        db.close()


if __name__ == "__main__":
    main()
