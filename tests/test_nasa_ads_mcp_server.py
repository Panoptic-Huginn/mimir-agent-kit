"""Unit tests for the standalone NASA ADS MCP 2.x server."""

import asyncio
import io
import json
import logging
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.client import HTTPMessage
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast

import pytest
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import TextContent

from scripts import nasa_ads_mcp_server as ads_server


if TYPE_CHECKING:
    from types import TracebackType


REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT_PATH = REPO_ROOT / "scripts" / "nasa_ads_mcp_server.py"
TEST_SCRIPT_PATH = Path(__file__).resolve()


class _FakeHTTPResponse:
    """In-memory context-managed HTTP response double for ``opener.open``."""

    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        headers: HTTPMessage | None = None,
    ) -> None:
        self._body = body
        self.status = status
        self.headers = headers if headers is not None else HTTPMessage()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        _ = (exc_type, exc_val, exc_tb)


@dataclass(slots=True)
class _RecordedCall:
    """Captured HTTP request and opener parameters."""

    request: urllib.request.Request
    timeout: float | None
    handlers: tuple[object, ...]


class _FakeOpenerFactory:
    """Factory recording ``urllib.request.build_opener`` calls and responses."""

    def __init__(
        self,
        outcome: _FakeHTTPResponse | BaseException,
    ) -> None:
        self.outcome = outcome
        self.calls: list[_RecordedCall] = []

    def build_opener(self, *handlers: object) -> object:
        def _open(
            req: urllib.request.Request,
            *,
            timeout: float | None = None,
        ) -> _FakeHTTPResponse:
            self.calls.append(
                _RecordedCall(request=req, timeout=timeout, handlers=handlers)
            )
            if isinstance(self.outcome, BaseException):
                raise self.outcome
            return self.outcome

        return SimpleNamespace(open=_open)


def _extract_tool_text(result: object) -> str:
    """Extract the first text content block from an ``MCPServer.call_tool`` result.

    Returns:
        Text payload of the first ``TextContent`` block.
    """
    content = getattr(result, "content", [])
    assert isinstance(content, list)
    assert content
    first = content[0]
    assert isinstance(first, TextContent)
    return first.text


def _extract_prompt_text(result: object) -> str:
    """Extract the first message text from an ``MCPServer.get_prompt`` result.

    Returns:
        Text payload of the first prompt message.
    """
    messages = getattr(result, "messages", [])
    assert isinstance(messages, list)
    assert messages
    content = getattr(messages[0], "content", None)
    assert isinstance(content, TextContent)
    return content.text


