#!/usr/bin/env python3
"""Standalone NASA Astrophysics Data System (ADS) MCP Server (MCP 2.x).

Provides a zero-third-party-HTTP-dependency stdio Model Context Protocol (MCP)
server exposing 12 NASA ADS REST API v1 tools (``search``, ``get_paper``,
``get_abstract``, ``get_references``, ``get_citations``, ``bigquery``,
``metrics``, ``export_bibtex``, ``export_refs``, ``resolve_links``,
``author_network``, ``paper_network``), the ``ads://query/{encoded_q}``
resource template, and 3 literature-workflow prompts.
"""

import argparse
import html
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, override

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations


if TYPE_CHECKING:
    from http.client import HTTPMessage
    from typing import IO


logger = logging.getLogger("nasa_ads_mcp")

ADS_API_HOST: Final[str] = "api.adsabs.harvard.edu"
ADS_API_BASE: Final[str] = f"https://{ADS_API_HOST}/v1"
ADS_SETTINGS_URL: Final[str] = "https://ui.adsabs.harvard.edu/user/settings/token"
ANTIGRAVITY_CONFIGURE_HINT: Final[str] = (
    "Antigravity > Customizations > Plugins > Mimir Agent Kit > Configure (ADS_API_TOKEN)"
)
USER_AGENT: Final[str] = "mimir-agent-kit-nasa-ads/1.0.0"

DEFAULT_TIMEOUT: Final[float] = 30.0
VIS_TIMEOUT: Final[float] = 60.0
DEFAULT_FIELDS: Final[str] = (
    "bibcode,title,author,year,pub,abstract,doi,citation_count,read_count,bibstem"
)
DEFAULT_AUTHOR_KEEP: Final[int] = 10
MIN_ROWS: Final[int] = 1
MAX_ROWS: Final[int] = 2000
RESOURCE_DEFAULT_ROWS: Final[int] = 25
ERROR_DETAIL_LIMIT: Final[int] = 300
NON_JSON_PREVIEW_LIMIT: Final[int] = 200

HTTP_REDIRECT_MIN: Final[int] = 300
HTTP_CLIENT_ERROR_MIN: Final[int] = 400
HTTP_UNAUTHORIZED: Final[int] = 401
HTTP_NOT_FOUND: Final[int] = 404
HTTP_TOO_MANY_REQUESTS: Final[int] = 429

_UNEXPANDED_PLACEHOLDER_RE: Final[re.Pattern[str]] = re.compile(
    r"^\$\{[A-Za-z0-9_]+\}$"
)
_SUB_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"<sub\b[^>]*>(.*?)</sub>",
    re.IGNORECASE | re.DOTALL,
)
_SUP_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"<sup\b[^>]*>(.*?)</sup>",
    re.IGNORECASE | re.DOTALL,
)
_HTML_TAG_RE: Final[re.Pattern[str]] = re.compile(
    r"<!--.*?-->|</?[A-Za-z][A-Za-z0-9]*(?:\s[^<>]*)?/?>",
    re.DOTALL,
)

SERVER_INSTRUCTIONS: Final[str] = (
    "NASA Astrophysics Data System (ADS) REST API v1 server. "
    'Use Solr query syntax in `search`: `author:"Last, F."`, '
    '`first_author:"Last, F."`, `bibcode:...`, `arXiv:...`, `doi:...`, '
    '`abs:"phrase"`, `year:2020-2026`, and `property:refereed`. '
    "Start discovery with `search`; use `get_paper` or `get_abstract` for single "
    "bibcodes, `bigquery` for batch metadata up to 2000 bibcodes, "
    "`get_references`/`get_citations` to traverse citation graphs, "
    "`export_bibtex`/`export_refs` for formatted references, `resolve_links` "
    "for full-text/arXiv/DOI URLs, and `metrics`/`author_network`/`paper_network` "
    "for bibliometric analysis."
)


def _is_unconfigured_token(candidate: str) -> bool:
    """Return True when ``candidate`` is empty or an unexpanded ``${...}`` token.

    Returns:
        ``True`` if blank or an unexpanded placeholder, ``False`` otherwise.
    """
    return (
        not candidate
        or bool(_UNEXPANDED_PLACEHOLDER_RE.match(candidate))
        or candidate.startswith("${")
    )


