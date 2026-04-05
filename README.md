# code-provenance

Resolve Docker images in a docker-compose file to their exact source code commits on GitHub.

Available as both a [Python package](https://pypi.org/project/code-provenance/) and a [Node.js package](https://www.npmjs.com/package/code-provenance).

## Installation

**Node.js:**

```bash
npm install -g code-provenance
```

**Python:**

```bash
pip install code-provenance
```

## Quick Example

Given a `docker-compose.yml`:

```yaml
version: "3"
services:
  web:
    image: traefik:v3.6.0
```

Run:

```bash
code-provenance docker-compose.yml
```

Output:

```
┌─────────┬────────────────┬────────────────────────────┬──────────────┬──────────┬────────────┐
│ SERVICE │ IMAGE          │ REPO                       │ COMMIT       │ STATUS   │ CONFIDENCE │
├─────────┼────────────────┼────────────────────────────┼──────────────┼──────────┼────────────┤
│ web     │ traefik:v3.6.0 │ github.com/traefik/traefik │ 06db5168c0d9 │ resolved │ exact      │
└─────────┴────────────────┴────────────────────────────┴──────────────┴──────────┴────────────┘
```

## How It Works

The tool resolves each Docker image through a chain of strategies, stopping at the first success:

1. **OCI labels** -- reads `org.opencontainers.image.source` and `org.opencontainers.image.revision` from the image manifest
2. **Repo inference** -- maps the image registry/namespace to a GitHub repository (GHCR namespaces map directly; Docker Hub images are resolved via the Hub API)
3. **Tag matching** -- matches the Docker tag against git tags in the inferred repository
4. **Packages API** -- for GHCR images, queries the GitHub Packages API to resolve digests or `:latest` tags
5. **Latest release / commit** -- for `:latest` tags, falls back to the most recent GitHub release or the HEAD commit on the default branch

## Confidence Levels

- **exact** -- the commit is definitively tied to the image (e.g., OCI revision label with a versioned tag, or an exact git tag match)
- **approximate** -- the commit is a best-effort match (e.g., `:latest` tag, prefix tag match, or latest release fallback)

## CLI Usage

```bash
code-provenance [compose-file] [--json] [--verbose]
```

| Argument | Description |
|----------|-------------|
| `compose-file` | Path to docker-compose file (default: `docker-compose.yml`) |
| `--json` | Output results as JSON |
| `--verbose`, `-v` | Show the resolution steps for each image |

### Examples

```bash
# Table output (default)
code-provenance docker-compose.yml

# JSON output
code-provenance docker-compose.yml --json

# Show resolution steps
code-provenance docker-compose.yml --verbose

# Combine flags
code-provenance docker-compose.yml --json --verbose
```

## Authentication

The tool works without authentication for basic resolution (OCI labels, tag matching). However, a `GITHUB_TOKEN` is **required** for:

- Resolving digest-only images (e.g., `image@sha256:...`) via the GitHub Packages API
- Resolving `:latest` tags on GHCR images via the Packages API
- Higher GitHub API rate limits (5000/hr vs 60/hr unauthenticated)

### Setup

**Option 1 — Use the `gh` CLI (recommended):** If you have the [GitHub CLI](https://cli.github.com/) installed and authenticated, `run.sh` auto-detects the token. Make sure your token has `read:packages` scope:

```bash
gh auth refresh -h github.com -s read:packages
```

**Option 2 — Set the environment variable directly:**

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

Create a classic token at https://github.com/settings/tokens with `read:packages` scope.

## Library Usage

Both packages export the same API for programmatic use.

**Node.js:**

```typescript
import { parseCompose, parseImageRef, resolveImage } from "code-provenance";
import { readFileSync } from "fs";

const yaml = readFileSync("docker-compose.yml", "utf-8");
for (const [service, image] of parseCompose(yaml)) {
  const ref = parseImageRef(image);
  const result = await resolveImage(service, ref);
  console.log(`${result.service}: ${result.commit} (${result.confidence})`);
}
```

**Python:**

```python
from code_provenance.compose_parser import parse_compose, parse_image_ref
from code_provenance.resolver import resolve_image

yaml_content = open("docker-compose.yml").read()
for service, image in parse_compose(yaml_content):
    ref = parse_image_ref(image)
    result = resolve_image(service, ref)
    print(f"{result.service}: {result.commit} ({result.confidence})")
```

See [python/README.md](./python/README.md) and [node/README.md](./node/README.md) for full API reference.

## License

MIT
