"""Unit tests for the standalone SQLite FTS5 `scripts/academic_mcp_server.py`."""

from pathlib import Path

import pytest

from scripts.academic_mcp_server import (
    DEFAULT_CORPUS_RELATIVE_PATH,
    StandaloneCorpusDB,
    create_academic_mcp_server,
    parse_authors_field,
    resolve_db_path,
)


def test_resolve_db_path_handles_placeholders_and_tilde(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fall back cleanly when `--db` or `ACADEMIC_CORPUS_DB_PATH` is unset or an unexpanded `${VAR}`."""
    monkeypatch.delenv("ACADEMIC_CORPUS_DB_PATH", raising=False)
    expected_default = (Path.home() / DEFAULT_CORPUS_RELATIVE_PATH).resolve()

    assert resolve_db_path(None) == expected_default
    assert resolve_db_path("") == expected_default
    assert resolve_db_path("${ACADEMIC_CORPUS_DB_PATH}") == expected_default
    assert resolve_db_path(":memory:") == Path(":memory:")

    explicit = tmp_path / "nested" / "corpus.db"
    assert resolve_db_path(explicit) == explicit.resolve()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            '["Crassidis, John L.", "Junkins, John L."]',
            ["Crassidis, John L.", "Junkins, John L."],
        ),
        (
            "Vallado, David A.; McClain, Wayne D.",
            ["Vallado, David A.", "McClain, Wayne D."],
        ),
        ("Bar-Shalom, Yaakov and Li, X. Rong", ["Bar-Shalom, Yaakov", "Li, X. Rong"]),
        ("   ", []),
    ],
)
def test_parse_authors_field(raw: str, expected: list[str]) -> None:
    """Split JSON arrays, commas, semicolons, and `'and'` author strings cleanly."""
    assert parse_authors_field(raw) == expected


def test_standalone_corpus_db_auto_initializes_and_searches(tmp_path: Path) -> None:
    """Auto-create parent directories, FTS5 triggers, BM25 search, chunk fetch, and author listing."""
    db_file = tmp_path / "fresh_dir" / "papers" / "academic_corpus.db"
    assert not db_file.exists()

    with StandaloneCorpusDB(db_file) as db:
        assert db_file.is_file()
        assert db.search_chunks("unscented kalman filter") == []
        assert db.search_chunks("   ") == []
        assert db.read_chunk(999) == {"error": "Chunk with ID 999 not found."}
        assert db.list_unique_authors() == []

        with db._conn:
            db._conn.execute(
                """
                INSERT INTO papers (id, path, title, authors, is_parsed)
                VALUES (?, ?, ?, ?, 1);
                """,
                (
                    "crassidis2003",
                    "papers/crassidis2003.pdf",
                    "Unscented Filtering for Spacecraft Attitude Estimation",
                    '["John L. Crassidis", "F. Landis Markley"]',
                ),
            )
            db._conn.execute(
                """
                INSERT INTO papers (id, path, title, authors, is_parsed)
                VALUES (?, ?, ?, ?, 1);
                """,
                (
                    "julier2004",
                    "papers/julier2004.pdf",
                    "Unscented Filtering and Nonlinear Estimation",
                    "Simon J. Julier and Jeffrey K. Uhlmann; F. Landis Markley",
                ),
            )
            cur = db._conn.execute(
                """
                INSERT INTO chunks (paper_id, section_title, page_start, page_end, markdown_content, contains_math)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (
                    "crassidis2003",
                    " Attitude Quaternion Kinematics ",
                    4,
                    6,
                    "Modified Rodrigues parameters avoid quaternion unit-norm singularities in unscented attitude filters.",
                    1,
                ),
            )
            chunk_id = int(cur.lastrowid or 1)

        hits = db.search_chunks("Rodrigues quaternion", limit=5)
        assert len(hits) == 1
        assert hits[0]["chunk_id"] == chunk_id
        assert hits[0]["paper_id"] == "crassidis2003"
        assert "Rodrigues" in hits[0]["snippet"]

        # Malformed FTS5 query syntax must fall back to quoted tokenization rather than raising
        fallback_hits = db.search_chunks('Rodrigues "quaternion AND (', limit=5)
        assert len(fallback_hits) == 1
        assert fallback_hits[0]["chunk_id"] == chunk_id

        chunk_data = db.read_chunk(chunk_id)
        assert (
            chunk_data["paper_title"]
            == "Unscented Filtering for Spacecraft Attitude Estimation"
        )
        assert chunk_data["contains_math"] is True
        assert "Modified Rodrigues parameters" in chunk_data["markdown_content"]

        assert db.list_unique_authors() == [
            "F. Landis Markley",
            "Jeffrey K. Uhlmann",
            "John L. Crassidis",
            "Simon J. Julier",
        ]


def test_create_academic_mcp_server_registers_expected_tools() -> None:
    """Expose `search_academic_corpus`, `read_parsed_chunk`, and `list_authors` on `MCPServer`."""
    app, db = create_academic_mcp_server(db_path=":memory:")
    try:
        assert app.name == "academic-corpus"
        registered = {tool.name for tool in app._tool_manager.list_tools()}
        assert registered == {
            "search_academic_corpus",
            "read_parsed_chunk",
            "list_authors",
        }

        assert db.search_chunks("orbit") == []
    finally:
        db.close()