def _install_mock_ads_api(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    """Patch ``_ads_request_json`` with deterministic ADS fixtures and record calls.

    Returns:
        List populated with dictionaries capturing each request call.
    """
    recorded: list[dict[str, object]] = []

    def _fake_request(
        path: str,
        *,
        params: dict[str, str] | None = None,
        body: bytes | None = None,
        follow_redirects: bool = True,
        options: ads_server._AdsRequestOptions | None = None,
    ) -> dict[str, object]:
        recorded.append({
            "path": path,
            "params": params,
            "body": body,
            "follow_redirects": follow_redirects,
            "options": options,
        })
        if path in {"/search/query", "/search/bigquery"}:
            return {
                "response": {
                    "numFound": 1,
                    "start": 0,
                    "docs": [
                        {
                            "bibcode": "2020A&A...641A...1P",
                            "title": ["Planck 2018 H<SUB>0</SUB> &amp; 10<SUP>2</SUP>"],
                            "abstract": "Measurement of &Omega;<i><sub>m</sub></i> &lt; 0.32.",
                            "author": [f"Author {i}" for i in range(13)],
                        }
                    ],
                }
            }
        if path == "/metrics":
            return {"citation stats": {"total number of citations": 42}}
        if path.startswith("/export/"):
            return {"export": "@ARTICLE{2020A&A...641A...1P,\n title={Planck}\n}"}
        if path.startswith("/resolver/"):
            return {"status": 302, "location": "https://arxiv.org/pdf/1807.06209"}
        if path.startswith("/vis/"):
            return {"summaryGraph": {"nodes": [{"name": "Planck"}]}}
        return {}

    monkeypatch.setattr(ads_server, "_ads_request_json", _fake_request)
    return recorded


def test_resolve_ads_token_precedence_and_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify explicit -> ADS_API_TOKEN -> ADS_DEV_KEY -> dev_key fallback and rejections."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ADS_API_TOKEN", raising=False)
    monkeypatch.delenv("ADS_DEV_KEY", raising=False)

    assert ads_server.resolve_ads_token("  explicit-token  ") == "explicit-token"

    for invalid in ("", "   ", "${ADS_API_TOKEN}", "${OTHER_VAR}", "${partial"):
        with pytest.raises(ToolError) as exc_info:
            ads_server.resolve_ads_token(invalid)
        msg = str(exc_info.value)
        assert "https://ui.adsabs.harvard.edu/user/settings/token" in msg
        assert "Antigravity > Customizations > Plugins > Mimir Agent Kit" in msg
        assert "Configure (ADS_API_TOKEN)" in msg

    key_file = tmp_path / "custom_dev_key"
    key_file.write_text("file-token\n", encoding="utf-8")
    monkeypatch.setenv("ADS_API_TOKEN", "${ADS_API_TOKEN}")
    monkeypatch.setenv("ADS_DEV_KEY", "dev-key-token")
    assert ads_server.resolve_ads_token(ads_dev_key_path=key_file) == "dev-key-token"

    monkeypatch.setenv("ADS_DEV_KEY", "${ADS_DEV_KEY}")
    assert ads_server.resolve_ads_token(ads_dev_key_path=key_file) == "file-token"

    default_dir = tmp_path / ".ads"
    default_dir.mkdir()
    (default_dir / "dev_key").write_text("home-key-token\n", encoding="utf-8")
    assert ads_server.resolve_ads_token() == "home-key-token"

    (default_dir / "dev_key").unlink()
    with pytest.raises(ToolError, match="ADS_API_TOKEN"):
        ads_server.resolve_ads_token(ads_dev_key_path=tmp_path / "missing_key")

    bad_file = tmp_path / "bad_key"
    bad_file.write_bytes(b"\xff\xfe\xfd")
    with pytest.raises(ToolError, match="Failed to read NASA ADS key file"):
        ads_server.resolve_ads_token(ads_dev_key_path=bad_file)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", ""),
        ("H<SUB>2</SUB>O and 10<SUP>-5</SUP>", "H$_{2}$O and 10$^{-5}$"),
        (
            '<sub class="x">3</sub>He + <i>Kepler</i> &amp; &lt;5&gt;',
            "$_{3}$He + Kepler & <5>",
        ),
        (
            "<!-- note -->Mass M < 10 and R > 1 with Fe<sup >+</sup>",
            "Mass M < 10 and R > 1 with Fe$^{+}$",
        ),
    ],
)
def test_clean_ads_text_converts_markup_and_unescapes(raw: str, expected: str) -> None:
    """Convert ADS SUB/SUP tags to LaTeX, strip residual HTML, and unescape entities."""
    assert ads_server.clean_ads_text(raw) == expected


