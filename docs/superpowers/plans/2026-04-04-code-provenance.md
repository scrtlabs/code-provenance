# Code Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that reads a docker-compose file and resolves each Docker image to its exact source commit on GitHub.

**Architecture:** Parse YAML to extract images, query OCI registries via HTTP for labels, infer GitHub repos from image paths/Docker Hub API, match image tags to git tags via GitHub API. No Docker daemon needed.

**Tech Stack:** Python 3.10+, pyyaml, requests, rich, pytest

---

## File Map

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata, dependencies, entry point |
| `code_provenance/__init__.py` | Package init, exports `ImageResult` dataclass |
| `code_provenance/models.py` | `ImageRef` and `ImageResult` dataclasses |
| `code_provenance/compose_parser.py` | Parse docker-compose YAML, extract and normalize image refs |
| `code_provenance/registry.py` | Fetch OCI labels from ghcr.io and Docker Hub registries |
| `code_provenance/github.py` | GitHub API: tag-to-commit resolution, repo metadata |
| `code_provenance/resolver.py` | Orchestrate the resolution chain for each image |
| `code_provenance/output.py` | Format results as table or JSON |
| `code_provenance/cli.py` | argparse entry point |
| `run.sh` | Venv setup + run wrapper |
| `tests/test_compose_parser.py` | Tests for YAML parsing |
| `tests/test_registry.py` | Tests for registry API calls |
| `tests/test_github.py` | Tests for GitHub tag resolution |
| `tests/test_resolver.py` | Tests for resolution chain |
| `tests/test_output.py` | Tests for formatting |
| `tests/test_cli.py` | Integration test: CLI end-to-end |

---

### Task 1: Project Scaffolding & Models

**Files:**
- Create: `pyproject.toml`
- Create: `code_provenance/__init__.py`
- Create: `code_provenance/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "code-provenance"
version = "0.1.0"
description = "Resolve Docker images to their source code commits on GitHub"
requires-python = ">=3.10"
dependencies = [
    "pyyaml>=6.0",
    "requests>=2.31",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0"]

[project.scripts]
code-provenance = "code_provenance.cli:main"
```

- [ ] **Step 2: Create `code_provenance/__init__.py`**

```python
from code_provenance.models import ImageRef, ImageResult
```

- [ ] **Step 3: Create `code_provenance/models.py`**

```python
from dataclasses import dataclass, field


@dataclass
class ImageRef:
    """A parsed Docker image reference."""
    registry: str          # e.g. "ghcr.io", "docker.io"
    namespace: str         # e.g. "acme-org", "library"
    name: str              # e.g. "excalidraw", "postgres"
    tag: str               # e.g. "v3.4.12", "latest"
    raw: str               # original string from docker-compose

    @property
    def full_name(self) -> str:
        """Registry/namespace/name without tag."""
        return f"{self.registry}/{self.namespace}/{self.name}"


@dataclass
class ImageResult:
    """Resolution result for a single image."""
    service: str
    image: str             # original image string
    registry: str
    repo: str | None = None
    tag: str = ""
    commit: str | None = None
    commit_url: str | None = None
    status: str = "repo_not_found"
    resolution_method: str | None = None
```

- [ ] **Step 4: Create `tests/__init__.py`**

Empty file.

- [ ] **Step 5: Write test for models**

```python
# tests/test_models.py
from code_provenance.models import ImageRef, ImageResult


def test_image_ref_full_name():
    ref = ImageRef(
        registry="ghcr.io",
        namespace="acme-org",
        name="excalidraw",
        tag="v3.4.12",
        raw="ghcr.io/acme-org/excalidraw:v3.4.12",
    )
    assert ref.full_name == "ghcr.io/acme-org/excalidraw"


def test_image_result_defaults():
    r = ImageResult(service="web", image="nginx:latest", registry="docker.io")
    assert r.status == "repo_not_found"
    assert r.commit is None
    assert r.resolution_method is None
```

