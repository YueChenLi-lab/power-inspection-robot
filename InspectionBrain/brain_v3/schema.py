"""Fail-closed validator for the exact JSON Schema vocabulary used by this contract.

No package installation needed. The checked-in schema is also consumable by
Draft202012Validator. Unsupported schema vocabulary fails rather than being ignored.
"""
import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("semantic-v3.schema.json")
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def schema_errors(value, schema=SCHEMA):
    errors = []
    types = {"object": lambda v: isinstance(v, dict), "array": lambda v: isinstance(v, list),
             "string": lambda v: isinstance(v, str), "boolean": lambda v: type(v) is bool,
             "integer": lambda v: type(v) is int, "null": lambda v: v is None}
    supported = {"$schema", "$id", "title", "description", "$defs", "$ref", "type", "const", "enum",
                 "properties", "required", "additionalProperties", "items", "minItems", "maxItems",
                 "minLength", "maxLength", "minimum", "maximum", "uniqueItems"}

    def walk(v, s, path):
        unknown = set(s) - supported
        if unknown:
            errors.append(f"{path}:unsupported_schema_keyword:{','.join(sorted(unknown))}")
            return
        if "$ref" in s:
            ref = s["$ref"]
            if not ref.startswith("#/$defs/"):
                errors.append(path + ":unsupported_reference")
                return
            walk(v, schema["$defs"][ref.split("/")[-1]], path)
            return
        expected = s.get("type")
        if expected and not any(types[t](v) for t in (expected if isinstance(expected, list) else [expected])):
            errors.append(path + ":type")
            return
        # Boolean false must not match numeric zero (Python's equality differs from JSON).
        if "const" in s and (v != s["const"] or type(v) is not type(s["const"])):
            errors.append(path + ":const")
        if "enum" in s and not any(v == x and type(v) is type(x) for x in s["enum"]):
            errors.append(path + ":enum")
        if isinstance(v, dict):
            for key in s.get("required", []):
                if key not in v:
                    errors.append(path + "." + key + ":required")
            props = s.get("properties", {})
            if s.get("additionalProperties") is False:
                for key in v.keys() - props.keys():
                    errors.append(path + "." + key + ":unexpected_field")
            for key in v.keys() & props.keys():
                walk(v[key], props[key], path + "." + key)
        if isinstance(v, list):
            if not s.get("minItems", 0) <= len(v) <= s.get("maxItems", 10**6):
                errors.append(path + ":array_length")
            if s.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in v}) != len(v):
                errors.append(path + ":duplicate_items")
            for i, item in enumerate(v):
                walk(item, s.get("items", {}), f"{path}[{i}]")
        if isinstance(v, str) and not s.get("minLength", 0) <= len(v) <= s.get("maxLength", 10**6):
            errors.append(path + ":string_length")
        if type(v) is int and not s.get("minimum", -10**9) <= v <= s.get("maximum", 10**9):
            errors.append(path + ":integer_bounds")
    walk(value, schema, "$")
    return sorted(errors)
