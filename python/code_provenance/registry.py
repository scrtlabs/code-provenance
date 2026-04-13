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


_MANIFEST_ACCEPT = ", ".join([
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
])

_INDEX_MEDIA_TYPES = {
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.index.v1+json",
}


def _resolve_manifest_to_config_digest(
    base_url: str, repo_path: str, reference: str, token: str, _depth: int = 0,
) -> str | None:
    """Resolve a manifest reference to a config blob digest, handling multi-arch indexes."""
    headers = {"Authorization": f"Bearer {token}", "Accept": _MANIFEST_ACCEPT}

    try:
        resp = requests.get(
            f"{base_url}/v2/{repo_path}/manifests/{reference}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except (requests.RequestException, KeyError, ValueError):
        return None

    media_type = data.get("mediaType", "")

    # If it's an index/manifest list, pick the first amd64/linux manifest
    if media_type in _INDEX_MEDIA_TYPES:
        manifests = data.get("manifests", [])
        platform_digest = None
        for m in manifests:
            platform = m.get("platform", {})
            # Skip attestation manifests
            if platform.get("os") == "unknown":
                continue
            if platform.get("architecture") == "amd64" and platform.get("os") == "linux":
                platform_digest = m["digest"]
                break
        if not platform_digest and manifests:
            # Fall back to first non-attestation manifest
            for m in manifests:
                if m.get("platform", {}).get("os") != "unknown":
                    platform_digest = m["digest"]
                    break
        if not platform_digest:
            return None
        if _depth >= 3:
            return None
        # Recursively resolve the platform-specific manifest
        return _resolve_manifest_to_config_digest(base_url, repo_path, platform_digest, token, _depth + 1)

    # Single manifest — extract config digest
    return data.get("config", {}).get("digest")


def fetch_oci_labels(ref: ImageRef) -> dict[str, str]:
    """Fetch OCI labels from an image's config blob without pulling the image."""
    repo_path = f"{ref.namespace}/{ref.name}"
    token = get_registry_token(ref.registry, repo_path)
    if not token:
        return {}

    base_url = _registry_base_url(ref.registry)
    config_digest = _resolve_manifest_to_config_digest(base_url, repo_path, ref.tag, token)
    if not config_digest:
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