- [ ] **Step 6: Run tests**

Run: `cd code_provenance && python -m pytest tests/test_models.py -v`
Expected: 2 tests PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml code_provenance/ tests/
git commit -m "feat: project scaffolding and data models"
```

---

### Task 2: Docker-Compose Parser

**Files:**
- Create: `code_provenance/compose_parser.py`
- Create: `tests/test_compose_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_compose_parser.py
import pytest
from code_provenance.compose_parser import parse_compose, parse_image_ref


class TestParseImageRef:
    def test_ghcr_with_tag(self):
        ref = parse_image_ref("ghcr.io/acme-org/excalidraw:v3.4.12")
        assert ref.registry == "ghcr.io"
        assert ref.namespace == "acme-org"
        assert ref.name == "excalidraw"
        assert ref.tag == "v3.4.12"

    def test_docker_hub_official(self):
        ref = parse_image_ref("postgres:16.2")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "postgres"
        assert ref.tag == "16.2"

    def test_docker_hub_namespaced(self):
        ref = parse_image_ref("bitnami/redis:7.2")
        assert ref.registry == "docker.io"
        assert ref.namespace == "bitnami"
        assert ref.name == "redis"
        assert ref.tag == "7.2"

    def test_no_tag_defaults_to_latest(self):
        ref = parse_image_ref("nginx")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "nginx"
        assert ref.tag == "latest"

    def test_ghcr_no_tag(self):
        ref = parse_image_ref("ghcr.io/owner/repo")
        assert ref.tag == "latest"

    def test_digest_reference(self):
        ref = parse_image_ref("nginx@sha256:abc123")
        assert ref.registry == "docker.io"
        assert ref.namespace == "library"
        assert ref.name == "nginx"
        assert ref.tag == "sha256:abc123"


class TestParseCompose:
    def test_extracts_services_and_images(self):
        yaml_content = """
version: '3'
services:
  web:
    image: ghcr.io/acme-org/excalidraw:v3.4.12
    ports:
      - "80:80"
  db:
    image: postgres:16.2
    environment:
      POSTGRES_PASSWORD: secret
  worker:
    build: ./worker
"""
        services = parse_compose(yaml_content)
        assert len(services) == 2  # worker has no image, skipped
        assert services[0] == ("web", "ghcr.io/acme-org/excalidraw:v3.4.12")
        assert services[1] == ("db", "postgres:16.2")

    def test_empty_services(self):
        yaml_content = """
version: '3'
services: {}
"""
        services = parse_compose(yaml_content)
        assert services == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_compose_parser.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `compose_parser.py`**

```python
# code_provenance/compose_parser.py
import yaml
from code_provenance.models import ImageRef


def parse_image_ref(image_string: str) -> ImageRef:
    """Parse a Docker image string into an ImageRef."""
    raw = image_string

    # Handle digest references (image@sha256:...)
    if "@" in image_string:
        name_part, digest = image_string.split("@", 1)
        tag = digest
        image_string = name_part
    elif ":" in image_string.split("/")[-1]:
        # Tag is after the last colon in the last path segment
        last_slash = image_string.rfind("/")
        after_slash = image_string[last_slash + 1:] if last_slash >= 0 else image_string
        if ":" in after_slash:
            colon_pos = image_string.rfind(":")
            tag = image_string[colon_pos + 1:]
            image_string = image_string[:colon_pos]
        else:
            tag = "latest"
    else:
        tag = "latest"

    # Determine registry
    parts = image_string.split("/")
    if len(parts) >= 2 and ("." in parts[0] or ":" in parts[0]):
        # First part looks like a registry hostname
        registry = parts[0]
        remaining = parts[1:]
    else:
        registry = "docker.io"
        remaining = parts

    # Determine namespace and name
    if len(remaining) == 1:
        namespace = "library"
        name = remaining[0]
    elif len(remaining) == 2:
        namespace = remaining[0]
        name = remaining[1]
    else:
        # Deeper paths: namespace is first, name is rest joined
        namespace = remaining[0]
        name = "/".join(remaining[1:])

    return ImageRef(
        registry=registry,
        namespace=namespace,
        name=name,
        tag=tag,
        raw=raw,
    )


def parse_compose(yaml_content: str) -> list[tuple[str, str]]:
    """Parse docker-compose YAML and return list of (service_name, image_string)."""
    data = yaml.safe_load(yaml_content)
    services = data.get("services", {}) or {}
    results = []
    for service_name, service_config in services.items():
        if isinstance(service_config, dict) and "image" in service_config:
            results.append((service_name, service_config["image"]))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_compose_parser.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/compose_parser.py tests/test_compose_parser.py
git commit -m "feat: docker-compose parser with image ref normalization"
```

