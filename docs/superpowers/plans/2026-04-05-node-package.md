# Node.js Package + Monorepo Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the repo into a dual-language monorepo (python/ + node/) matching the secretvm-verify pattern, and implement a Node.js/TypeScript version of the code-provenance tool.

**Architecture:** Move existing Python code into `python/` subdirectory. Create `node/` with TypeScript source mirroring each Python module. Use Node.js built-in `fetch` for HTTP, `yaml` npm package for YAML parsing, manual string formatting for table output. All async/await.

**Tech Stack:** TypeScript 5.3+, Node.js 20+ (built-in fetch), yaml npm package, node:test for testing

---

## File Map

### Restructure (move existing files)

| From | To |
|------|-----|
| `pyproject.toml` | `python/pyproject.toml` |
| `code_provenance/` | `python/code_provenance/` |
| `tests/` | `python/tests/` |
| `run.sh` | `python/run.sh` |

### New Node.js files

| File | Responsibility |
|------|---------------|
| `node/package.json` | npm package config |
| `node/tsconfig.json` | TypeScript compiler config |
| `node/src/types.ts` | ImageRef and ImageResult interfaces |
| `node/src/composeParser.ts` | YAML parsing, image ref normalization |
| `node/src/registry.ts` | OCI registry API (token, manifest, labels) |
| `node/src/github.ts` | GitHub API (tags, packages, releases, repo check) |
| `node/src/resolver.ts` | Resolution chain orchestration |
| `node/src/output.ts` | Table and JSON formatting |
| `node/src/cli.ts` | CLI entry point |
| `node/src/index.ts` | Public API barrel export |

---

### Task 1: Restructure to Monorepo

**Files:**
- Move: `pyproject.toml` → `python/pyproject.toml`
- Move: `code_provenance/` → `python/code_provenance/`
- Move: `tests/` → `python/tests/`
- Move: `run.sh` → `python/run.sh`
- Modify: `python/run.sh` (fix SCRIPT_DIR path)
- Modify: `.gitignore`

- [ ] **Step 1: Create directories and move files**

```bash
mkdir -p python
git mv pyproject.toml python/
git mv code_provenance python/
git mv tests python/
git mv run.sh python/
```

- [ ] **Step 2: Fix `python/run.sh` to install from correct path**

The `SCRIPT_DIR` logic already uses `dirname "$0"`, so it should auto-resolve. But the `-e "$SCRIPT_DIR"` pip install needs to point at the directory containing `pyproject.toml`, which is now `python/`. No change needed since `run.sh` is now inside `python/`.

- [ ] **Step 3: Update `.gitignore`**

Replace the root `.gitignore` with:

```
.venv/
__pycache__/
*.pyc
*.egg-info/
.pytest_cache/

# Node
node/dist/
node/node_modules/

# Sample compose files in project root
/*.yaml
/*.yml
```

- [ ] **Step 4: Verify Python still works**

```bash
cd python && python3 -m venv .venv && .venv/bin/pip install -e . && .venv/bin/python -m pytest tests/ -v -m "not integration"
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "refactor: restructure into python/ subdirectory for monorepo"
```

---

### Task 2: Node.js Scaffolding

**Files:**
- Create: `node/package.json`
- Create: `node/tsconfig.json`
- Create: `node/src/types.ts`
- Create: `node/src/index.ts`

- [ ] **Step 1: Create `node/package.json`**

```json
{
  "name": "code-provenance",
  "version": "0.1.0",
  "description": "Resolve Docker images to their source code commits on GitHub",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "exports": {
    ".": {
      "types": "./dist/index.d.ts",
      "import": "./dist/index.js"
    }
  },
  "bin": {
    "code-provenance": "dist/cli.js"
  },
  "scripts": {
    "build": "tsc",
    "test": "node --test dist/**/*.test.js",
    "prepublishOnly": "npm run build"
  },
  "dependencies": {
    "yaml": "^2.4.0"
  },
  "devDependencies": {
    "@types/node": "^20.11.0",
    "typescript": "^5.3.0"
  }
}
```

