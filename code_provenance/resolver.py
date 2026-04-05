import re
from code_provenance.models import ImageRef, ImageResult
from code_provenance.registry import fetch_oci_labels
from code_provenance.github import (
    resolve_tag_to_commit, infer_repo_from_dockerhub,
    resolve_ghcr_digest_via_packages, resolve_ghcr_latest_via_packages,
)

_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40,}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _is_resolvable_tag(tag: str) -> bool:
    """Check if a tag can be matched against git tags."""
    return bool(tag) and tag != "latest" and not _DIGEST_RE.match(tag)


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
    if _is_resolvable_tag(ref.tag):
        commit_sha = resolve_tag_to_commit(owner, repo_name, ref.tag)
        if commit_sha:
            result.commit = commit_sha
            result.commit_url = f"{result.repo}/commit/{commit_sha}"
            result.status = "resolved"
            result.resolution_method = "tag_match"
            return result
        result.status = "repo_found_tag_not_matched"
        return result

    # Step 4: For GHCR images, try the packages API for digest or :latest
    if ref.registry == "ghcr.io":
        if _DIGEST_RE.match(ref.tag):
            pkg_result = resolve_ghcr_digest_via_packages(ref.namespace, ref.name, ref.tag)
        elif ref.tag == "latest" or not ref.tag:
            pkg_result = resolve_ghcr_latest_via_packages(ref.namespace, ref.name)
        else:
            pkg_result = None

        if pkg_result:
            repo_full = pkg_result["repo"]
            result.repo = f"https://github.com/{repo_full}"
            if pkg_result.get("commit"):
                result.commit = pkg_result["commit"]
                result.commit_url = f"{result.repo}/commit/{result.commit}"
                result.status = "resolved"
                result.resolution_method = "packages_api"
                return result
            tags = pkg_result.get("tags", [])
            resolvable = [t for t in tags if t != "latest"]
            result.status = "repo_found_tag_not_matched" if resolvable else "no_tag"
            return result

    result.status = "no_tag"
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