---

### Task 3: OCI Registry Client

**Files:**
- Create: `code_provenance/registry.py`
- Create: `tests/test_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_registry.py
from unittest.mock import patch, MagicMock
from code_provenance.registry import fetch_oci_labels, get_registry_token
from code_provenance.models import ImageRef


class TestGetRegistryToken:
    @patch("code_provenance.registry.requests.get")
    def test_ghcr_token(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"token": "test-token-123"},
        )
        token = get_registry_token("ghcr.io", "acme-org/excalidraw")
        assert token == "test-token-123"
        mock_get.assert_called_once_with(
            "https://ghcr.io/token",
            params={"scope": "repository:acme-org/excalidraw:pull"},
            timeout=10,
        )

    @patch("code_provenance.registry.requests.get")
    def test_docker_hub_token(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"token": "hub-token-456"},
        )
        token = get_registry_token("docker.io", "library/postgres")
        assert token == "hub-token-456"
        mock_get.assert_called_once_with(
            "https://auth.docker.io/token",
            params={
                "service": "registry.docker.io",
                "scope": "repository:library/postgres:pull",
            },
            timeout=10,
        )


class TestFetchOciLabels:
    @patch("code_provenance.registry.requests.get")
    @patch("code_provenance.registry.get_registry_token")
    def test_returns_labels_when_present(self, mock_token, mock_get):
        mock_token.return_value = "fake-token"

        manifest_response = MagicMock(
            status_code=200,
            json=lambda: {
                "config": {"digest": "sha256:abc123"},
            },
        )
        config_response = MagicMock(
            status_code=200,
            json=lambda: {
                "config": {
                    "Labels": {
                        "org.opencontainers.image.source": "https://github.com/owner/repo",
                        "org.opencontainers.image.revision": "deadbeef1234",
                    }
                }
            },
        )
        mock_get.side_effect = [manifest_response, config_response]

        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        labels = fetch_oci_labels(ref)
        assert labels["org.opencontainers.image.source"] == "https://github.com/owner/repo"
        assert labels["org.opencontainers.image.revision"] == "deadbeef1234"

    @patch("code_provenance.registry.requests.get")
    @patch("code_provenance.registry.get_registry_token")
    def test_returns_empty_dict_on_failure(self, mock_token, mock_get):
        mock_token.return_value = "fake-token"
        mock_get.return_value = MagicMock(status_code=404)

        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        labels = fetch_oci_labels(ref)
        assert labels == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_registry.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `registry.py`**

```python
# code_provenance/registry.py
import requests
from code_provenance.models import ImageRef


def get_registry_token(registry: str, repo_path: str) -> str | None:
    """Get an anonymous pull token from an OCI registry."""
    if registry == "ghcr.io":
        url = "https://ghcr.io/token"
        params = {"scope": f"repository:{repo_path}:pull"}
    elif registry == "docker.io":
        url = "https://auth.docker.io/token"
        params = {
            "service": "registry.docker.io",
            "scope": f"repository:{repo_path}:pull",
        }
    else:
        return None

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()["token"]
    except (requests.RequestException, KeyError):
        return None