def test_ads_request_json_headers_https_guard_and_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify request headers, HTTPS host guard, and 302 redirect capture."""
    monkeypatch.setenv("ADS_API_TOKEN", "ads-secret-tok")

    ok_resp = _FakeHTTPResponse(json.dumps({"ok": True}).encode("utf-8"))
    ok_factory = _FakeOpenerFactory(ok_resp)
    monkeypatch.setattr(urllib.request, "build_opener", ok_factory.build_opener)

    payload = ads_server._ads_request_json(
        "/search/query",
        params={"q": "exoplanets"},
        options=ads_server._AdsRequestOptions(
            method="POST",
            content_type="application/json",
            timeout=15.0,
        ),
        body=b'{"x":1}',
    )
    assert payload == {"ok": True}
    assert len(ok_factory.calls) == 1
    recorded = ok_factory.calls[0]
    assert recorded.timeout == pytest.approx(15.0)
    assert recorded.handlers == ()
    assert (
        recorded.request.full_url
        == "https://api.adsabs.harvard.edu/v1/search/query?q=exoplanets"
    )
    assert recorded.request.get_method() == "POST"
    assert recorded.request.get_header("Authorization") == "Bearer ads-secret-tok"
    assert recorded.request.get_header("Accept") == "application/json"
    assert recorded.request.get_header("User-agent") == "mimir-agent-kit-nasa-ads/1.0.0"
    assert recorded.request.get_header("Content-type") == "application/json"

    with pytest.raises(ToolError, match="Invalid NASA ADS API path"):
        ads_server._ads_request_json("search/query")
    monkeypatch.setattr(ads_server, "ADS_API_BASE", "http://api.adsabs.harvard.edu/v1")
    with pytest.raises(ToolError, match="Refusing untrusted"):
        ads_server._ads_request_json("/search/query")
    monkeypatch.setattr(ads_server, "ADS_API_BASE", "https://evil.example.com/v1")
    with pytest.raises(ToolError, match="Refusing untrusted"):
        ads_server._ads_request_json("/search/query")
    monkeypatch.undo()
    monkeypatch.setenv("ADS_API_TOKEN", "ads-secret-tok")

    hdrs = HTTPMessage()
    hdrs["Location"] = "https://arxiv.org/pdf/2001.00001"
    redirect_err = urllib.error.HTTPError(
        "https://api.adsabs.harvard.edu/v1/resolver/bib/esource",
        302,
        "Found",
        hdrs,
        io.BytesIO(b""),
    )
    redirect_factory = _FakeOpenerFactory(redirect_err)
    monkeypatch.setattr(urllib.request, "build_opener", redirect_factory.build_opener)
    res = ads_server._ads_request_json(
        "/resolver/bib/esource",
        follow_redirects=False,
    )
    assert res == {"status": 302, "location": "https://arxiv.org/pdf/2001.00001"}
    assert redirect_factory.calls[0].handlers == (ads_server._NoRedirectHandler,)

    handler = ads_server._NoRedirectHandler()
    dummy_req = urllib.request.Request("https://api.adsabs.harvard.edu/v1/resolver/x")
    assert (
        handler.redirect_request(
            dummy_req,
            io.BytesIO(b""),
            302,
            "Found",
            hdrs,
            "https://arxiv.org/pdf/2001.00001",
        )
        is None
    )


def test_ads_request_json_error_mapping(monkeypatch: pytest.MonkeyPatch) -> None:
    """Map 401, 404, 429, 500, URLError, TimeoutError, and non-JSON payloads to ToolError."""
    monkeypatch.setenv("ADS_API_TOKEN", "ads-secret-tok")
    url = "https://api.adsabs.harvard.edu/v1/search/query"

    err_401 = urllib.error.HTTPError(url, 401, "Unauthorized", HTTPMessage(), None)
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(err_401).build_opener,
    )
    with pytest.raises(ToolError, match="HTTP 401") as exc_401:
        ads_server._ads_request_json("/search/query")
    assert "Configure (ADS_API_TOKEN)" in str(exc_401.value)

    err_404 = urllib.error.HTTPError(
        url, 404, "Not Found", HTTPMessage(), io.BytesIO(b"missing bibcode")
    )
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(err_404).build_opener,
    )
    with pytest.raises(ToolError, match="HTTP 404"):
        ads_server._ads_request_json("/search/query")

    rl_headers = HTTPMessage()
    rl_headers["X-RateLimit-Remaining"] = "0"
    rl_headers["X-RateLimit-Reset"] = "1795000000"
    err_429 = urllib.error.HTTPError(
        url, 429, "Too Many Requests", rl_headers, io.BytesIO(b"rate limited")
    )
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(err_429).build_opener,
    )
    with pytest.raises(ToolError, match="HTTP 429") as exc_429:
        ads_server._ads_request_json("/search/query")
    assert "X-RateLimit-Remaining=0" in str(exc_429.value)
    assert "X-RateLimit-Reset=1795000000" in str(exc_429.value)

    err_500 = urllib.error.HTTPError(
        url, 500, "Internal Server Error", HTTPMessage(), io.BytesIO(b"backend failure")
    )
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(err_500).build_opener,
    )
    with pytest.raises(ToolError, match="HTTP 500"):
        ads_server._ads_request_json("/search/query")

    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(urllib.error.URLError("dns failure")).build_opener,
    )
    with pytest.raises(ToolError, match="ADS API network error: dns failure"):
        ads_server._ads_request_json("/search/query")

    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(TimeoutError("timed out")).build_opener,
    )
    with pytest.raises(ToolError, match="ADS API network error: timed out"):
        ads_server._ads_request_json("/search/query")

    html_resp = _FakeHTTPResponse(b"<html><body>Scheduled Maintenance</body></html>")
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(html_resp).build_opener,
    )
    with pytest.raises(ToolError, match="non-JSON payload"):
        ads_server._ads_request_json("/search/query")

    list_resp = _FakeHTTPResponse(b"[1, 2, 3]")
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        _FakeOpenerFactory(list_resp).build_opener,
    )
    assert ads_server._ads_request_json("/search/query") == {"data": [1, 2, 3]}


def test_server_registers_12_tools_with_read_only_annotations() -> None:
    """All 12 tools must carry readOnly/idempotent/openWorld hints and unique titles."""
    app = ads_server.create_nasa_ads_mcp_server()
    assert app.name == "nasa-ads"
    assert app.version == "1.0.0"
    assert app.instructions is not None
    assert "bibcode:" in app.instructions
    assert "property:refereed" in app.instructions

    tools = asyncio.run(app.list_tools())
    expected_names = {
        "search",
        "get_paper",
        "get_abstract",
        "get_references",
        "get_citations",
        "bigquery",
        "metrics",
        "export_bibtex",
        "export_refs",
        "resolve_links",
        "author_network",
        "paper_network",
    }
    assert {tool.name for tool in tools} == expected_names

    titles: set[str] = set()
    for tool in tools:
        ann = tool.annotations
        assert ann is not None, f"Missing ToolAnnotations on {tool.name}"
        assert ann.title
        assert ann.title.strip()
        assert ann.read_only_hint is True
        assert ann.destructive_hint is False
        assert ann.idempotent_hint is True
        assert ann.open_world_hint is True
        titles.add(ann.title)
    assert len(titles) == 12

    templates = asyncio.run(app.list_resource_templates())
    assert [tmpl.uri_template for tmpl in templates] == ["ads://query/{encoded_q}"]

    prompts = asyncio.run(app.list_prompts())
    assert {prompt.name for prompt in prompts} == {
        "lit_review",
        "citation_chase",
        "bib_export",
    }


def test_search_record_and_citation_tools_via_mocked_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise search, get_paper, get_abstract, get_references, get_citations, and bigquery."""
    recorded = _install_mock_ads_api(monkeypatch)
    app = ads_server.create_nasa_ads_mcp_server()

    async def _exercise() -> None:
        search_res = json.loads(
            _extract_tool_text(
                await app.call_tool(
                    "search", {"q": "Planck", "rows": 5000, "start": -4}
                )
            )
        )
        assert recorded[-1]["path"] == "/search/query"
        assert recorded[-1]["params"] == {
            "q": "Planck",
            "fl": ads_server.DEFAULT_FIELDS,
            "rows": "2000",
            "sort": "date desc",
            "start": "0",
        }
        doc = search_res["docs"][0]
        assert doc["title"] == ["Planck 2018 H$_{0}$ & 10$^{2}$"]
        assert doc["abstract"] == "Measurement of Ω$_{m}$ < 0.32."
        assert len(doc["author"]) == 11
        assert doc["author"][-1] == "... +3 more"

        paper_res = json.loads(
            _extract_tool_text(
                await app.call_tool("get_paper", {"bibcode": "2020A&A...641A...1P"})
            )
        )
        assert paper_res["bibcode"] == "2020A&A...641A...1P"

        await app.call_tool("get_abstract", {"bibcode": "2020A&A...641A...1P"})
        assert cast("dict[str, str]", recorded[-1]["params"])["fl"] == (
            "bibcode,title,author,year,pub,abstract,doi,citation_count"
        )

        await app.call_tool(
            "get_references", {"bibcode": "2020A&A...641A...1P", "rows": 0}
        )
        assert recorded[-1]["params"] == {
            "q": "references(bibcode:2020A&A...641A...1P)",
            "fl": ads_server.DEFAULT_FIELDS,
            "rows": "1",
            "sort": "date desc",
            "start": "0",
        }

        await app.call_tool(
            "get_citations", {"bibcode": "2020A&A...641A...1P", "rows": 25}
        )
        assert (
            cast("dict[str, str]", recorded[-1]["params"])["sort"]
            == "citation_count desc"
        )

        bq_res = json.loads(
            _extract_tool_text(
                await app.call_tool(
                    "bigquery",
                    {"bibcodes": ["2020A&A...641A...1P", "1974Natur.248...30H"]},
                )
            )
        )
        assert bq_res["numFound"] == 1
        assert recorded[-1]["path"] == "/search/bigquery"
        assert (
            recorded[-1]["body"] == b"bibcode\n2020A&A...641A...1P\n1974Natur.248...30H"
        )
        bq_opts = recorded[-1]["options"]
        assert isinstance(bq_opts, ads_server._AdsRequestOptions)
        assert bq_opts.content_type == "big-query/csv"

    asyncio.run(_exercise())


