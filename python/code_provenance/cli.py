import argparse
import html
import os
import re
import sys
from pathlib import Path
import requests
from code_provenance.compose_parser import parse_compose, parse_image_ref
from code_provenance.resolver import resolve_image
from code_provenance.output import format_json, format_text


def _extract_yaml_from_html(text: str) -> str:
    """Extract YAML content from HTML-wrapped SecretVM response."""
    match = re.search(r"<pre[^>]*>(.*)</pre>", text, re.DOTALL)
    if match:
        text = match.group(1)
    return html.unescape(text).strip().strip("\u200b").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="code-provenance",
        description="Resolve Docker images to their source code commits on GitHub.",
        epilog="environment:\n"
               "  GITHUB_TOKEN       GitHub personal access token (recommended). Enables\n"
               "                     digest and :latest resolution, and raises API rate\n"
               "                     limit to 5000/hr. Create one at\n"
               "                     https://github.com/settings/tokens with read:packages\n"
               "                     scope. Set with: export GITHUB_TOKEN=ghp_...",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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
        "--secretvm",
        metavar="URL",
        help="Fetch docker-compose from a SecretVM at URL (port 29343)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.13",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show resolution steps",
    )

    args = parser.parse_args(argv)

    # Show help if no mode specified
    if not args.image and not args.secretvm and args.compose_file == "docker-compose.yml" and not os.path.exists("docker-compose.yml"):
        parser.print_help()
        return 0

    if not os.environ.get("GITHUB_TOKEN"):
        # Try to auto-detect from gh CLI
        try:
            import subprocess
            result = subprocess.run(
                ["gh", "auth", "token"], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                os.environ["GITHUB_TOKEN"] = result.stdout.strip()
                print("Using GITHUB_TOKEN from gh CLI.", file=sys.stderr)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    if not os.environ.get("GITHUB_TOKEN"):
        print(
            "Warning: GITHUB_TOKEN is not set. Some resolution methods (digest, :latest) will not work.\n"
            "Set it with: export GITHUB_TOKEN=ghp_your_token_here\n"
            "Or install gh CLI and run: gh auth login\n",
            file=sys.stderr,
        )

    if args.secretvm:
        # SecretVM mode — fetch docker-compose from the VM
        url = args.secretvm.rstrip("/")
        if not url.startswith("http://") and not url.startswith("https://"):
            url = f"https://{url}"
        compose_url = f"{url}:29343/docker-compose"
        print(f"Fetching docker-compose from {compose_url} ...", file=sys.stderr)
        try:
            resp = requests.get(compose_url, timeout=15, verify=False)
            resp.raise_for_status()
            yaml_content = _extract_yaml_from_html(resp.text)
        except requests.RequestException as e:
            print(f"Error: failed to fetch docker-compose from {compose_url} — {e}", file=sys.stderr)
            return 1

        try:
            services = parse_compose(yaml_content)
        except Exception as e:
            print(f"Error: failed to parse docker-compose from {compose_url} — {e}", file=sys.stderr)
            return 1

        if not services:
            print("No services with images found in the SecretVM docker-compose.", file=sys.stderr)
            return 1

        results = []
        for service_name, image_string in services:
            ref = parse_image_ref(image_string)
            result = resolve_image(service_name, ref)
            results.append(result)

    elif args.image:
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
