# Code Provenance — Design Spec

## Overview

A Python CLI tool that reads a docker-compose file, identifies all Docker images, and resolves each to the exact source code commit on GitHub from which it was built.

## CLI Interface

```
code-provenance [docker-compose.yml] [--json]
./run.sh [docker-compose.yml] [--json]
```

- Default input: `docker-compose.yml` in the current directory
- Default output: formatted table
- `--json`: outputs JSON array to stdout

## Input & Parsing

Parse the docker-compose YAML and extract all `image:` fields from services. Normalize each into:

- **registry**: `ghcr.io`, `docker.io`, etc. (bare image names like `postgres:16` default to `docker.io`)
- **namespace/name**: e.g., `acme-org/excalidraw`, `library/postgres`
- **tag**: e.g., `v3.4.12`, `latest`, or a digest. If omitted, defaults to `latest`.

## Resolution Chain

For each image, run through these strategies in order, stopping at the first success:

### Step 1 — OCI Labels Check

Fetch the image config blob from the registry via HTTP (no Docker daemon needed):

1. Get an anonymous auth token from the registry's token endpoint
2. Fetch the manifest to get the config blob digest
3. Fetch the config blob and read labels

If `org.opencontainers.image.revision` (commit SHA) and `org.opencontainers.image.source` (repo URL) both exist, resolution is complete.

### Step 2 — Repo Inference

If no OCI labels provide the source repo, infer it:

- **ghcr.io**: image path maps directly to GitHub repo (`ghcr.io/owner/repo` -> `github.com/owner/repo`)
- **Docker Hub**: query the Docker Hub API (`https://hub.docker.com/v2/repositories/{namespace}/{name}`) for source repo URL or description links

### Step 3 — Tag-to-Commit Resolution

Once the GitHub repo is known, resolve the image tag to a commit:

1. Fetch git tags via GitHub API (`GET /repos/{owner}/{repo}/tags`)
2. Match the image tag to a git tag (exact match, with and without `v` prefix)
3. If matched, return the commit SHA from the tag
4. If the image tag itself is a 40+ hex character string, treat it as a commit SHA directly

## Output

### Table (default)

```
SERVICE     IMAGE                                     REPO                                 COMMIT       STATUS
web         ghcr.io/acme-org/excalidraw:v3.4.12     github.com/acme-org/excalidraw      0f769068b3f1 resolved
db          postgres:16.2                              github.com/docker-library/postgres    a1b2c3d4e5f6 resolved
cache       redis:7.2                                  github.com/redis/redis                -            tag_not_matched
```

### JSON (`--json`)

```json
[
  {
    "service": "web",
    "image": "ghcr.io/acme-org/excalidraw:v3.4.12",
    "registry": "ghcr.io",
    "repo": "https://github.com/acme-org/excalidraw",
    "tag": "v3.4.12",
    "commit": "0f769068b3f1...",
    "commit_url": "https://github.com/acme-org/excalidraw/commit/0f769068b3f1...",
    "status": "resolved",
    "resolution_method": "tag_match"
  }
]
```

### Status values

| Status | Meaning |
|--------|---------|
| `resolved` | Commit SHA found |
| `repo_found_tag_not_matched` | GitHub repo identified but tag doesn't match any git tag |
| `repo_not_found` | Could not determine the source GitHub repo |
| `no_tag` | Image has no tag (uses `latest` or digest-only) |

### Resolution method values

| Method | Meaning |
|--------|---------|
| `oci_labels` | Found via image labels |
| `tag_match` | Matched image tag to git tag |
| `commit_sha_tag` | Image tag was itself a commit SHA |

## Project Structure

```
code_provenance/
├── run.sh                  # Sets up venv if needed, installs deps, runs the tool
├── code_provenance/
│   ├── __init__.py
│   ├── cli.py              # argparse entry point
│   ├── compose_parser.py   # YAML parsing, image extraction
│   ├── registry.py         # OCI registry API calls (ghcr.io, Docker Hub)
│   ├── resolver.py         # Resolution chain orchestration
│   └── output.py           # Table and JSON formatting
├── tests/
│   └── ...
├── pyproject.toml
└── README.md
```

## Dependencies

- `pyyaml` — docker-compose YAML parsing
- `requests` — HTTP calls to registries and GitHub API
- `rich` — terminal table formatting

## Authentication

- No auth required for public images and public GitHub repos
- If `GITHUB_TOKEN` env var is set, use it for GitHub API calls (raises rate limit from 60/hr to 5000/hr)
- Registry tokens are obtained anonymously per the OCI distribution spec

## Scope / Non-goals

- Private registries and private repos: out of scope for v1
- No Docker daemon required
- No manual image-to-repo mapping config
- No recursive `FROM` chain resolution (only the top-level image)
