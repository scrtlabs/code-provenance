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