def test_export_resolver_and_network_tools_via_mocked_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise metrics, export_bibtex, export_refs, resolve_links, and network tools."""
    recorded = _install_mock_ads_api(monkeypatch)
    app = ads_server.create_nasa_ads_mcp_server()

    async def _exercise() -> None:
        metrics_res = json.loads(
            _extract_tool_text(
                await app.call_tool("metrics", {"bibcodes": ["2020A&A...641A...1P"]})
            )
        )
        assert metrics_res["citation stats"]["total number of citations"] == 42
        assert recorded[-1]["path"] == "/metrics"

        bib_res = _extract_tool_text(
            await app.call_tool("export_bibtex", {"bibcodes": ["2020A&A...641A...1P"]})
        )
        assert "@ARTICLE{2020A&A...641A...1P" in bib_res
        assert recorded[-1]["path"] == "/export/bibtex"

        mnras_res = _extract_tool_text(
            await app.call_tool(
                "export_refs",
                {"bibcodes": ["2020A&A...641A...1P"], "format": "MNRAS"},
            )
        )
        assert "@ARTICLE" in mnras_res
        assert recorded[-1]["path"] == "/export/mnras"

        link_res = json.loads(
            _extract_tool_text(
                await app.call_tool(
                    "resolve_links",
                    {"bibcode": "2020A&A...641A...1P", "link_type": "esource"},
                )
            )
        )
        assert link_res == {
            "status": 302,
            "location": "https://arxiv.org/pdf/1807.06209",
        }
        assert recorded[-1]["path"] == "/resolver/2020A%26A...641A...1P/esource"
        assert recorded[-1]["follow_redirects"] is False

        author_net = json.loads(
            _extract_tool_text(
                await app.call_tool(
                    "author_network", {"bibcodes": ["2020A&A...641A...1P"]}
                )
            )
        )
        assert "summaryGraph" in author_net
        assert recorded[-1]["path"] == "/vis/author-network"
        vis_opts = recorded[-1]["options"]
        assert isinstance(vis_opts, ads_server._AdsRequestOptions)
        assert vis_opts.timeout == pytest.approx(ads_server.VIS_TIMEOUT)

        paper_net = json.loads(
            _extract_tool_text(
                await app.call_tool(
                    "paper_network", {"bibcodes": ["2020A&A...641A...1P"]}
                )
            )
        )
        assert "summaryGraph" in paper_net
        assert recorded[-1]["path"] == "/vis/paper-network"

        with pytest.raises(ToolError, match="must not be empty"):
            await app.call_tool("search", {"q": "   "})
        with pytest.raises(ToolError, match="at least one bibcode"):
            await app.call_tool("metrics", {"bibcodes": ["  "]})

    asyncio.run(_exercise())


def test_resource_and_prompts_via_mocked_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise ads://query/{encoded_q} resource template and all 3 MCP prompts."""
    recorded = _install_mock_ads_api(monkeypatch)
    app = ads_server.create_nasa_ads_mcp_server()

    async def _exercise() -> None:
        rsrc = await app.read_resource(
            "ads://query/author%3A%22Einstein%2C%20A.%22%20year%3A1915"
        )
        rsrc_items = list(rsrc)
        assert len(rsrc_items) == 1
        raw_content = getattr(rsrc_items[0], "content", "")
        assert isinstance(raw_content, str)
        rsrc_payload = json.loads(raw_content)
        assert rsrc_payload["query"] == 'author:"Einstein, A." year:1915'
        assert cast("dict[str, str]", recorded[-1]["params"])["rows"] == "25"

        p1 = _extract_prompt_text(
            await app.get_prompt(
                "lit_review", {"topic": "dark energy", "years": "2020-2026"}
            )
        )
        assert "dark energy" in p1
        assert "year:2020-2026" in p1

        p2 = _extract_prompt_text(
            await app.get_prompt(
                "citation_chase", {"bibcode": "1974Natur.248...30H", "depth": 2}
            )
        )
        assert "1974Natur.248...30H" in p2
        assert "depth 2" in p2

        p3 = _extract_prompt_text(
            await app.get_prompt(
                "bib_export",
                {"query": "gravitational waves", "n": 15, "format": "ris"},
            )
        )
        assert "gravitational waves" in p3
        assert "top 15" in p3
        assert "format='ris'" in p3

    asyncio.run(_exercise())