def resolve_ads_token(
    explicit_token: str | None = None,
    *,
    ads_dev_key_path: Path | None = None,
) -> str:
    """Resolve and validate the NASA ADS Bearer token.

    Resolution order: ``explicit_token`` -> ``ADS_API_TOKEN`` env var ->
    ``ADS_DEV_KEY`` env var -> ``ads_dev_key_path`` (default ``~/.ads/dev_key``).
    Empty/whitespace values and unexpanded Antigravity ``${VAR}`` placeholders
    are rejected.

    Args:
        explicit_token: Optional explicit token override (useful in tests).
        ads_dev_key_path: Optional path to ADS developer key file (defaults to
            ``~/.ads/dev_key``).

    Returns:
        Validated non-empty NASA ADS API token string.

    Raises:
        ToolError: If no valid token is configured or the key file cannot be read.
    """
    if explicit_token is not None:
        cleaned = explicit_token.strip()
        if _is_unconfigured_token(cleaned):
            raise ToolError(
                "ADS_API_TOKEN is missing or unexpanded. Create a token at "
                f"{ADS_SETTINGS_URL} and configure it in {ANTIGRAVITY_CONFIGURE_HINT}."
            )
        return cleaned

    for env_var in ("ADS_API_TOKEN", "ADS_DEV_KEY"):
        env_candidate = os.environ.get(env_var, "").strip()
        if not _is_unconfigured_token(env_candidate):
            return env_candidate

    key_file = (ads_dev_key_path or Path("~/.ads/dev_key")).expanduser()
    if key_file.is_file():
        try:
            file_candidate = key_file.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise ToolError(
                f"Failed to read NASA ADS key file at {key_file}: {exc}. "
                f"Create a token at {ADS_SETTINGS_URL} and configure it in "
                f"{ANTIGRAVITY_CONFIGURE_HINT}."
            ) from exc
        if not _is_unconfigured_token(file_candidate):
            return file_candidate

    raise ToolError(
        "ADS_API_TOKEN is not configured. Create a token at "
        f"{ADS_SETTINGS_URL} and set it via {ANTIGRAVITY_CONFIGURE_HINT}."
    )


