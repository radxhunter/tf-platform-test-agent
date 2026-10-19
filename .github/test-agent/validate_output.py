#!/usr/bin/env python3
"""Validate the agent's final JSON against output.schema.json.

Usage: validate_output.py <schema.json> <document.json>

Supports the subset of JSON Schema the output schema uses: type, enum,
required, properties, additionalProperties: false, items, maxItems,
maxLength, pattern and minimum. Dependency-free on purpose: the runner's
system Python does not allow installing packages, and this check must not
depend on anything the pull request can influence.

Exit code 0 when valid, 1 with one line per problem otherwise.
"""
import json
import re
import sys

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "boolean": bool,
}


def validate(schema, value, path, errors):
    expected = schema.get("type")
    if expected:
        py_type = TYPES[expected]
        ok = isinstance(value, py_type) and not (expected == "integer" and isinstance(value, bool))
        if not ok:
            errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']}")
    if isinstance(value, str):
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']} characters")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, int) and "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: below {schema['minimum']}")
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        for i, item in enumerate(value):
            validate(schema.get("items", {}), item, f"{path}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required '{key}'")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}: unexpected property '{key}'")
        for key, sub in props.items():
            if key in value:
                validate(sub, value[key], f"{path}.{key}", errors)


def main(argv):
    schema = json.load(open(argv[1], encoding="utf-8"))
    document = json.load(open(argv[2], encoding="utf-8"))
    errors = []
    validate(schema, document, "$", errors)
    for e in errors[:50]:
        print(e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
