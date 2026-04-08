# code-provenance

Resolve Docker images in a docker-compose file to their exact source code commits on GitHub.

## Installation

```bash
pip install code-provenance
```

Requires Python 3.10+.

## CLI Usage

```bash
code-provenance [compose-file] [--image IMAGE] [--json] [--verbose]
```

- `compose-file` -- path to a docker-compose file (default: `docker-compose.yml`)
- `--image IMAGE` -- resolve a single image reference instead of a compose file
- `--json` -- output results as JSON
- `--verbose`, `-v` -- show resolution steps for each image

### Examples

Resolve all images in a docker-compose file:

```bash
code-provenance docker-compose.yml
```

```
web: traefik:v3.6.0
  repo:       github.com/traefik/traefik
  commit:     06db5168c0d9
  status:     resolved
  confidence: exact
  url:        https://github.com/traefik/traefik/commit/06db5168c0d9...
```

Resolve a single image:

```bash
code-provenance --image ollama/ollama:0.12.3
```

```
image: ollama/ollama:0.12.3
  repo:       github.com/ollama/ollama
  commit:     b04e46da3ebc
  status:     resolved
  confidence: exact
  url:        https://github.com/ollama/ollama/commit/b04e46da3ebc...
```

## Library Usage

```python
from code_provenance.compose_parser import parse_compose, parse_image_ref
from code_provenance.resolver import resolve_image

yaml_content = open("docker-compose.yml").read()
for service, image in parse_compose(yaml_content):
    ref = parse_image_ref(image)
    result = resolve_image(service, ref)
    print(f"{result.service}: {result.commit} ({result.confidence})")
```

## API Reference

### Functions

- `parse_compose(yaml_content: str) -> list[tuple[str, str]]` -- parse a docker-compose YAML string and return `(service_name, image_string)` pairs
- `parse_image_ref(image: str) -> ImageRef` -- parse a Docker image string into its components
- `resolve_image(service: str, ref: ImageRef) -> ImageResult` -- resolve an image reference to its source code commit

### ImageRef

| Field | Type | Description |
|-------|------|-------------|
| `registry` | `str` | e.g. `"ghcr.io"`, `"docker.io"` |
| `namespace` | `str` | e.g. `"myorg"`, `"library"` |
| `name` | `str` | e.g. `"traefik"`, `"postgres"` |
| `tag` | `str` | e.g. `"v3.6.0"`, `"latest"` |
| `raw` | `str` | original image string from docker-compose |

### ImageResult

| Field | Type | Description |
|-------|------|-------------|
| `service` | `str` | service name from docker-compose |
| `image` | `str` | original image string |
| `registry` | `str` | image registry |
| `repo` | `str \| None` | GitHub repository URL |
| `tag` | `str` | image tag |
| `commit` | `str \| None` | resolved commit SHA |
| `commit_url` | `str \| None` | URL to the commit on GitHub |
| `status` | `str` | `"resolved"`, `"repo_not_found"`, `"repo_found_tag_not_matched"`, or `"no_tag"` |
| `resolution_method` | `str \| None` | how the commit was resolved (e.g. `"oci_labels"`, `"tag_match"`) |
| `confidence` | `str \| None` | `"exact"` or `"approximate"` |
| `steps` | `list[str]` | resolution steps taken (useful with `--verbose`) |

## Authentication

Set `GITHUB_TOKEN` for full functionality (digest resolution, `:latest` on GHCR, higher rate limits):

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

Create a classic token at https://github.com/settings/tokens with `read:packages` scope. If using the `gh` CLI, run `gh auth refresh -h github.com -s read:packages` first.

The `run.sh` wrapper auto-detects the token from `gh` CLI if available.

## License

MIT
