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


def resolve_tag_to_commit(owner: str, repo: str, tag: str) -> tuple[str, bool, str] | None:
    """Resolve an image tag to a commit SHA by matching against git tags.

    Tries exact match first, then prefix match (e.g., v2.10 -> highest v2.10.x).
    Returns (commit_sha, is_exact_match, matched_git_tag) or None.
    """
    headers = github_headers()
    url = f"https://api.github.com/repos/{owner}/{repo}/tags"

    prefix_candidates: list[tuple[tuple[int, ...], str, str]] = []  # (version, sha, tag_name)

    while url:
        resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
        if resp.status_code != 200:
            return None

        for git_tag in resp.json():
            name = git_tag["name"]
            # Exact match (with/without v prefix)
            if name == tag or name == f"v{tag}" or _normalize_tag(name) == _normalize_tag(tag):
                return git_tag["commit"]["sha"], True, name

            # Collect prefix match candidates
            if _is_prefix_match(tag, name):
                version = _parse_version_tuple(name)
                if version is not None:
                    prefix_candidates.append((version, git_tag["commit"]["sha"], name))

        url = resp.links.get("next", {}).get("url")

    # Return the highest version among prefix matches
    if prefix_candidates:
        prefix_candidates.sort(reverse=True)
        return prefix_candidates[0][1], False, prefix_candidates[0][2]

    return None


def get_branch_commit(owner: str, repo: str, branch: str) -> str | None:
    """Get the latest commit on a specific branch. Returns SHA or None."""
    headers = github_headers()
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/branches/{branch}",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        return resp.json().get("commit", {}).get("sha")
    except (requests.RequestException, KeyError):
        return None


def get_latest_release_commit(owner: str, repo: str) -> tuple[str, str] | None:
    """Get the commit SHA of the latest GitHub release.

    Returns (commit_sha, tag_name) or None.
    """
    headers = github_headers()
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            headers=headers,
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        tag_name = resp.json().get("tag_name")
        if not tag_name:
            return None
    except requests.RequestException:
        return None

    # Resolve the release tag to a commit
    tag_result = resolve_tag_to_commit(owner, repo, tag_name)
    if tag_result:
        commit_sha, _, _ = tag_result
        return commit_sha, tag_name
    return None


def get_latest_commit(owner: str, repo: str) -> str | None:
    """Get the latest commit SHA on the default branch."""
    headers = github_headers()
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            headers=headers,
            params={"per_page": 1},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        commits = resp.json()
        if commits:
            return commits[0]["sha"]
    except (requests.RequestException, KeyError, IndexError):
        pass
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


def _find_ghcr_package_version(
    owner: str, package_name: str, *, match_digest: str | None = None, match_tag: str | None = None,
) -> dict | None:
    """Find a GHCR package version by digest or tag via the GitHub Packages API.

    Requires GITHUB_TOKEN with read:packages scope.
    Returns {"repo": "owner/repo", "commit": "sha", "tags": [...]} or None.
    """
    headers = github_headers()
    if "Authorization" not in headers:
        return None

    for entity_type in ["orgs", "users"]:
        pkg_base = f"https://api.github.com/{entity_type}/{owner}/packages/container/{package_name}"

        # Get package metadata for source repo
        try:
            pkg_resp = requests.get(pkg_base, headers=headers, timeout=10)
            if pkg_resp.status_code == 403:
                return None
            if pkg_resp.status_code != 200:
                continue
            pkg_data = pkg_resp.json()
        except requests.RequestException:
            continue

        repo_info = pkg_data.get("repository", {})
        full_name = repo_info.get("full_name")
        if not full_name:
            continue

        # Search versions
        url = f"{pkg_base}/versions"
        try:
            while url:
                resp = requests.get(url, headers=headers, params={"per_page": 50}, timeout=10)
                if resp.status_code != 200:
                    break

                for version in resp.json():
                    name = version.get("name", "")
                    metadata = version.get("metadata", {}).get("container", {})
                    tags = metadata.get("tags", [])

                    # Match by digest (version name is the digest)
                    if match_digest and name != match_digest:
                        if match_tag is None:
                            continue
                    # Match by tag
                    if match_tag and match_tag not in tags:
                        continue

                    # Found matching version — resolve tags to a commit
                    repo_owner, repo_name = full_name.split("/", 1)
                    resolvable_tags = [t for t in tags if t != "latest"]
                    for tag in resolvable_tags:
                        tag_result = resolve_tag_to_commit(repo_owner, repo_name, tag)
                        if tag_result:
                            commit_sha, _, _ = tag_result
                            return {"repo": full_name, "commit": commit_sha, "tags": tags}

                    return {"repo": full_name, "commit": None, "tags": tags}

                url = resp.links.get("next", {}).get("url")
        except requests.RequestException:
            continue

    return None


def resolve_ghcr_digest_via_packages(owner: str, package_name: str, digest: str) -> dict | None:
    """Find the commit for a GHCR image by its digest."""
    return _find_ghcr_package_version(owner, package_name, match_digest=digest)


def resolve_ghcr_latest_via_packages(owner: str, package_name: str) -> dict | None:
    """Find the commit for a GHCR image's :latest tag."""
    return _find_ghcr_package_version(owner, package_name, match_tag="latest")


def find_ghcr_version_by_tag_prefix(
    owner: str, package_name: str, tag_prefix: str,
) -> dict | None:
    """Search GHCR package versions for a tag matching a prefix.

    e.g., tag_prefix='10.11' matches '10.11.16-jammy', returns the first match.
    Returns {"repo": "owner/repo", "version_tag": "10.11.16-jammy"} or None.
    """
    headers = github_headers()
    if "Authorization" not in headers:
        return None

    for entity_type in ["orgs", "users"]:
        pkg_base = f"https://api.github.com/{entity_type}/{owner}/packages/container/{package_name}"

        try:
            pkg_resp = requests.get(pkg_base, headers=headers, timeout=10)
            if pkg_resp.status_code == 403:
                return None
            if pkg_resp.status_code != 200:
                continue
            pkg_data = pkg_resp.json()
        except requests.RequestException:
            continue

        repo_info = pkg_data.get("repository", {})
        full_name = repo_info.get("full_name")
        if not full_name:
            continue

        # Search versions for a tag matching the prefix
        url = f"{pkg_base}/versions"
        best_match = None
        best_version: tuple[int, ...] | None = None
        try:
            while url:
                resp = requests.get(url, headers=headers, params={"per_page": 100}, timeout=10)
                if resp.status_code != 200:
                    break

                for version in resp.json():
                    metadata = version.get("metadata", {}).get("container", {})
                    tags = metadata.get("tags", [])
                    for tag in tags:
                        # Check if tag starts with prefix followed by . or -
                        stripped = tag[len(tag_prefix):] if tag.startswith(tag_prefix) else None
                        if stripped is not None and (stripped == "" or stripped[0] in ".-"):
                            # Parse version for comparison
                            ver_str = tag.split("-")[0]  # strip OS suffix like -jammy
                            parts = ver_str.split(".")
                            try:
                                ver_tuple = tuple(int(p) for p in parts)
                            except ValueError:
                                ver_tuple = None
                            if ver_tuple and (best_version is None or ver_tuple > best_version):
                                best_version = ver_tuple
                                best_match = {"repo": full_name, "version_tag": tag}

                url = resp.links.get("next", {}).get("url")
        except requests.RequestException:
            pass

        if best_match:
            return best_match

    return None


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