def test_main_configures_stderr_logging_and_runs_stdio(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI main() routes diagnostics strictly to stderr and starts stdio transport."""
    transports: list[str] = []
    logging_calls: list[tuple[object, object]] = []

    def _fake_basic_config(**kwargs: object) -> None:
        logging_calls.append((kwargs.get("level"), kwargs.get("stream")))

    def _fake_run(self: MCPServer, *, transport: str = "stdio") -> None:
        _ = self
        transports.append(transport)

    monkeypatch.setattr(logging, "basicConfig", _fake_basic_config)
    monkeypatch.setattr(MCPServer, "run", _fake_run)

    ads_server.main(["--log-level", "DEBUG"])

    assert logging_calls[0] == (logging.DEBUG, sys.stderr)
    assert transports == ["stdio"]
    assert not capsys.readouterr().out


def test_executable_bit_and_zero_forbidden_hardcoded_paths() -> None:
    """Verify 0755 executable permission and absence of hardcoded home directory paths."""
    mode = SERVER_SCRIPT_PATH.stat().st_mode
    assert os.access(SERVER_SCRIPT_PATH, os.X_OK)
    assert mode & stat.S_IXUSR

    forbidden_home = re.compile(r"/home" + r"/")
    forbidden_users = re.compile(r"/Users" + r"/")
    for target in (SERVER_SCRIPT_PATH, TEST_SCRIPT_PATH):
        text = target.read_text(encoding="utf-8")
        assert forbidden_home.search(text) is None, f"Forbidden path in {target}"
        assert forbidden_users.search(text) is None, f"Forbidden path in {target}"