def _registry_base_url(registry: str) -> str:
    if registry == "docker.io":
        return "https://registry-1.docker.io"
    return f"https://{registry}"


def fetch_oci_labels(ref: ImageRef) -> dict[str, str]:
    """Fetch OCI labels from an image's config blob without pulling the image."""
    repo_path = f"{ref.namespace}/{ref.name}"
    token = get_registry_token(ref.registry, repo_path)
    if not token:
        return {}

    base_url = _registry_base_url(ref.registry)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.docker.distribution.manifest.v2+json",
    }

    # Fetch manifest to get config digest
    try:
        manifest_resp = requests.get(
            f"{base_url}/v2/{repo_path}/manifests/{ref.tag}",
            headers=headers,
            timeout=10,
        )
        if manifest_resp.status_code != 200:
            return {}
        config_digest = manifest_resp.json()["config"]["digest"]
    except (requests.RequestException, KeyError):
        return {}

    # Fetch config blob to read labels
    try:
        config_headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.docker.container.image.v1+json",
        }
        config_resp = requests.get(
            f"{base_url}/v2/{repo_path}/blobs/{config_digest}",
            headers=config_headers,
            timeout=10,
            allow_redirects=True,
        )
        if config_resp.status_code != 200:
            return {}
        return config_resp.json().get("config", {}).get("Labels", {}) or {}
    except (requests.RequestException, KeyError):
        return {}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_registry.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/registry.py tests/test_registry.py
git commit -m "feat: OCI registry client for fetching image labels"
```

---

### Task 4: GitHub API Client

**Files:**
- Create: `code_provenance/github.py`
- Create: `tests/test_github.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_github.py
import os
from unittest.mock import patch, MagicMock
from code_provenance.github import resolve_tag_to_commit, infer_repo_from_dockerhub, github_headers


class TestGithubHeaders:
    @patch.dict(os.environ, {}, clear=True)
    def test_no_token(self):
        h = github_headers()
        assert "Authorization" not in h
        assert h["Accept"] == "application/vnd.github+json"

    @patch.dict(os.environ, {"GITHUB_TOKEN": "ghp_test123"})
    def test_with_token(self):
        h = github_headers()
        assert h["Authorization"] == "Bearer ghp_test123"


class TestResolveTagToCommit:
    @patch("code_provenance.github.requests.get")
    def test_exact_match(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v3.4.12", "commit": {"sha": "0f769068b3f1abcdef"}},
                {"name": "v3.4.11", "commit": {"sha": "aaa111bbb222"}},
            ],
        )
        sha = resolve_tag_to_commit("acme-org", "excalidraw", "v3.4.12")
        assert sha == "0f769068b3f1abcdef"

    @patch("code_provenance.github.requests.get")
    def test_match_with_v_prefix(self, mock_get):
        """Image tag '3.4.12' should match git tag 'v3.4.12'."""
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v3.4.12", "commit": {"sha": "0f769068b3f1abcdef"}},
            ],
        )
        sha = resolve_tag_to_commit("acme-org", "excalidraw", "3.4.12")
        assert sha == "0f769068b3f1abcdef"

    @patch("code_provenance.github.requests.get")
    def test_no_match(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"name": "v1.0.0", "commit": {"sha": "aaa111"}},
            ],
        )
        sha = resolve_tag_to_commit("owner", "repo", "v9.9.9")
        assert sha is None

    @patch("code_provenance.github.requests.get")
    def test_paginated_tags(self, mock_get):
        """GitHub API returns 100 tags per page. Test pagination."""
        page1 = MagicMock(
            status_code=200,
            json=lambda: [{"name": f"v0.{i}", "commit": {"sha": f"sha{i}"}} for i in range(100)],
            links={"next": {"url": "https://api.github.com/repos/o/r/tags?page=2"}},
        )
        page2 = MagicMock(
            status_code=200,
            json=lambda: [{"name": "v1.0.0", "commit": {"sha": "target_sha"}}],
            links={},
        )
        mock_get.side_effect = [page1, page2]
        sha = resolve_tag_to_commit("o", "r", "v1.0.0")
        assert sha == "target_sha"


