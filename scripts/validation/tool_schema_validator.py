"""Validator for tool schemas and parameter definitions."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.validation.codes import ErrorCode
from scripts.validation.models import Severity


if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from scripts.validation.models import ValidationReport


VALID_JSON_SCHEMA_TYPES = frozenset({'string', 'integer', 'number', 'boolean', 'array', 'object', 'null'})


def validate_tool_parameter_schema(
    schema: Mapping[str, object],
    tool_name: str,
    report: ValidationReport,
    path: Path | str,
) -> None:
    """Validate a tool input/parameters schema object.

    Args:
        schema: JSON Schema dictionary for tool parameters.
        tool_name: Name of tool being validated.
        report: Aggregating ValidationReport.
        path: Path to the schema or defining file.
    """
    properties = schema.get('properties')
    required = schema.get('required')

    props_dict: dict[str, object] = {}
    if properties is not None:
        if not isinstance(properties, dict):
            report.add(
                code=ErrorCode.TLS001,
                message=f"Tool '{tool_name}' schema 'properties' must be a JSON object mapping property names to specs.",
                severity=Severity.ERROR,
                path=path,
            )
        else:
            props_dict = properties

    for prop_name, prop_spec in props_dict.items():
        if not isinstance(prop_spec, dict):
            report.add(
                code=ErrorCode.TLS001,
                message=f"Property '{prop_name}' in tool '{tool_name}' must be a JSON object specification.",
                severity=Severity.ERROR,
                path=path,
            )
            continue

        prop_type = prop_spec.get('type')
        if prop_type is None:
            report.add(
                code=ErrorCode.TLS001,
                message=f"Parameter '{prop_name}' in tool '{tool_name}' is missing required JSON Schema 'type'.",
                severity=Severity.ERROR,
                path=path,
                suggestion=f"Add 'type' (e.g. 'string', 'integer', 'boolean') to parameter '{prop_name}'.",
            )
        elif isinstance(prop_type, str):
            if prop_type not in VALID_JSON_SCHEMA_TYPES:
                report.add(
                    code=ErrorCode.TLS001,
                    message=(f"Parameter '{prop_name}' in tool '{tool_name}' has invalid type '{prop_type}'. Valid types are: {', '.join(sorted(VALID_JSON_SCHEMA_TYPES))}"),
                    severity=Severity.ERROR,
                    path=path,
                )
        elif isinstance(prop_type, list):
            for t in prop_type:
                if not isinstance(t, str) or t not in VALID_JSON_SCHEMA_TYPES:
                    report.add(
                        code=ErrorCode.TLS001,
                        message=f"Parameter '{prop_name}' in tool '{tool_name}' has invalid union type '{t}'.",
                        severity=Severity.ERROR,
                        path=path,
                    )
        else:
            report.add(
                code=ErrorCode.TLS001,
                message=f"Parameter '{prop_name}' in tool '{tool_name}' has non-string 'type' field.",
                severity=Severity.ERROR,
                path=path,
            )

    # Check TLS002: required items present in properties
    if required is not None:
        if not isinstance(required, list):
            report.add(
                code=ErrorCode.TLS002,
                message=f"Tool '{tool_name}' 'required' must be a list of property names.",
                severity=Severity.ERROR,
                path=path,
            )
        else:
            for req_item in required:
                if not isinstance(req_item, str) or req_item not in props_dict:
                    report.add(
                        code=ErrorCode.TLS002,
                        message=(f"Required property '{req_item}' in tool '{tool_name}' is not declared in 'properties'."),
                        severity=Severity.ERROR,
                        path=path,
                        suggestion=f"Define '{req_item}' under 'properties' or remove it from 'required'.",
                    )


def validate_tool_schemas(
    repo_root: Path,
    report: ValidationReport,
) -> None:
    """Scan and validate any standalone tool schema files in repository.

    Args:
        repo_root: Root path of repository.
        report: Aggregating ValidationReport.
    """
    # Check any schema files in resources/ or schemas/
    for schema_dir_name in ('schemas', 'resources/schemas'):
        schema_dir = repo_root / schema_dir_name
        if schema_dir.is_dir():
            for schema_file in schema_dir.glob('**/*.json'):
                try:
                    content = schema_file.read_text(encoding='utf-8')
                    data = json.loads(content)
                    if isinstance(data, dict):
                        tool_name = schema_file.stem
                        validate_tool_parameter_schema(data, tool_name, report, schema_file)
                except OSError, json.JSONDecodeError:
                    pass