- [ ] **Step 2: Create `node/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "outDir": "dist",
    "rootDir": "src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "declaration": true,
    "sourceMap": true
  },
  "include": ["src/**/*.ts"],
  "exclude": ["node_modules", "dist"]
}
```

- [ ] **Step 3: Create `node/src/types.ts`**

```typescript
export interface ImageRef {
  registry: string;
  namespace: string;
  name: string;
  tag: string;
  raw: string;
}

export interface ImageResult {
  service: string;
  image: string;
  registry: string;
  repo: string | null;
  tag: string;
  commit: string | null;
  commit_url: string | null;
  status: string;
  resolution_method: string | null;
  confidence: string | null;
}
```

- [ ] **Step 4: Create `node/src/index.ts`** (placeholder, will expand later)

```typescript
export type { ImageRef, ImageResult } from "./types.js";
```

- [ ] **Step 5: Install deps and build**

```bash
cd node && npm install && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add node/ && git commit -m "feat(node): project scaffolding and type definitions"
```

---

### Task 3: Compose Parser

**Files:**
- Create: `node/src/composeParser.ts`
- Create: `node/src/composeParser.test.ts`

- [ ] **Step 1: Create `node/src/composeParser.ts`**

```typescript
import YAML from "yaml";
import type { ImageRef } from "./types.js";

export function parseImageRef(imageString: string): ImageRef {
  const raw = imageString;
  let tag: string;

  if (imageString.includes("@")) {
    const [namePart, digest] = imageString.split("@", 2);
    tag = digest;
    imageString = namePart;
  } else if (imageString.split("/").at(-1)!.includes(":")) {
    const colonPos = imageString.lastIndexOf(":");
    tag = imageString.slice(colonPos + 1);
    imageString = imageString.slice(0, colonPos);
  } else {
    tag = "latest";
  }

  const parts = imageString.split("/");
  let registry: string;
  let remaining: string[];

  if (parts.length >= 2 && (parts[0].includes(".") || parts[0].includes(":"))) {
    registry = parts[0];
    remaining = parts.slice(1);
  } else {
    registry = "docker.io";
    remaining = parts;
  }

  let namespace: string;
  let name: string;

  if (remaining.length === 1) {
    namespace = "library";
    name = remaining[0];
  } else if (remaining.length === 2) {
    namespace = remaining[0];
    name = remaining[1];
  } else {
    namespace = remaining[0];
    name = remaining.slice(1).join("/");
  }

  return { registry, namespace, name, tag, raw };
}

export function parseCompose(yamlContent: string): Array<[string, string]> {
  const data = YAML.parse(yamlContent);
  const services = data?.services ?? {};
  const results: Array<[string, string]> = [];

  for (const [serviceName, serviceConfig] of Object.entries(services)) {
    if (
      typeof serviceConfig === "object" &&
      serviceConfig !== null &&
      "image" in serviceConfig
    ) {
      results.push([serviceName, (serviceConfig as any).image]);
    }
  }

  return results;
}
```

- [ ] **Step 2: Create `node/src/composeParser.test.ts`**