class TestInferRepoFromDockerhub:
    @patch("code_provenance.github.requests.get")
    def test_finds_github_url(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "full_description": "Source: https://github.com/docker-library/postgres",
                "description": "The PostgreSQL object-relational database system",
            },
        )
        owner, repo = infer_repo_from_dockerhub("library", "postgres")
        assert owner == "docker-library"
        assert repo == "postgres"

    @patch("code_provenance.github.requests.get")
    def test_no_github_url(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "full_description": "Some image with no GitHub link",
                "description": "",
            },
        )
        result = infer_repo_from_dockerhub("someuser", "someimage")
        assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_github.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `github.py`**

```python
# code_provenance/github.py
import os
import re
import requests


def github_headers() -> dict[str, str]:
    """Build GitHub API headers, with optional token auth."""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def resolve_tag_to_commit(owner: str, repo: str, tag: str) -> str | None:
    """Resolve an image tag to a commit SHA by matching against git tags."""
    headers = github_headers()
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"

    while url:
        resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
        if resp.status_code != 200:
            return None

        for git_tag in resp.json():
            name = git_tag["name"]
            # Exact match, or match with/without 'v' prefix
            if name == tag or name == f"v{tag}" or name.lstrip("v") == tag.lstrip("v"):
                return git_tag["commit"]["sha"]

        # Follow pagination
        url = resp.links.get("next", {}).get("url")

    return None


def infer_repo_from_dockerhub(namespace: str, name: str) -> tuple[str, str] | None:
    """Try to find the GitHub repo for a Docker Hub image."""
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        # Search full_description and description for GitHub URLs
        text = (data.get("full_description") or "") + " " + (data.get("description") or "")
        match = re.search(r"https?://github\.com/([\w.-]+)/([\w.-]+)", text)
        if match:
            return match.group(1), match.group(2)
    except requests.RequestException:
        pass

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_github.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/github.py tests/test_github.py
git commit -m "feat: GitHub API client for tag-to-commit resolution"
```

---

### Task 5: Resolution Chain

