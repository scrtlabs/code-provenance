#!/usr/bin/env python3
"""Resolve a single Docker image to its source code commit.

Usage:
    python check_image.py ghcr.io/scrtlabs/siyuan@sha256:dd399fbc...
    python check_image.py traefik:v2.10
    python check_image.py mariadb:10.11
"""
import sys
import os

# Add the python package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "python"))

from code_provenance.compose_parser import parse_image_ref
from code_provenance.resolver import resolve_image
from code_provenance.output import format_text, format_json


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python check_image.py <image> [--json] [--verbose]")
        print("Example: python check_image.py traefik:v2.10")
        return 0

    args = sys.argv[1:]
    json_output = "--json" in args
    verbose = "--verbose" in args or "-v" in args
    image = [a for a in args if not a.startswith("-")][0]

    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "Warning: GITHUB_TOKEN not set. Some resolution methods will not work.\n",
            file=sys.stderr,
        )

    ref = parse_image_ref(image)
    result = resolve_image("image", ref)

    if verbose:
        print(f"Resolving {image} ...", file=sys.stderr)
        for step in result.steps:
            print(f"  {step}", file=sys.stderr)
        status_line = f"  → {result.status}"
        if result.status == "resolved":
            status_line += f" ({result.resolution_method}, {result.confidence})"
        print(status_line, file=sys.stderr)
        print(file=sys.stderr)

    if json_output:
        print(format_json([result]))
    else:
        print(format_text([result]))

    return 0 if result.status == "resolved" else 1


if __name__ == "__main__":
    sys.exit(main())
