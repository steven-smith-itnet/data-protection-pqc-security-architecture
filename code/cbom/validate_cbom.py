#!/usr/bin/env python3
"""Validate CBOM files against the official CycloneDX 1.6 JSON schema.

The schema files are not vendored. Download them once:

    mkdir -p code/.schemas && cd code/.schemas
    for f in bom-1.6.schema.json spdx.schema.json jsf-0.82.schema.json; do
      curl -sfLO https://raw.githubusercontent.com/CycloneDX/specification/master/schema/$f
    done

Then:

    python cbom/validate_cbom.py --schema-dir .schemas cbom/sample-output/*.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from jsonschema import Draft7Validator
from referencing import Registry, Resource


def build_validator(schema_dir: str) -> Draft7Validator:
    def load(name):
        with open(os.path.join(schema_dir, name), encoding="utf-8") as fh:
            return json.load(fh)

    registry = Registry()
    for name in ("spdx.schema.json", "jsf-0.82.schema.json"):
        schema = load(name)
        res = Resource.from_contents(schema)
        registry = registry.with_resource(name, res).with_resource(schema.get("$id", name), res)
        registry = registry.with_resource("http://cyclonedx.org/schema/" + name, res)
    return Draft7Validator(load("bom-1.6.schema.json"), registry=registry)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--schema-dir", required=True)
    ap.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    validator = build_validator(args.schema_dir)
    rc = 0
    for path in args.files:
        with open(path, encoding="utf-8") as fh:
            errors = sorted(validator.iter_errors(json.load(fh)), key=lambda e: list(e.path))
        status = "VALID" if not errors else f"{len(errors)} error(s)"
        print(f"{os.path.basename(path)}: {status} against CycloneDX bom-1.6.schema.json")
        for e in errors[:10]:
            print(f"    {list(e.path)}: {e.message[:200]}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