def clean_ads_text(text: str) -> str:
    """Convert ADS HTML subscript/superscript markup to LaTeX and strip residual tags.

    Converts ``<SUB>...</SUB>`` to ``$_{...}$`` and ``<SUP>...</SUP>`` to
    ``$^{...}$``, strips remaining HTML tags/comments while leaving plain
    mathematical ``<``/``>`` comparisons intact, and unescapes HTML entities.

    Args:
        text: Raw ADS title or abstract string.

    Returns:
        Cleaned text with LaTeX sub/superscripts and decoded HTML entities.
    """
    if not text:
        return ""
    converted = _SUB_TAG_RE.sub(r"$_{\1}$", text)
    converted = _SUP_TAG_RE.sub(r"$^{\1}$", converted)
    stripped = _HTML_TAG_RE.sub("", converted)
    return html.unescape(stripped)


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """HTTP redirect handler that stops on 3xx responses instead of following them."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        _ = (req, fp, code, msg, headers, newurl)
        return None


@dataclass(slots=True, frozen=True, kw_only=True)
class _AdsRequestOptions:
    """Transport options for :func:`_ads_request_json`."""

    method: str = "GET"
    content_type: str | None = None
    timeout: float = DEFAULT_TIMEOUT


def _get_header(headers: object, name: str) -> str | None:
    """Fetch a header case-insensitively from an ``HTTPMessage`` or mapping.

    Returns:
        Header value string if present, otherwise ``None``.
    """
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if not callable(getter):
        return None
    direct = getter(name)
    if isinstance(direct, str):
        return direct
    lower = getter(name.lower())
    return lower if isinstance(lower, str) else None


def _build_ads_url(path: str, params: dict[str, str] | None = None) -> str:
    """Construct and validate a NASA ADS API v1 HTTPS URL.

    Returns:
        Validated ``https://api.adsabs.harvard.edu/v1/...`` URL string.

    Raises:
        ToolError: If ``path`` or the resulting URL fails HTTPS/host validation.
    """
    if not path.startswith("/") or any(ch.isspace() for ch in path):
        raise ToolError(f"Invalid NASA ADS API path: {path!r}")
    url = f"{ADS_API_BASE}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != ADS_API_HOST:
        raise ToolError(f"Refusing untrusted NASA ADS API URL: {url}")
    return url


def _handle_http_error(
    exc: urllib.error.HTTPError,
    *,
    follow_redirects: bool,
) -> dict[str, object]:
    """Translate ``HTTPError`` into a 3xx redirect payload or actionable ``ToolError``.

    Returns:
        Redirect descriptor dictionary when ``follow_redirects=False`` and 3xx.

    Raises:
        ToolError: On HTTP 401, 404, 429, or any other >=400 error status.
    """
    headers = exc.headers
    if not follow_redirects and HTTP_REDIRECT_MIN <= exc.code < HTTP_CLIENT_ERROR_MIN:
        return {
            "status": exc.code,
            "location": _get_header(headers, "Location"),
        }
    if exc.code == HTTP_UNAUTHORIZED:
        raise ToolError(
            "ADS API authentication failed (HTTP 401: invalid or expired token). "
            f"Generate a valid token at {ADS_SETTINGS_URL} and update "
            f"{ANTIGRAVITY_CONFIGURE_HINT}."
        ) from exc
    if exc.code == HTTP_TOO_MANY_REQUESTS:
        remaining = _get_header(headers, "X-RateLimit-Remaining")
        reset = _get_header(headers, "X-RateLimit-Reset")
        raise ToolError(
            "ADS API rate limit exceeded (HTTP 429; "
            f"X-RateLimit-Remaining={remaining}, X-RateLimit-Reset={reset})."
        ) from exc
    detail = exc.read().decode("utf-8", errors="replace")[:ERROR_DETAIL_LIMIT]
    if exc.code == HTTP_NOT_FOUND:
        raise ToolError(f"ADS API resource not found (HTTP 404): {detail}") from exc
    raise ToolError(f"ADS API error (HTTP {exc.code}): {detail}") from exc


def _ads_request_json(
    path: str,
    *,
    params: dict[str, str] | None = None,
    body: bytes | None = None,
    follow_redirects: bool = True,
    options: _AdsRequestOptions | None = None,
) -> dict[str, object]:
    """Execute an authenticated NASA ADS REST API v1 request and decode JSON.

    Args:
        path: Endpoint path beginning with ``/`` under ``/v1``.
        params: Optional URL query parameters.
        body: Optional encoded request body bytes.
        follow_redirects: When ``False``, return 3xx status and ``Location``.
        options: Optional HTTP method, ``Content-Type``, and socket timeout.

    Returns:
        Decoded JSON dictionary (or ``{"data": ...}`` / redirect descriptor).

    Raises:
        ToolError: On missing token, untrusted URL, HTTP errors, network errors,
            or non-JSON maintenance payloads.
    """
    opts = options or _AdsRequestOptions()
    url = _build_ads_url(path, params)
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != ADS_API_HOST:
        raise ToolError(f"Refusing untrusted NASA ADS API URL: {url}")

    token = resolve_ads_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }
    if opts.content_type:
        headers["Content-Type"] = opts.content_type

    req = urllib.request.Request(  # ruff: ignore[suspicious-url-open-usage] - scheme=='https' and netloc=='api.adsabs.harvard.edu' verified above
        url,
        data=body,
        headers=headers,
        method=opts.method,
    )
    opener = (
        urllib.request.build_opener()
        if follow_redirects
        else urllib.request.build_opener(_NoRedirectHandler)
    )

    try:
        with opener.open(req, timeout=opts.timeout) as resp:
            status = getattr(resp, "status", None)
            if (
                not follow_redirects
                and isinstance(status, int)
                and HTTP_REDIRECT_MIN <= status < HTTP_CLIENT_ERROR_MIN
            ):
                return {
                    "status": status,
                    "location": _get_header(getattr(resp, "headers", None), "Location"),
                }
            raw_bytes: bytes = resp.read()
    except urllib.error.HTTPError as exc:
        try:
            return _handle_http_error(exc, follow_redirects=follow_redirects)
        finally:
            exc.close()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        raise ToolError(f"ADS API network error: {reason}") from exc

    try:
        decoded = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        preview = raw_bytes.decode("utf-8", errors="replace").strip()[
            :NON_JSON_PREVIEW_LIMIT
        ]
        raise ToolError(
            f"ADS API returned non-JSON payload (possible maintenance): {preview}"
        ) from exc
    return (
        {str(key): value for key, value in decoded.items()}
        if isinstance(decoded, dict)
        else {"data": decoded}
    )


def _clamp_rows(rows: int) -> int:
    """Clamp requested row count safely into ``[1, 2000]``.

    Returns:
        Row count clamped between ``1`` and ``2000``.
    """
    return max(MIN_ROWS, min(rows, MAX_ROWS))


def _clamp_start(start: int) -> int:
    """Clamp pagination offset safely to ``>= 0``.

    Returns:
        Non-negative starting offset.
    """
    return max(0, start)


def _require_non_empty(value: str, label: str) -> str:
    """Strip ``value`` and raise ``ToolError`` if blank.

    Returns:
        Stripped non-empty string.

    Raises:
        ToolError: If ``value`` is empty or whitespace-only.
    """
    cleaned = value.strip()
    if not cleaned:
        raise ToolError(f"Parameter '{label}' must not be empty.")
    return cleaned


def _require_bibcodes(bibcodes: list[str]) -> list[str]:
    """Strip and validate a non-empty list of ADS bibcodes.

    Returns:
        List of stripped non-empty bibcode strings.

    Raises:
        ToolError: If no non-empty bibcodes remain.
    """
    cleaned = [item.strip() for item in bibcodes if item.strip()]
    if not cleaned:
        raise ToolError("Parameter 'bibcodes' must contain at least one bibcode.")
    return cleaned


def _trim_authors(
    doc: dict[str, object],
    keep: int = DEFAULT_AUTHOR_KEEP,
) -> dict[str, object]:
    """Cap long ``author`` lists at ``keep`` entries with a ``... +N more`` suffix.

    Returns:
        Copy of ``doc`` with truncated ``author`` list when over ``keep``.
    """
    authors = doc.get("author")
    if isinstance(authors, list) and len(authors) > keep:
        return {
            **doc,
            "author": [*authors[:keep], f"... +{len(authors) - keep} more"],
        }
    return doc


def _clean_text_field(value: object) -> object:
    """Apply :func:`clean_ads_text` to string or string-list ADS metadata fields.

    Returns:
        Cleaned string, list of cleaned strings, or original non-text value.
    """
    if isinstance(value, str):
        return clean_ads_text(value)
    if isinstance(value, list):
        return [
            clean_ads_text(item) if isinstance(item, str) else item for item in value
        ]
    return value


def _normalize_doc(doc: dict[str, object]) -> dict[str, object]:
    """Clean HTML/LaTeX markup in ``title``/``abstract`` and trim ``author`` lists.

    Returns:
        Normalized ADS document dictionary.
    """
    normalized = _trim_authors(doc)
    for field_name in ("title", "abstract"):
        if field_name in normalized:
            normalized = {
                **normalized,
                field_name: _clean_text_field(normalized[field_name]),
            }
    return normalized


def _extract_docs(
    data: dict[str, object],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Extract normalized document records from an ADS ``response`` payload.

    Returns:
        Tuple of ``(response_metadata_dict, normalized_docs_list)``.
    """
    raw_resp = data.get("response")
    resp_dict: dict[str, object] = (
        {str(k): v for k, v in raw_resp.items()} if isinstance(raw_resp, dict) else {}
    )
    raw_docs = resp_dict.get("docs")
    docs = [
        _normalize_doc({str(k): v for k, v in item.items()})
        for item in (raw_docs if isinstance(raw_docs, list) else [])
        if isinstance(item, dict)
    ]
    return (resp_dict, docs)