**Files:**
- Create: `code_provenance/resolver.py`
- Create: `tests/test_resolver.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_resolver.py
import re
from unittest.mock import patch
from code_provenance.models import ImageRef, ImageResult
from code_provenance.resolver import resolve_image


class TestResolveImage:
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_oci_labels_resolution(self, mock_labels):
        mock_labels.return_value = {
            "org.opencontainers.image.source": "https://github.com/owner/repo",
            "org.opencontainers.image.revision": "abc123def456",
        }
        ref = ImageRef("ghcr.io", "owner", "repo", "v1.0", "ghcr.io/owner/repo:v1.0")
        result = resolve_image("web", ref)
        assert result.status == "resolved"
        assert result.commit == "abc123def456"
        assert result.repo == "https://github.com/owner/repo"
        assert result.resolution_method == "oci_labels"

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_ghcr_tag_match_fallback(self, mock_labels, mock_tag):
        mock_labels.return_value = {}  # no OCI labels
        mock_tag.return_value = "0f769068b3f1"

        ref = ImageRef("ghcr.io", "acme-org", "excalidraw", "v3.4.12", "ghcr.io/acme-org/excalidraw:v3.4.12")
        result = resolve_image("web", ref)
        assert result.status == "resolved"
        assert result.commit == "0f769068b3f1"
        assert result.repo == "https://github.com/acme-org/excalidraw"
        assert result.resolution_method == "tag_match"
        mock_tag.assert_called_once_with("acme-org", "excalidraw", "v3.4.12")

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.infer_repo_from_dockerhub")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_dockerhub_inference_and_tag_match(self, mock_labels, mock_infer, mock_tag):
        mock_labels.return_value = {}
        mock_infer.return_value = ("docker-library", "postgres")
        mock_tag.return_value = "a1b2c3d4"

        ref = ImageRef("docker.io", "library", "postgres", "16.2", "postgres:16.2")
        result = resolve_image("db", ref)
        assert result.status == "resolved"
        assert result.commit == "a1b2c3d4"
        assert result.repo == "https://github.com/docker-library/postgres"

    @patch("code_provenance.resolver.resolve_tag_to_commit")
    @patch("code_provenance.resolver.fetch_oci_labels")
    def test_tag_not_matched(self, mock_labels, mock_tag):
        mock_labels.return_value = {}
        mock_tag.return_value = None

        ref = ImageRef("ghcr.io", "owner", "repo", "v9.9.9", "ghcr.io/owner/repo:v9.9.9")
        result = resolve_image("svc", ref)
        assert result.status == "repo_found_tag_not_matched"
        assert result.commit is None

    def test_commit_sha_as_tag(self):
        sha = "ac99122bcbd69f56a7d6523cbc883df9c4766e4c1046b661b76803087e4f475a"
        ref = ImageRef("ghcr.io", "owner", "repo", sha, f"ghcr.io/owner/repo:{sha}")
        with patch("code_provenance.resolver.fetch_oci_labels", return_value={}):
            result = resolve_image("svc", ref)
        assert result.status == "resolved"
        assert result.commit == sha
        assert result.resolution_method == "commit_sha_tag"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_resolver.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `resolver.py`**

```python
# code_provenance/resolver.py
import re
from code_provenance.models import ImageRef, ImageResult
from code_provenance.registry import fetch_oci_labels
from code_provenance.github import resolve_tag_to_commit, infer_repo_from_dockerhub

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40,}$")


def resolve_image(service: str, ref: ImageRef) -> ImageResult:
    """Run the resolution chain for a single image."""
    result = ImageResult(
        service=service,
        image=ref.raw,
        registry=ref.registry,
        tag=ref.tag,
    )

    # Step 1: Check OCI labels
    labels = fetch_oci_labels(ref)
    source = labels.get("org.opencontainers.image.source")
    revision = labels.get("org.opencontainers.image.revision")
    if source and revision:
        result.repo = source
        result.commit = revision
        result.commit_url = f"{source}/commit/{revision}"
        result.status = "resolved"
        result.resolution_method = "oci_labels"
        return result

    # Step 2: Infer repo
    owner, repo_name = _infer_repo(ref)
    if owner and repo_name:
        result.repo = f"https://github.com/{owner}/{repo_name}"
    else:
        result.status = "repo_not_found"
        return result

    # Check if tag is a commit SHA
    if _COMMIT_SHA_RE.match(ref.tag):
        result.commit = ref.tag
        result.commit_url = f"{result.repo}/commit/{ref.tag}"
        result.status = "resolved"
        result.resolution_method = "commit_sha_tag"
        return result

    # Step 3: Tag-to-commit resolution
    if ref.tag and ref.tag != "latest":
        commit_sha = resolve_tag_to_commit(owner, repo_name, ref.tag)
        if commit_sha:
            result.commit = commit_sha
            result.commit_url = f"{result.repo}/commit/{commit_sha}"
            result.status = "resolved"
            result.resolution_method = "tag_match"
            return result

    result.status = "repo_found_tag_not_matched" if ref.tag and ref.tag != "latest" else "no_tag"
    return result


def _infer_repo(ref: ImageRef) -> tuple[str | None, str | None]:
    """Infer the GitHub owner and repo name from an image reference."""
    if ref.registry == "ghcr.io":
        return ref.namespace, ref.name

    if ref.registry == "docker.io":
        hub_result = infer_repo_from_dockerhub(ref.namespace, ref.name)
        if hub_result:
            return hub_result

    return None, None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_resolver.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/resolver.py tests/test_resolver.py
