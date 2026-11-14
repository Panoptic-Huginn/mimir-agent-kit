#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""Canonical PEP 723 standalone Python 3.14+/3.15 script template.

Demonstrates universal 3.14+ baselines alongside 3.15-friendly lazy loading:
- Native deferred annotations (PEP 649/749) with zero ``from __future__`` imports
- PEP 695/696 generic classes with type-parameter defaults
- PEP 750 template strings (``t"..."``) for injection-safe structured rendering
- PEP 784 ``compression.zstd`` standard-library round-trip compression
- ``ReadOnly`` ``TypedDict`` (PEP 705) and ``TypeIs`` (PEP 742) narrowing
- ``@dataclass(slots=True, frozen=True, kw_only=True)`` and UTC timestamps
"""

import annotationlib
import argparse
import datetime
import json
import sys
from compression import zstd
from dataclasses import dataclass
from pathlib import Path
from string.templatelib import Interpolation, Template
from typing import ReadOnly, TypedDict, TypeIs


# Under Python 3.15+, `lazy import <pkg>` defers module evaluation cleanly;
# declaring __lazy_modules__ supports deferred optimization on both 3.14 and 3.15.
__lazy_modules__ = ["json", "pathlib"]


class AuditEvent(TypedDict):
    """Immutable audit record schema typed via PEP 705 ReadOnly fields."""

    event_id: ReadOnly[str]
    recorded_utc: ReadOnly[str]
    bytes_compressed: ReadOnly[int]


@dataclass(slots=True, frozen=True, kw_only=True)
class SampleBuffer[T: (str, bytes) = bytes]:
    """Typed immutable ring-buffer sample using PEP 695/696 defaults."""

    label: str
    payload: T
    next_link: SampleBuffer[T] | None = None


def is_nonempty_text(value: object) -> TypeIs[str]:
    """Narrow arbitrary values to non-empty strings via PEP 742 TypeIs.

    Returns:
        ``True`` when ``value`` is a non-blank string.
    """
    return isinstance(value, str) and bool(value.strip())


def format_safe_log_template(template: Template) -> tuple[str, list[str]]:
    """Render a PEP 750 ``t"..."`` template into an escaped message and bindings.

    Args:
        template: PEP 750 template literal instance.

    Returns:
        Tuple of structured log format string and sanitized field values.
    """
    fragments: list[str] = []
    values: list[str] = []
    for part in template:
        if isinstance(part, Interpolation):
            clean = repr(part.value).replace("\n", "\\n")
            fragments.append("{}")
            values.append(clean)
        else:
            fragments.append(part)
    return "".join(fragments), values


def compress_and_verify(payload: bytes) -> bytes:
    """Compress and verify bytes with Python 3.14+ ``compression.zstd``.

    Args:
        payload: Raw UTF-8 or binary payload.

    Returns:
        Original uncompressed bytes after verified round-trip.

    Raises:
        ValueError: If round-trip verification fails.
    """
    compressed = zstd.compress(payload, level=3)
    restored = zstd.decompress(compressed)
    if restored != payload:
        raise ValueError("Zstandard round-trip integrity check failed")
    return restored


def run_self_test() -> AuditEvent:
    """Execute self-verification across PEP 649/695/705/742/750/784 features.

    Returns:
        Populated immutable ``AuditEvent`` dictionary.

    Raises:
        RuntimeError: If annotation metadata or compression verification fails.
        ValueError: If sample validation rejects an empty identifier.
    """
    annots = annotationlib.get_annotations(
        SampleBuffer, format=annotationlib.Format.FORWARDREF
    )
    if "next_link" not in annots:
        raise RuntimeError("Expected PEP 649 deferred annotation 'next_link'")

    sample = SampleBuffer[bytes](label="telemetry-01", payload=b"sensor-ok")
    if not is_nonempty_text(sample.label):
        raise ValueError("SampleBuffer label must be a non-empty string")

    msg, bound = format_safe_log_template(t"Telemetry frame source={sample.label}")
    encoded = json.dumps({"msg": msg, "bound": bound}).encode("utf-8")
    compressed = zstd.compress(encoded, level=3)
    if compress_and_verify(encoded) != encoded:
        raise RuntimeError("Unexpected round-trip mismatch")

    return AuditEvent(
        event_id=sample.label,
        recorded_utc=datetime.datetime.now(datetime.UTC).isoformat(),
        bytes_compressed=len(compressed),
    )


def main(argv: list[str] | None = None) -> int:
    """Run CLI entrypoint for the PEP 723 template script.

    Args:
        argv: Optional argument list overriding ``sys.argv[1:]``.

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(description="PEP 723 modern Python template")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in Python 3.14+/3.15 feature verification and print JSON summary.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional UTF-8 JSON output path.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        record = run_self_test()
        rendered = json.dumps(record, indent=2) + "\n"
        if args.output is not None:
            args.output.write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