def _fmt_json(payload: object) -> str:
    """Serialize ``payload`` as indented UTF-8 JSON.

    Returns:
        Indented JSON string representation.
    """
    return json.dumps(payload, indent=2, default=str)


def _read_only_annotations(title: str) -> ToolAnnotations:
    """Build standard read-only, idempotent, open-world ``ToolAnnotations``.

    Returns:
        Configured ``ToolAnnotations`` instance.
    """
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    )


def _search_ads(
    q: str,
    *,
    fl: str | None = None,
    rows: int = 10,
    sort: str = "date desc",
    start: int = 0,
) -> str:
    """Execute an ADS Solr search and return normalized JSON output.

    Returns:
        Indented JSON search results payload.
    """
    cleaned_q = _require_non_empty(q, "q")
    clamped_rows = _clamp_rows(rows)
    clamped_start = _clamp_start(start)
    data = _ads_request_json(
        "/search/query",
        params={
            "q": cleaned_q,
            "fl": fl.strip() if fl and fl.strip() else DEFAULT_FIELDS,
            "rows": str(clamped_rows),
            "sort": sort.strip() or "date desc",
            "start": str(clamped_start),
        },
    )
    resp_dict, docs = _extract_docs(data)
    return _fmt_json({
        "numFound": resp_dict.get("numFound"),
        "start": resp_dict.get("start"),
        "query": cleaned_q,
        "docs": docs,
    })


