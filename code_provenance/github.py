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


def _normalize_tag(tag: str) -> str:
    """Strip leading 'v' for comparison."""
    return tag.lstrip("v")


def _is_prefix_match(image_tag: str, git_tag: str) -> bool:
    """Check if git_tag is a more specific version of image_tag.

    e.g., image_tag='v2.10' matches git_tag='v2.10.7' but not 'v2.1' or 'v2.100'.
    """
    norm_image = _normalize_tag(image_tag)
    norm_git = _normalize_tag(git_tag)
    return norm_git.startswith(norm_image + ".")


def _parse_version_tuple(tag: str) -> tuple[int, ...] | None:
    """Parse a version string into a tuple of ints for comparison."""
    norm = _normalize_tag(tag)
    # Strip pre-release suffixes like -rc1, -beta2
    norm = re.split(r"[-+]", norm)[0]
    parts = norm.split(".")
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def resolve_tag_to_commit(owner: str, repo: str, tag: str) -> str | None:
    """Resolve an image tag to a commit SHA by matching against git tags.

    Tries exact match first, then prefix match (e.g., v2.10 -> highest v2.10.x).
    """
    headers = github_headers()
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"

    prefix_candidates: list[tuple[tuple[int, ...], str]] = []

    while url:
        resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
        if resp.status_code != 200:
            return None

        for git_tag in resp.json():
            name = git_tag["name"]
            # Exact match (with/without v prefix)
            if name == tag or name == f"v{tag}" or _normalize_tag(name) == _normalize_tag(tag):
                return git_tag["commit"]["sha"]

            # Collect prefix match candidates
            if _is_prefix_match(tag, name):
                version = _parse_version_tuple(name)
                if version is not None:
                    prefix_candidates.append((version, git_tag["commit"]["sha"]))

        url = resp.links.get("next", {}).get("url")

    # Return the highest version among prefix matches
    if prefix_candidates:
        prefix_candidates.sort(reverse=True)
        return prefix_candidates[0][1]

    return None


def check_github_repo_exists(owner: str, repo: str) -> bool:
    """Check if a GitHub repo exists."""
    headers = github_headers()
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
            timeout=10,
        )
        return resp.status_code == 200
    except requests.RequestException:
        return False


def infer_repo_from_dockerhub(namespace: str, name: str) -> tuple[str, str] | None:
    """Try to find the GitHub repo for a Docker Hub image."""
    # For official images (library/X), try the image name as org/repo directly
    # e.g., traefik -> traefik/traefik, nginx -> nginx/nginx
    if namespace == "library":
        if check_github_repo_exists(name, name):
            return name, name

    # For namespaced images, try namespace/name on GitHub
    if namespace != "library":
        if check_github_repo_exists(namespace, name):
            return namespace, name

    # Fall back to scraping Docker Hub description for GitHub links
    url = f"https://hub.docker.com/v2/repositories/{namespace}/{name}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        text = (data.get("full_description") or "") + " " + (data.get("description") or "")
        match = re.search(r"https?://github\.com/([\w.-]+)/([\w.-]+)", text)
        if match:
            return match.group(1), match.group(2)
    except requests.RequestException:
        pass

    return None