```typescript
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseImageRef, parseCompose } from "./composeParser.js";

describe("parseImageRef", () => {
  it("parses ghcr with tag", () => {
    const ref = parseImageRef("ghcr.io/acme-org/excalidraw:v3.4.12");
    assert.equal(ref.registry, "ghcr.io");
    assert.equal(ref.namespace, "acme-org");
    assert.equal(ref.name, "excalidraw");
    assert.equal(ref.tag, "v3.4.12");
  });

  it("parses docker hub official", () => {
    const ref = parseImageRef("postgres:16.2");
    assert.equal(ref.registry, "docker.io");
    assert.equal(ref.namespace, "library");
    assert.equal(ref.name, "postgres");
    assert.equal(ref.tag, "16.2");
  });

  it("parses docker hub namespaced", () => {
    const ref = parseImageRef("bitnami/redis:7.2");
    assert.equal(ref.registry, "docker.io");
    assert.equal(ref.namespace, "bitnami");
    assert.equal(ref.name, "redis");
    assert.equal(ref.tag, "7.2");
  });

  it("defaults to latest when no tag", () => {
    const ref = parseImageRef("nginx");
    assert.equal(ref.tag, "latest");
    assert.equal(ref.namespace, "library");
  });

  it("handles digest reference", () => {
    const ref = parseImageRef("nginx@sha256:abc123");
    assert.equal(ref.tag, "sha256:abc123");
    assert.equal(ref.name, "nginx");
  });
});

describe("parseCompose", () => {
  it("extracts services with images", () => {
    const yaml = `
version: '3'
services:
  web:
    image: ghcr.io/acme-org/excalidraw:v3.4.12
  db:
    image: postgres:16.2
  worker:
    build: ./worker
`;
    const services = parseCompose(yaml);
    assert.equal(services.length, 2);
    assert.deepEqual(services[0], ["web", "ghcr.io/acme-org/excalidraw:v3.4.12"]);
    assert.deepEqual(services[1], ["db", "postgres:16.2"]);
  });

  it("handles empty services", () => {
    const services = parseCompose("version: '3'\nservices: {}");
    assert.equal(services.length, 0);
  });
});
```

- [ ] **Step 3: Build and test**

```bash
cd node && npm run build && node --test dist/composeParser.test.js
```

- [ ] **Step 4: Commit**

```bash
git add node/src/composeParser.ts node/src/composeParser.test.ts && git commit -m "feat(node): compose parser with image ref normalization"
```

---

### Task 4: Registry Client

**Files:**
- Create: `node/src/registry.ts`

- [ ] **Step 1: Create `node/src/registry.ts`**

```typescript
import type { ImageRef } from "./types.js";

const MANIFEST_ACCEPT = [
  "application/vnd.docker.distribution.manifest.v2+json",
  "application/vnd.oci.image.manifest.v1+json",
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.oci.image.index.v1+json",
].join(", ");

const INDEX_MEDIA_TYPES = new Set([
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.oci.image.index.v1+json",
]);

export async function getRegistryToken(
  registry: string,
  repoPath: string
): Promise<string | null> {
  let url: string;
  let params: URLSearchParams;

  if (registry === "ghcr.io") {
    url = "https://ghcr.io/token";
    params = new URLSearchParams({ scope: `repository:${repoPath}:pull` });
  } else if (registry === "docker.io") {
    url = "https://auth.docker.io/token";
    params = new URLSearchParams({
      service: "registry.docker.io",
      scope: `repository:${repoPath}:pull`,
    });
  } else {
    return null;
  }

  try {
    const resp = await fetch(`${url}?${params}`, { signal: AbortSignal.timeout(10_000) });
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.token ?? null;
  } catch {
    return null;
  }
}

function registryBaseUrl(registry: string): string {
  if (registry === "docker.io") return "https://registry-1.docker.io";
  return `https://${registry}`;
}

async function resolveManifestToConfigDigest(
  baseUrl: string,
  repoPath: string,
  reference: string,
  token: string
): Promise<string | null> {
  try {
    const resp = await fetch(
      `${baseUrl}/v2/${repoPath}/manifests/${reference}`,
      {
        headers: { Authorization: `Bearer ${token}`, Accept: MANIFEST_ACCEPT },
        signal: AbortSignal.timeout(10_000),
      }
    );
    if (!resp.ok) return null;
    const data = await resp.json();

    const mediaType = data.mediaType ?? "";

    if (INDEX_MEDIA_TYPES.has(mediaType)) {
      const manifests: any[] = data.manifests ?? [];
      let digest: string | null = null;

      for (const m of manifests) {
        const plat = m.platform ?? {};
        if (plat.os === "unknown") continue;
        if (plat.architecture === "amd64" && plat.os === "linux") {
          digest = m.digest;
          break;
        }
      }
      if (!digest) {
        for (const m of manifests) {
          if (m.platform?.os !== "unknown") {
            digest = m.digest;
            break;
          }
        }
      }
      if (!digest) return null;
      return resolveManifestToConfigDigest(baseUrl, repoPath, digest, token);
    }

    return data.config?.digest ?? null;
  } catch {
    return null;
  }
}