def _get_paper_ads(bibcode: str, fl: str | None = None) -> str:
    """Fetch and normalize a single ADS paper record by bibcode.

    Returns:
        Indented JSON record for the paper or ``{}`` when absent.
    """
    cleaned_bibcode = _require_non_empty(bibcode, "bibcode")
    data = _ads_request_json(
        "/search/query",
        params={
            "q": f"bibcode:{cleaned_bibcode}",
            "fl": fl.strip() if fl and fl.strip() else DEFAULT_FIELDS,
            "rows": "1",
            "sort": "date desc",
            "start": "0",
        },
    )
    _, docs = _extract_docs(data)
    return _fmt_json(docs[0] if docs else {})


def _bigquery_ads(
    bibcodes: list[str],
    *,
    fl: str | None = None,
    rows: int = 200,
) -> str:
    """Batch-fetch normalized ADS records via ``/search/bigquery``.

    Returns:
        Indented JSON payload with ``numFound`` and ``docs``.
    """
    cleaned_bibcodes = _require_bibcodes(bibcodes)
    clamped_rows = _clamp_rows(rows)
    body = ("bibcode\n" + "\n".join(cleaned_bibcodes)).encode("utf-8")
    data = _ads_request_json(
        "/search/bigquery",
        params={
            "q": "*:*",
            "fl": fl.strip() if fl and fl.strip() else DEFAULT_FIELDS,
            "rows": str(clamped_rows),
        },
        body=body,
        options=_AdsRequestOptions(method="POST", content_type="big-query/csv"),
    )
    resp_dict, docs = _extract_docs(data)
    return _fmt_json({"numFound": resp_dict.get("numFound"), "docs": docs})


def _export_refs_ads(bibcodes: list[str], fmt: str = "bibtex") -> str:
    """Export citations for ``bibcodes`` in the requested ADS export format.

    Returns:
        Formatted bibliography string.
    """
    cleaned_bibcodes = _require_bibcodes(bibcodes)
    cleaned_fmt = _require_non_empty(fmt, "format").lower()
    encoded_fmt = urllib.parse.quote(cleaned_fmt, safe="")
    data = _ads_request_json(
        f"/export/{encoded_fmt}",
        body=json.dumps({"bibcode": cleaned_bibcodes}).encode("utf-8"),
        options=_AdsRequestOptions(method="POST", content_type="application/json"),
    )
    export_val = data.get("export")
    return str(export_val) if export_val is not None else ""


def _resolve_links_ads(bibcode: str, link_type: str | None = None) -> str:
    """Resolve full-text, arXiv, DOI, or data links for a bibcode.

    Returns:
        Indented JSON resolver payload or 3xx redirect descriptor.
    """
    cleaned_bibcode = _require_non_empty(bibcode, "bibcode")
    path = f"/resolver/{urllib.parse.quote(cleaned_bibcode, safe='')}"
    if link_type is not None and link_type.strip():
        path = f"{path}/{urllib.parse.quote(link_type.strip(), safe='')}"
    return _fmt_json(_ads_request_json(path, follow_redirects=False))


