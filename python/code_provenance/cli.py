import argparse
import sys
from pathlib import Path
from code_provenance.compose_parser import parse_compose, parse_image_ref
from code_provenance.resolver import resolve_image
from code_provenance.output import format_json, format_table


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="code-provenance",
        description="Resolve Docker images to their source code commits on GitHub.",
    )
    parser.add_argument(
        "compose_file",
        nargs="?",
        default="docker-compose.yml",
        help="Path to docker-compose file (default: docker-compose.yml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show resolution steps",
    )

    args = parser.parse_args(argv)

    compose_path = Path(args.compose_file)
    if not compose_path.exists():
        print(f"Error: {compose_path} not found", file=sys.stderr)
        return 1

    yaml_content = compose_path.read_text()
    services = parse_compose(yaml_content)

    if not services:
        print("No services with images found.", file=sys.stderr)
        return 0

    results = []
    for service_name, image_string in services:
        ref = parse_image_ref(image_string)
        result = resolve_image(service_name, ref)
        results.append(result)

    if args.verbose:
        for result in results:
            print(f"\nResolving {result.image} ...", file=sys.stderr)
            for step in result.steps:
                print(f"  {step}", file=sys.stderr)
            print(f"  → {result.status}" + (f" ({result.resolution_method}, {result.confidence})" if result.status == "resolved" else ""), file=sys.stderr)
        print(file=sys.stderr)

    if args.json_output:
        print(format_json(results))
    else:
        print(format_table(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