export async function fetchOciLabels(
  ref: ImageRef
): Promise<Record<string, string>> {
  const repoPath = `${ref.namespace}/${ref.name}`;
  const token = await getRegistryToken(ref.registry, repoPath);
  if (!token) return {};

  const baseUrl = registryBaseUrl(ref.registry);
  const configDigest = await resolveManifestToConfigDigest(
    baseUrl,
    repoPath,
    ref.tag,
    token
  );
  if (!configDigest) return {};

  try {
    const resp = await fetch(
      `${baseUrl}/v2/${repoPath}/blobs/${configDigest}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.docker.container.image.v1+json",
        },
        redirect: "follow",
        signal: AbortSignal.timeout(10_000),
      }
    );
    if (!resp.ok) return {};
    const data = await resp.json();
    return data.config?.Labels ?? {};
  } catch {
    return {};
  }
}
```

- [ ] **Step 2: Build**

```bash
cd node && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add node/src/registry.ts && git commit -m "feat(node): OCI registry client"
```

---

### Task 5: GitHub API Client

**Files:**
- Create: `node/src/github.ts`

- [ ] **Step 1: Create `node/src/github.ts`**

```typescript
function githubHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
  };
  const token = process.env.GITHUB_TOKEN || DEFAULT_TOKEN;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function normalizeTag(tag: string): string {
  return tag.replace(/^v/, "");
}

function isPrefixMatch(imageTag: string, gitTag: string): boolean {
  const normImage = normalizeTag(imageTag);
  const normGit = normalizeTag(gitTag);
  return normGit.startsWith(normImage + ".");
}

function parseVersionTuple(tag: string): number[] | null {
  const norm = normalizeTag(tag).split(/[-+]/)[0];
  const parts = norm.split(".");
  const nums = parts.map(Number);
  if (nums.some(isNaN)) return null;
  return nums;
}

function parseLinkHeader(header: string | null): string | null {
  if (!header) return null;
  const match = header.match(/<([^>]+)>;\s*rel="next"/);
  return match ? match[1] : null;
}

export async function resolveTagToCommit(
  owner: string,
  repo: string,
  tag: string
): Promise<[string, boolean] | null> {
  const headers = githubHeaders();
  let url: string | null =
    `https://api.github.com/repos/${owner}/${repo}/tags?per_page=100`;

  const prefixCandidates: Array<{ version: number[]; sha: string }> = [];

  while (url) {
    const resp = await fetch(url, {
      headers,
      signal: AbortSignal.timeout(10_000),
    });
    if (!resp.ok) return null;

    const tags: any[] = await resp.json();

    for (const gitTag of tags) {
      const name: string = gitTag.name;
      if (
        name === tag ||
        name === `v${tag}` ||
        normalizeTag(name) === normalizeTag(tag)
      ) {
        return [gitTag.commit.sha, true];
      }

      if (isPrefixMatch(tag, name)) {
        const version = parseVersionTuple(name);
        if (version) {
          prefixCandidates.push({ version, sha: gitTag.commit.sha });
        }
      }
    }

    url = parseLinkHeader(resp.headers.get("link"));
  }

  if (prefixCandidates.length > 0) {
    prefixCandidates.sort((a, b) => {
      for (let i = 0; i < Math.max(a.version.length, b.version.length); i++) {
        const diff = (b.version[i] ?? 0) - (a.version[i] ?? 0);
        if (diff !== 0) return diff;
      }
      return 0;
    });
    return [prefixCandidates[0].sha, false];
  }

  return null;
}

export async function getLatestReleaseCommit(
  owner: string,
  repo: string
): Promise<[string, string] | null> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/releases/latest`,
      { headers, signal: AbortSignal.timeout(10_000) }
    );
    if (!resp.ok) return null;
    const data = await resp.json();
    const tagName = data.tag_name;
    if (!tagName) return null;

    const result = await resolveTagToCommit(owner, repo, tagName);
    if (result) return [result[0], tagName];
    return null;
  } catch {
    return null;
  }
}

export async function getLatestCommit(
  owner: string,
  repo: string
): Promise<string | null> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/commits?per_page=1`,
      { headers, signal: AbortSignal.timeout(10_000) }
    );
    if (!resp.ok) return null;
    const commits: any[] = await resp.json();
    return commits[0]?.sha ?? null;
  } catch {
    return null;
  }
}