git commit -m "feat: resolution chain orchestration"
```

---

### Task 6: Output Formatting

**Files:**
- Create: `code_provenance/output.py`
- Create: `tests/test_output.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_output.py
import json
from code_provenance.models import ImageResult
from code_provenance.output import format_json, format_table


def _sample_results():
    return [
        ImageResult(
            service="web",
            image="ghcr.io/owner/repo:v1.0",
            registry="ghcr.io",
            repo="https://github.com/owner/repo",
            tag="v1.0",
            commit="abc123def456",
            commit_url="https://github.com/owner/repo/commit/abc123def456",
            status="resolved",
            resolution_method="tag_match",
        ),
        ImageResult(
            service="cache",
            image="redis:7.2",
            registry="docker.io",
            tag="7.2",
            status="repo_not_found",
        ),
    ]


class TestFormatJson:
    def test_output_is_valid_json(self):
        output = format_json(_sample_results())
        data = json.loads(output)
        assert len(data) == 2
        assert data[0]["service"] == "web"
        assert data[0]["commit"] == "abc123def456"
        assert data[1]["status"] == "repo_not_found"
        assert data[1]["commit"] is None


class TestFormatTable:
    def test_table_contains_service_names(self):
        output = format_table(_sample_results())
        assert "web" in output
        assert "cache" in output

    def test_table_contains_status(self):
        output = format_table(_sample_results())
        assert "resolved" in output
        assert "repo_not_found" in output
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_output.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `output.py`**

```python
# code_provenance/output.py
import json
from dataclasses import asdict
from io import StringIO
from rich.console import Console
from rich.table import Table
from code_provenance.models import ImageResult


def format_json(results: list[ImageResult]) -> str:
    """Format results as a JSON array."""
    return json.dumps([asdict(r) for r in results], indent=2)


def format_table(results: list[ImageResult]) -> str:
    """Format results as a rich table, returned as a string."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("SERVICE")
    table.add_column("IMAGE")
    table.add_column("REPO")
    table.add_column("COMMIT")
    table.add_column("STATUS")

    for r in results:
        commit_display = r.commit[:12] if r.commit else "-"
        repo_display = r.repo.replace("https://", "") if r.repo else "-"
        table.add_row(r.service, r.image, repo_display, commit_display, r.status)

    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=160)
    console.print(table)
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_output.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/output.py tests/test_output.py
git commit -m "feat: table and JSON output formatting"
```

---

### Task 7: CLI Entry Point

**Files:**
- Create: `code_provenance/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_cli.py
import json
import os
import tempfile
from unittest.mock import patch
from code_provenance.cli import main
from code_provenance.models import ImageResult


SAMPLE_COMPOSE = """\
version: '3'
services:
  web:
    image: ghcr.io/acme-org/excalidraw:v3.4.12
    ports:
      - "80:80"
  db:
    image: postgres:16.2
"""


class TestCli:
    @patch("code_provenance.cli.resolve_image")
    def test_json_output(self, mock_resolve, capsys):
        mock_resolve.return_value = ImageResult(
            service="web",
            image="ghcr.io/acme-org/excalidraw:v3.4.12",
            registry="ghcr.io",
            repo="https://github.com/acme-org/excalidraw",
            tag="v3.4.12",
            commit="0f769068b3f1",
            commit_url="https://github.com/acme-org/excalidraw/commit/0f769068b3f1",
            status="resolved",
            resolution_method="tag_match",
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            f.write(SAMPLE_COMPOSE)
            f.flush()
            try:
                main([f.name, "--json"])
                captured = capsys.readouterr()
                data = json.loads(captured.out)
                assert len(data) == 2
                assert data[0]["status"] == "resolved"
            finally:
                os.unlink(f.name)

    def test_missing_file(self, capsys):
        code = main(["/nonexistent/docker-compose.yml"])
        assert code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower() or "not found" in captured.out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd code_provenance && python -m pytest tests/test_cli.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `cli.py`**

```python
# code_provenance/cli.py
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

    if args.json_output:
        print(format_json(results))
    else:
        print(format_table(results))

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd code_provenance && python -m pytest tests/test_cli.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add code_provenance/cli.py tests/test_cli.py
git commit -m "feat: CLI entry point with argparse"
```

---

### Task 8: run.sh Wrapper

**Files:**
- Create: `run.sh`

- [ ] **Step 1: Create `run.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

