# code-provenance

Resolve Docker images in a docker-compose file to their exact source code commits on GitHub.

Available as both a [Python package](./python/) and a [Node.js package](./node/).

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

## CLI Flags

| Flag | Description |
|------|-------------|
| `--json` | Output results as JSON |
| `--verbose`, `-v` | Show the resolution steps for each image |

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

## Language Implementations

- **Python** -- see [python/README.md](./python/README.md) for installation and API details
- **Node.js** -- see [node/README.md](./node/README.md) for installation and API details

## License

MIT