export async function checkGithubRepoExists(
  owner: string,
  repo: string
): Promise<boolean> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}`,
      { headers, signal: AbortSignal.timeout(10_000) }
    );
    return resp.ok;
  } catch {
    return false;
  }
}

interface PackageResult {
  repo: string;
  commit: string | null;
  tags: string[];
}

async function findGhcrPackageVersion(
  owner: string,
  packageName: string,
  opts: { matchDigest?: string; matchTag?: string }
): Promise<PackageResult | null> {
  const headers = githubHeaders();
  if (!headers.Authorization) return null;

  for (const entityType of ["orgs", "users"]) {
    const pkgBase = `https://api.github.com/${entityType}/${owner}/packages/container/${packageName}`;

    let pkgResp: Response;
    try {
      pkgResp = await fetch(pkgBase, {
        headers,
        signal: AbortSignal.timeout(10_000),
      });
      if (pkgResp.status === 403) return null;
      if (!pkgResp.ok) continue;
    } catch {
      continue;
    }

    const pkgData = await pkgResp.json();
    const fullName: string | undefined = pkgData.repository?.full_name;
    if (!fullName) continue;

    let url: string | null = `${pkgBase}/versions?per_page=50`;

    try {
      while (url) {
        const resp = await fetch(url, {
          headers,
          signal: AbortSignal.timeout(10_000),
        });
        if (!resp.ok) break;

        const versions: any[] = await resp.json();

        for (const version of versions) {
          const name: string = version.name ?? "";
          const tags: string[] =
            version.metadata?.container?.tags ?? [];

          if (opts.matchDigest && name !== opts.matchDigest) {
            if (!opts.matchTag) continue;
          }
          if (opts.matchTag && !tags.includes(opts.matchTag)) continue;

          const [repoOwner, repoName] = fullName.split("/", 2);
          const resolvable = tags.filter((t) => t !== "latest");
          for (const t of resolvable) {
            const result = await resolveTagToCommit(repoOwner, repoName, t);
            if (result) {
              return { repo: fullName, commit: result[0], tags };
            }
          }
          return { repo: fullName, commit: null, tags };
        }

        url = parseLinkHeader(resp.headers.get("link"));
      }
    } catch {
      continue;
    }
  }

  return null;
}

export async function resolveGhcrDigestViaPackages(
  owner: string,
  packageName: string,
  digest: string
): Promise<PackageResult | null> {
  return findGhcrPackageVersion(owner, packageName, { matchDigest: digest });
}

export async function resolveGhcrLatestViaPackages(
  owner: string,
  packageName: string
): Promise<PackageResult | null> {
  return findGhcrPackageVersion(owner, packageName, { matchTag: "latest" });
}