def _post_bibcodes_json(
    path: str,
    bibcodes: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT,
) -> str:
    """POST ``{"bibcodes": ...}`` to an ADS JSON endpoint and format output.

    Returns:
        Indented JSON response string.
    """
    cleaned_bibcodes = _require_bibcodes(bibcodes)
    data = _ads_request_json(
        path,
        body=json.dumps({"bibcodes": cleaned_bibcodes}).encode("utf-8"),
        options=_AdsRequestOptions(
            method="POST",
            content_type="application/json",
            timeout=timeout,
        ),
    )
    return _fmt_json(data)


def _register_search_and_record_tools(app: MCPServer) -> None:
    """Register search, paper, citation, and bigquery tools on ``app``."""

    @app.tool(annotations=_read_only_annotations("Search NASA ADS Literature"))
    def search(
        q: str,
        fl: str | None = None,
        rows: int = 10,
        sort: str = "date desc",
        start: int = 0,
    ) -> str:
        """Search NASA ADS with full ADS Solr query syntax.

        Args:
            q: ADS Solr query string (e.g., ``author:"Einstein, A." year:1915``).
            fl: Comma-separated ADS fields to return (defaults to core metadata).
            rows: Maximum results per page, clamped to ``1..2000`` (default 10).
            sort: ADS sort expression (default ``"date desc"``).
            start: Zero-based pagination offset, clamped to ``>= 0`` (default 0).

        Returns:
            Indented JSON containing ``numFound``, ``start``, ``query``, and ``docs``.
        """
        return _search_ads(q, fl=fl, rows=rows, sort=sort, start=start)

    @app.tool(annotations=_read_only_annotations("Get NASA ADS Paper Record"))
    def get_paper(bibcode: str, fl: str | None = None) -> str:
        """Fetch the metadata record for a single paper by ADS bibcode.

        Args:
            bibcode: ADS bibcode (e.g., ``1974Natur.248...30H``).
            fl: Optional comma-separated list of fields to return.

        Returns:
            Indented JSON record for the matched paper, or ``{}`` if not found.
        """
        return _get_paper_ads(bibcode, fl=fl)

    @app.tool(annotations=_read_only_annotations("Get NASA ADS Paper Abstract"))
    def get_abstract(bibcode: str) -> str:
        """Fetch abstract and core bibliographic metadata for a bibcode.

        Args:
            bibcode: ADS bibcode.

        Returns:
            Indented JSON containing bibcode, title, author, year, pub, abstract,
            DOI, and citation count.
        """
        return _get_paper_ads(
            bibcode,
            fl="bibcode,title,author,year,pub,abstract,doi,citation_count",
        )

    @app.tool(annotations=_read_only_annotations("Get Paper References"))
    def get_references(bibcode: str, rows: int = 50) -> str:
        """Fetch papers cited by the given ADS bibcode.

        Args:
            bibcode: ADS bibcode whose reference list should be retrieved.
            rows: Maximum references to return, clamped to ``1..2000`` (default 50).

        Returns:
            Indented JSON search payload sorted by publication date descending.
        """
        cleaned_bibcode = _require_non_empty(bibcode, "bibcode")
        return _search_ads(
            f"references(bibcode:{cleaned_bibcode})",
            rows=rows,
            sort="date desc",
        )

    @app.tool(annotations=_read_only_annotations("Get Paper Citations"))
    def get_citations(bibcode: str, rows: int = 50) -> str:
        """Fetch papers citing the given ADS bibcode, sorted by citation count.

        Args:
            bibcode: ADS bibcode whose citing papers should be retrieved.
            rows: Maximum citing papers to return, clamped to ``1..2000`` (default 50).

        Returns:
            Indented JSON search payload sorted by citation count descending.
        """
        cleaned_bibcode = _require_non_empty(bibcode, "bibcode")
        return _search_ads(
            f"citations(bibcode:{cleaned_bibcode})",
            rows=rows,
            sort="citation_count desc",
        )

    @app.tool(annotations=_read_only_annotations("Batch Fetch ADS Records"))
    def bigquery(
        bibcodes: list[str],
        fl: str | None = None,
        rows: int = 200,
    ) -> str:
        """Batch-fetch records for up to 2000 bibcodes in one ADS bigquery request.

        Args:
            bibcodes: List of ADS bibcodes to retrieve.
            fl: Optional comma-separated list of fields to return.
            rows: Maximum records to return, clamped to ``1..2000`` (default 200).

        Returns:
            Indented JSON containing ``numFound`` and normalized ``docs``.
        """
        return _bigquery_ads(bibcodes, fl=fl, rows=rows)


