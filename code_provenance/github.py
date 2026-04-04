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
            if name == tag or name == f"v{tag}" or name.lstrip("v") == tag.lstrip("v"):
                return git_tag["commit"]["sha"]

        # Follow pagination
        url = resp.links.get("next", {}).get("url")

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