export async function inferRepoFromDockerhub(
  namespace: string,
  name: string
): Promise<[string, string] | null> {
  if (namespace === "library") {
    if (await checkGithubRepoExists(name, name)) return [name, name];
  } else {
    if (await checkGithubRepoExists(namespace, name))
      return [namespace, name];
  }

  try {
    const resp = await fetch(
      `https://hub.docker.com/v2/repositories/${namespace}/${name}`,
      { signal: AbortSignal.timeout(10_000) }
    );
    if (!resp.ok) return null;

    const data = await resp.json();
    const text = `${data.full_description ?? ""} ${data.description ?? ""}`;
    const match = text.match(/https?:\/\/github\.com\/([\w.-]+)\/([\w.-]+)/);
    if (match) return [match[1], match[2]];
  } catch {
    // ignore
  }

  return null;
}
```

- [ ] **Step 2: Build**

```bash
cd node && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add node/src/github.ts && git commit -m "feat(node): GitHub API client"
```

---

### Task 6: Resolver

**Files:**
- Create: `node/src/resolver.ts`

- [ ] **Step 1: Create `node/src/resolver.ts`**

```typescript
import type { ImageRef, ImageResult } from "./types.js";
import { fetchOciLabels } from "./registry.js";
import {
  resolveTagToCommit,
  inferRepoFromDockerhub,
  resolveGhcrDigestViaPackages,
  resolveGhcrLatestViaPackages,
  getLatestReleaseCommit,
  getLatestCommit,
} from "./github.js";

const COMMIT_SHA_RE = /^[0-9a-f]{40,}$/;
const DIGEST_RE = /^sha256:[0-9a-f]{64}$/;

function isResolvableTag(tag: string): boolean {
  return !!tag && tag !== "latest" && !DIGEST_RE.test(tag);
}

async function inferRepo(
  ref: ImageRef
): Promise<[string, string] | null> {
  if (ref.registry === "ghcr.io") return [ref.namespace, ref.name];
  if (ref.registry === "docker.io") {
    return inferRepoFromDockerhub(ref.namespace, ref.name);
  }
  return null;
}