def _register_export_and_analysis_tools(app: MCPServer) -> None:
    """Register metrics, citation export, resolver, and network tools on ``app``."""

    @app.tool(annotations=_read_only_annotations("Compute ADS Citation Metrics"))
    def metrics(bibcodes: list[str]) -> str:
        """Compute ADS citation metrics (h-index, reads, tori, i10) for bibcodes.

        Args:
            bibcodes: List of ADS bibcodes to analyze.

        Returns:
            Indented JSON metrics report from ``/metrics``.
        """
        return _post_bibcodes_json("/metrics", bibcodes)

    @app.tool(annotations=_read_only_annotations("Export ADS BibTeX Entries"))
    def export_bibtex(bibcodes: list[str]) -> str:
        """Export BibTeX entries for the supplied ADS bibcodes.

        Args:
            bibcodes: List of ADS bibcodes to export.

        Returns:
            Raw BibTeX text string.
        """
        return _export_refs_ads(bibcodes, fmt="bibtex")

    @app.tool(annotations=_read_only_annotations("Export ADS Formatted Citations"))
    def export_refs(bibcodes: list[str], format: str = "bibtex") -> str:
        """Export citations for ``bibcodes`` in any supported ADS format.

        Args:
            bibcodes: List of ADS bibcodes to export.
            format: ADS export format (e.g., ``bibtex``, ``bibtexabs``, ``ads``,
                ``ris``, ``endnote``, ``aastex``, ``mnras``).

        Returns:
            Formatted bibliography string.
        """
        return _export_refs_ads(bibcodes, fmt=format)

    @app.tool(annotations=_read_only_annotations("Resolve ADS Paper Links"))
    def resolve_links(bibcode: str, link_type: str | None = None) -> str:
        """Resolve full-text, arXiv, DOI, or data product links for a bibcode.

        Args:
            bibcode: Target ADS bibcode.
            link_type: Optional resolver link type (e.g., ``esource``,
                ``eprint_html``, ``data``, ``associated``).

        Returns:
            Indented JSON resolver payload or 3xx redirect status and ``location``.
        """
        return _resolve_links_ads(bibcode, link_type=link_type)

    @app.tool(annotations=_read_only_annotations("Build ADS Coauthor Network"))
    def author_network(bibcodes: list[str]) -> str:
        """Build a coauthor network graph for a collection of ADS bibcodes.

        Args:
            bibcodes: List of ADS bibcodes to include in the network.

        Returns:
            Indented JSON coauthor network graph from ``/vis/author-network``.
        """
        return _post_bibcodes_json("/vis/author-network", bibcodes, timeout=VIS_TIMEOUT)

    @app.tool(annotations=_read_only_annotations("Build ADS Paper Network"))
    def paper_network(bibcodes: list[str]) -> str:
        """Build a citation/reference network graph for a collection of ADS bibcodes.

        Args:
            bibcodes: List of ADS bibcodes to include in the network.

        Returns:
            Indented JSON paper network graph from ``/vis/paper-network``.
        """
        return _post_bibcodes_json("/vis/paper-network", bibcodes, timeout=VIS_TIMEOUT)


