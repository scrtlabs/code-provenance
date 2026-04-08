import argparse
import os
import sys
from pathlib import Path
from code_provenance.compose_parser import parse_compose, parse_image_ref
from code_provenance.resolver import resolve_image
from code_provenance.output import format_json, format_text


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
        "--image",
        help="Resolve a single image reference instead of a compose file",
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

    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "Warning: GITHUB_TOKEN is not set. Some resolution methods (digest, :latest) will not work.\n"
            "Set it with: export GITHUB_TOKEN=ghp_your_token_here\n"
            "Create a token at https://github.com/settings/tokens with read:packages scope.\n",
            file=sys.stderr,
        )

    if args.image:
        # Single image mode
        ref = parse_image_ref(args.image)
        results = [resolve_image("image", ref)]
    else:
        # Compose file mode
        compose_path = Path(args.compose_file)
        if not compose_path.exists():
            print(f"Error: {compose_path} not found", file=sys.stderr)
            return 1

        yaml_content = compose_path.read_text()

        try:
            services = parse_compose(yaml_content)
        except Exception as e:
            print(f"Error: failed to parse {compose_path} — {e}", file=sys.stderr)
            return 1

        if not services:
            print("No services with images found. Is this a valid docker-compose file?", file=sys.stderr)
            return 1

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
        print(format_text(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