export async function resolveImage(
  service: string,
  ref: ImageRef
): Promise<ImageResult> {
  const result: ImageResult = {
    service,
    image: ref.raw,
    registry: ref.registry,
    repo: null,
    tag: ref.tag,
    commit: null,
    commit_url: null,
    status: "repo_not_found",
    resolution_method: null,
    confidence: null,
  };

  // Step 1: Check OCI labels
  const labels = await fetchOciLabels(ref);
  const source = labels["org.opencontainers.image.source"];
  const revision = labels["org.opencontainers.image.revision"];
  if (source && revision) {
    result.repo = source;
    result.commit = revision;
    result.commit_url = `${source}/commit/${revision}`;
    result.status = "resolved";
    result.resolution_method = "oci_labels";
    result.confidence = ref.tag === "latest" ? "approximate" : "exact";
    return result;
  }

  // Step 2: Infer repo
  const repoInfo = await inferRepo(ref);
  let owner: string | null = null;
  let repoName: string | null = null;
  if (repoInfo) {
    [owner, repoName] = repoInfo;
    result.repo = `https://github.com/${owner}/${repoName}`;
  } else {
    result.status = "repo_not_found";
    return result;
  }

  // Check if tag is a commit SHA
  if (COMMIT_SHA_RE.test(ref.tag)) {
    result.commit = ref.tag;
    result.commit_url = `${result.repo}/commit/${ref.tag}`;
    result.status = "resolved";
    result.resolution_method = "commit_sha_tag";
    result.confidence = "exact";
    return result;
  }

  // Step 3: Tag-to-commit resolution
  if (isResolvableTag(ref.tag)) {
    const tagResult = await resolveTagToCommit(owner, repoName, ref.tag);
    if (tagResult) {
      const [commitSha, isExact] = tagResult;
      result.commit = commitSha;
      result.commit_url = `${result.repo}/commit/${commitSha}`;
      result.status = "resolved";
      result.resolution_method = "tag_match";
      result.confidence = isExact ? "exact" : "approximate";
      return result;
    }
    result.status = "repo_found_tag_not_matched";
    return result;
  }

  // Step 4: GHCR packages API for digest or :latest
  if (ref.registry === "ghcr.io") {
    let pkgResult: { repo: string; commit: string | null; tags: string[] } | null = null;
    let pkgConfidence: string | null = null;

    if (DIGEST_RE.test(ref.tag)) {
      pkgResult = await resolveGhcrDigestViaPackages(ref.namespace, ref.name, ref.tag);
      pkgConfidence = "exact";
    } else if (ref.tag === "latest" || !ref.tag) {
      pkgResult = await resolveGhcrLatestViaPackages(ref.namespace, ref.name);
      pkgConfidence = "approximate";
    }

    if (pkgResult) {
      result.repo = `https://github.com/${pkgResult.repo}`;
      if (pkgResult.commit) {
        result.commit = pkgResult.commit;
        result.commit_url = `${result.repo}/commit/${pkgResult.commit}`;
        result.status = "resolved";
        result.resolution_method = "packages_api";
        result.confidence = pkgConfidence;
        return result;
      }
      const resolvable = pkgResult.tags.filter((t) => t !== "latest");
      result.status = resolvable.length > 0 ? "repo_found_tag_not_matched" : "no_tag";
      return result;
    }
  }

  // Step 5: Latest release or latest commit fallback
  if ((ref.tag === "latest" || !ref.tag) && owner && repoName) {
    const releaseResult = await getLatestReleaseCommit(owner, repoName);
    if (releaseResult) {
      result.commit = releaseResult[0];
      result.commit_url = `${result.repo}/commit/${releaseResult[0]}`;
      result.status = "resolved";
      result.resolution_method = "latest_release";
      result.confidence = "approximate";
      return result;
    }

    const latestSha = await getLatestCommit(owner, repoName);
    if (latestSha) {
      result.commit = latestSha;
      result.commit_url = `${result.repo}/commit/${latestSha}`;
      result.status = "resolved";
      result.resolution_method = "latest_commit";
      result.confidence = "approximate";
      return result;
    }
  }

  result.status = "no_tag";
  return result;
}
```

- [ ] **Step 2: Build**

```bash
cd node && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add node/src/resolver.ts && git commit -m "feat(node): resolution chain"
```

---

### Task 7: Output Formatting

**Files:**
- Create: `node/src/output.ts`

- [ ] **Step 1: Create `node/src/output.ts`**

```typescript
import type { ImageResult } from "./types.js";

export function formatJson(results: ImageResult[]): string {
  return JSON.stringify(results, null, 2);
}

export function formatTable(results: ImageResult[]): string {
  const headers = ["SERVICE", "IMAGE", "REPO", "COMMIT", "STATUS", "CONFIDENCE"];

  const rows = results.map((r) => [
    r.service,
    r.image,
    r.repo?.replace("https://", "") ?? "-",
    r.commit?.slice(0, 12) ?? "-",
    r.status,
    r.confidence ?? "-",
  ]);

  // Calculate column widths
  const widths = headers.map((h, i) =>
    Math.max(h.length, ...rows.map((row) => row[i].length))
  );

  const sep = widths.map((w) => "─".repeat(w + 2)).join("┼");
  const headerLine = headers
    .map((h, i) => ` ${h.padEnd(widths[i])} `)
    .join("│");
  const dataLines = rows.map((row) =>
    row.map((cell, i) => ` ${cell.padEnd(widths[i])} `).join("│")
  );

  return [
    `┌${sep.replaceAll("┼", "┬")}┐`,
    `│${headerLine}│`,
    `├${sep}┤`,
    ...dataLines.map((line) => `│${line}│`),
    `└${sep.replaceAll("┼", "┴")}┘`,
  ].join("\n");
}
```

- [ ] **Step 2: Build**

```bash
cd node && npm run build
```

- [ ] **Step 3: Commit**

```bash
git add node/src/output.ts && git commit -m "feat(node): table and JSON output formatting"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `node/src/cli.ts`
- Modify: `node/src/index.ts`