def _register_resources_and_prompts(app: MCPServer) -> None:
    """Register the ``ads://query/{encoded_q}`` resource and 3 prompts on ``app``."""

    @app.resource("ads://query/{encoded_q}")
    def query_resource(encoded_q: str) -> str:
        """Attach a URL-encoded NASA ADS search query as an MCP resource.

        Args:
            encoded_q: Percent-encoded ADS Solr query string.

        Returns:
            Indented JSON search results for up to 25 matching records.
        """
        return _search_ads(urllib.parse.unquote(encoded_q), rows=RESOURCE_DEFAULT_ROWS)

    @app.prompt()
    def lit_review(topic: str, years: str = "2015-") -> str:
        """Draft a structured NASA ADS literature review prompt on a topic.

        Args:
            topic: Research topic or search phrase.
            years: ADS year range filter (default ``"2015-"``).

        Returns:
            Prompt text instructing the assistant how to run the ADS review.
        """
        return (
            f"Run a NASA ADS literature review on '{topic}' restricted to year:{years}.\n"
            "  1. `search` with a focused query — include `property:refereed` and sort by "
            "`citation_count desc`. Ask for rows=25.\n"
            "  2. Pick the top ~10 bibcodes and pass them to `bigquery` to pull abstracts.\n"
            "  3. Cluster the results by theme. For each cluster, cite 2-3 bibcodes and "
            "summarize what they collectively established.\n"
            "  4. End with open problems — papers from the last 2 years whose abstracts "
            "explicitly flag unresolved questions."
        )

    @app.prompt()
    def citation_chase(bibcode: str, depth: int = 1) -> str:
        """Draft a prompt to walk the citation graph outward from a seed paper.

        Args:
            bibcode: Seed ADS bibcode.
            depth: Citation traversal depth (default 1).

        Returns:
            Prompt text guiding reference and citation exploration.
        """
        return (
            f"Starting from {bibcode}, chase the citation graph to depth {depth}.\n"
            "  1. `get_abstract` the seed so we know what it's about.\n"
            "  2. `get_references` (what it builds on) and `get_citations` "
            "(what built on it), sorted by citation_count.\n"
            "  3. Keep the top 5 of each that look thematically closest — briefly "
            "justify each pick.\n"
            f"  4. If depth > 1, recurse on each kept bibcode up to depth {depth}.\n"
            "  5. Report a small bulleted tree with bibcode, 1-line summary, and why "
            "it matters for the seed paper."
        )

    @app.prompt()
    def bib_export(query: str, n: int = 10, format: str = "bibtex") -> str:
        """Draft a prompt that exports top ADS search hits into a bibliography.

        Args:
            query: ADS Solr search query.
            n: Number of top refereed results to export (default 10).
            format: ADS export format (default ``"bibtex"``).

        Returns:
            Prompt text instructing the assistant to export formatted references.
        """
        return (
            f"Search ADS for '{query}', take the top {n} refereed results sorted by "
            f"citation_count, then call `export_refs` with format='{format}' on those "
            "bibcodes. Return the exported string verbatim in a fenced block so I "
            "can paste it into my .bib file."
        )


def create_nasa_ads_mcp_server(server_name: str = "nasa-ads") -> MCPServer:
    """Create and configure the standalone NASA ADS ``MCPServer`` instance.

    Args:
        server_name: Identifier advertised in MCP ``serverInfo.name``.

    Returns:
        Configured ``MCPServer`` with 12 tools, 1 resource, and 3 prompts.
    """
    app = MCPServer(
        name=server_name,
        version="1.0.0",
        instructions=SERVER_INSTRUCTIONS,
    )
    _register_search_and_record_tools(app)
    _register_export_and_analysis_tools(app)
    _register_resources_and_prompts(app)
    return app


def main(argv: list[str] | None = None) -> None:
    """Run the NASA ADS MCP server over standard I/O (``stdio``).

    All diagnostics are routed strictly to ``sys.stderr`` to preserve JSON-RPC
    frames on ``sys.stdout``.

    Args:
        argv: Optional CLI argument list (defaults to ``sys.argv[1:]``).
    """
    parser = argparse.ArgumentParser(
        prog="nasa_ads_mcp_server",
        description="Standalone NASA Astrophysics Data System (ADS) MCP Server",
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

    app = create_nasa_ads_mcp_server()
    logger.info("Starting NASA ADS MCP Server over stdio transport")
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
