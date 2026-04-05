# code-provenance

Resolve Docker images in a docker-compose file to their exact source code commits on GitHub.

## Installation

```bash
npm install code-provenance
```

Requires Node.js 20+.

## CLI Usage

```bash
npx code-provenance [compose-file] [--json] [--verbose]
```

- `compose-file` -- path to a docker-compose file (default: `docker-compose.yml`)
- `--json` -- output results as JSON
- `--verbose`, `-v` -- show resolution steps for each image

### Example

```bash
npx code-provenance docker-compose.yml
```

```
┌─────────┬────────────────┬────────────────────────────┬──────────────┬──────────┬────────────┐
│ SERVICE │ IMAGE          │ REPO                       │ COMMIT       │ STATUS   │ CONFIDENCE │
├─────────┼────────────────┼────────────────────────────┼──────────────┼──────────┼────────────┤
│ web     │ traefik:v3.6.0 │ github.com/traefik/traefik │ 06db5168c0d9 │ resolved │ exact      │
└─────────┴────────────────┴────────────────────────────┴──────────────┴──────────┴────────────┘
```

## Library Usage

```typescript
import { readFileSync } from "node:fs";
import { parseCompose, parseImageRef, resolveImage } from "code-provenance";

const yaml = readFileSync("docker-compose.yml", "utf-8");
for (const [service, image] of parseCompose(yaml)) {
  const ref = parseImageRef(image);
  const result = await resolveImage(service, ref);
  console.log(`${result.service}: ${result.commit} (${result.confidence})`);
}
```

## API Reference

### Exports

- `parseCompose(yaml: string): [string, string][]` -- parse a docker-compose YAML string and return `[serviceName, imageString]` pairs
- `parseImageRef(image: string): ImageRef` -- parse a Docker image string into its components
- `resolveImage(service: string, ref: ImageRef): Promise<ImageResult>` -- resolve an image reference to its source code commit
- `formatTable(results: ImageResult[]): string` -- format results as a table
- `formatJson(results: ImageResult[]): string` -- format results as JSON

### ImageRef

| Field | Type | Description |
|-------|------|-------------|
| `registry` | `string` | e.g. `"ghcr.io"`, `"docker.io"` |
| `namespace` | `string` | e.g. `"myorg"`, `"library"` |
| `name` | `string` | e.g. `"traefik"`, `"postgres"` |
| `tag` | `string` | e.g. `"v3.6.0"`, `"latest"` |
| `raw` | `string` | original image string from docker-compose |

### ImageResult

| Field | Type | Description |
|-------|------|-------------|
| `service` | `string` | service name from docker-compose |
| `image` | `string` | original image string |
| `registry` | `string` | image registry |
| `repo` | `string \| null` | GitHub repository URL |
| `tag` | `string` | image tag |
| `commit` | `string \| null` | resolved commit SHA |
| `commit_url` | `string \| null` | URL to the commit on GitHub |
| `status` | `string` | `"resolved"`, `"repo_not_found"`, `"repo_found_tag_not_matched"`, or `"no_tag"` |
| `resolution_method` | `string \| null` | how the commit was resolved (e.g. `"oci_labels"`, `"tag_match"`) |
| `confidence` | `string \| null` | `"exact"` or `"approximate"` |
| `steps` | `string[]` | resolution steps taken (useful with `--verbose`) |

## Authentication

Set `GITHUB_TOKEN` for full functionality (digest resolution, `:latest` on GHCR, higher rate limits):

```bash
export GITHUB_TOKEN=ghp_your_token_here
```

Create a classic token at https://github.com/settings/tokens with `read:packages` scope.

## License

MIT