# Create venv if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Install/update deps
"$VENV_DIR/bin/pip" install -q -e "$SCRIPT_DIR"

# Run the tool, passing all arguments through
"$VENV_DIR/bin/code-provenance" "$@"
```

- [ ] **Step 2: Make executable**

Run: `chmod +x run.sh`

- [ ] **Step 3: Test it manually**

Run: `./run.sh --help`
Expected: prints usage/help text

- [ ] **Step 4: Commit**

```bash
git add run.sh
git commit -m "feat: run.sh wrapper for easy execution"
```

---

### Task 9: Integration Test with Real Registry

**Files:**
- Create: `tests/test_integration.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_integration.py
"""Integration tests that hit real registries and GitHub API.

Skip with: pytest -m 'not integration'
"""
import pytest
from code_provenance.compose_parser import parse_image_ref
from code_provenance.resolver import resolve_image


@pytest.mark.integration
def test_ghcr_excalidraw_tag_resolution():
    """Test against real ghcr.io/acme-org/excalidraw:v3.4.12."""
    ref = parse_image_ref("ghcr.io/acme-org/excalidraw:v3.4.12")
    result = resolve_image("web", ref)
    assert result.repo == "https://github.com/acme-org/excalidraw"
    assert result.commit is not None
    assert len(result.commit) >= 12
    assert result.status == "resolved"


@pytest.mark.integration
def test_ghcr_commit_sha_tag():
    """Test that a commit-SHA tag is detected directly."""
    sha = "ac99122bcbd69f56a7d6523cbc883df9c4766e4c1046b661b76803087e4f475a"
    ref = parse_image_ref(f"ghcr.io/acme-org/excalidraw:{sha}")
    result = resolve_image("svc", ref)
    assert result.status == "resolved"
    assert result.resolution_method == "commit_sha_tag"
    assert result.commit == sha
```

- [ ] **Step 2: Run integration tests**

Run: `cd code_provenance && python -m pytest tests/test_integration.py -v -m integration`
Expected: PASS (requires network access)

- [ ] **Step 3: Add pytest marker config**

Add to `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "integration: tests that hit real external APIs (deselect with '-m not integration')",
]
```

- [ ] **Step 4: Run full test suite**

Run: `cd code_provenance && python -m pytest -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py pyproject.toml
git commit -m "feat: integration tests against real registries"
```

---

### Task 10: End-to-End Test with run.sh

- [ ] **Step 1: Create a test docker-compose file**

Create `tests/fixtures/docker-compose.yml`:

```yaml
version: '3'
services:
  web:
    image: ghcr.io/acme-org/excalidraw:v3.4.12
    ports:
      - "80:80"
```

- [ ] **Step 2: Run end-to-end with table output**

Run: `cd code_provenance && ./run.sh tests/fixtures/docker-compose.yml`
Expected: table showing excalidraw resolved to a commit

- [ ] **Step 3: Run end-to-end with JSON output**

Run: `cd code_provenance && ./run.sh tests/fixtures/docker-compose.yml --json`
Expected: JSON array with status "resolved"

- [ ] **Step 4: Commit fixture**

```bash
git add tests/fixtures/
git commit -m "feat: end-to-end test fixture"
```