- [ ] **Step 1: Create `node/src/cli.ts`**

```typescript
#!/usr/bin/env node
import { readFileSync, existsSync } from "node:fs";
import { parseCompose, parseImageRef } from "./composeParser.js";
import { resolveImage } from "./resolver.js";
import { formatJson, formatTable } from "./output.js";

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  const jsonOutput = args.includes("--json");
  const filtered = args.filter((a) => a !== "--json");
  const composePath = filtered[0] ?? "docker-compose.yml";

  if (composePath === "--help" || composePath === "-h") {
    console.log(
      "Usage: code-provenance [compose-file] [--json]\n\n" +
        "Resolve Docker images to their source code commits on GitHub.\n\n" +
        "Arguments:\n" +
        "  compose-file  Path to docker-compose file (default: docker-compose.yml)\n\n" +
        "Options:\n" +
        "  --json        Output results as JSON\n" +
        "  --help, -h    Show this help"
    );
    return 0;
  }

  if (!existsSync(composePath)) {
    console.error(`Error: ${composePath} not found`);
    return 1;
  }

  const yamlContent = readFileSync(composePath, "utf-8");
  const services = parseCompose(yamlContent);

  if (services.length === 0) {
    console.error("No services with images found.");
    return 0;
  }

  const results = await Promise.all(
    services.map(([serviceName, imageString]) => {
      const ref = parseImageRef(imageString);
      return resolveImage(serviceName, ref);
    })
  );

  if (jsonOutput) {
    console.log(formatJson(results));
  } else {
    console.log(formatTable(results));
  }

  return 0;
}

main().then((code) => process.exit(code));
```

- [ ] **Step 2: Update `node/src/index.ts`** with full exports

```typescript
export type { ImageRef, ImageResult } from "./types.js";
export { parseCompose, parseImageRef } from "./composeParser.js";
export { resolveImage } from "./resolver.js";
export { formatJson, formatTable } from "./output.js";
```

- [ ] **Step 3: Build and test CLI**

```bash
cd node && npm run build && node dist/cli.js --help
```

Expected: prints help text

- [ ] **Step 4: Commit**

```bash
git add node/src/cli.ts node/src/index.ts && git commit -m "feat(node): CLI entry point and public API exports"
```

---

### Task 9: End-to-End Test

- [ ] **Step 1: Create a test compose file at repo root if not present**

```yaml
# test-data/docker-compose.yml
version: '3'
services:
  web:
    image: traefik:v3.6.0
```

- [ ] **Step 2: Test Node CLI against real compose file**

```bash
cd node && node dist/cli.js ../test-data/docker-compose.yml
```

Expected: table showing traefik resolved to a commit

- [ ] **Step 3: Test JSON output**

```bash
cd node && node dist/cli.js ../test-data/docker-compose.yml --json
```

Expected: JSON array with status "resolved"

- [ ] **Step 4: Compare Python and Node output**

```bash
cd python && ./run.sh ../test-data/docker-compose.yml --json > /tmp/py.json
cd ../node && node dist/cli.js ../test-data/docker-compose.yml --json > /tmp/node.json
diff <(jq -S '.[].commit' /tmp/py.json) <(jq -S '.[].commit' /tmp/node.json)
```

Expected: same commit SHAs

- [ ] **Step 5: Commit test fixture**

```bash
git add test-data/ && git commit -m "feat: shared test fixtures and end-to-end verification"
```

---

## Verification

1. **Python still works:** `cd python && ./run.sh ../test-data/docker-compose.yml`
2. **Node works:** `cd node && node dist/cli.js ../test-data/docker-compose.yml`
3. **Both produce same results:** compare JSON output commit SHAs
4. **Node tests pass:** `cd node && npm run build && node --test dist/composeParser.test.js`
5. **Python tests pass:** `cd python && .venv/bin/python -m pytest tests/ -v -m "not integration"`
