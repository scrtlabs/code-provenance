import re
from code_provenance.models import ImageRef, ImageResult
from code_provenance.registry import fetch_oci_labels
from code_provenance.github import (
    resolve_tag_to_commit, infer_repo_from_dockerhub,
    resolve_ghcr_digest_via_packages, resolve_ghcr_latest_via_packages,
    get_latest_release_commit, get_latest_commit,
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
    result.steps.append(f"[1/5] Fetching OCI labels from {ref.registry}/{ref.namespace}/{ref.name}:{ref.tag}")
    labels = fetch_oci_labels(ref)
    source = labels.get("org.opencontainers.image.source")
    revision = labels.get("org.opencontainers.image.revision")
    if source and revision:
        result.steps.append(f"[1/5] Found OCI labels: source={source}, revision={revision[:12]}")
        result.repo = source
        result.commit = revision
        result.commit_url = f"{source}/commit/{revision}"
        result.status = "resolved"
        result.resolution_method = "oci_labels"
        result.confidence = "approximate" if ref.tag == "latest" else "exact"
        return result
    else:
        result.steps.append("[1/5] No OCI labels found")

    # Step 2: Infer repo
    result.steps.append(f"[2/5] Inferring GitHub repo from {ref.registry}/{ref.namespace}/{ref.name}")
    owner, repo_name = _infer_repo(ref)
    if owner and repo_name:
        result.steps.append(f"[2/5] Repo inferred: {owner}/{repo_name}")
        result.repo = f"https://github.com/{owner}/{repo_name}"
    else:
        result.steps.append("[2/5] Could not infer GitHub repo")
        result.status = "repo_not_found"
        return result

    # Check if tag is a commit SHA
    if _COMMIT_SHA_RE.match(ref.tag):
        result.steps.append("[2/5] Tag is a commit SHA, using directly")
        result.commit = ref.tag
        result.commit_url = f"{result.repo}/commit/{ref.tag}"
        result.status = "resolved"
        result.resolution_method = "commit_sha_tag"
        result.confidence = "exact"
        return result

    # Step 3: Tag-to-commit resolution
    if _is_resolvable_tag(ref.tag):
        result.steps.append(f'[3/5] Matching tag "{ref.tag}" against git tags in {owner}/{repo_name}')
        tag_result = resolve_tag_to_commit(owner, repo_name, ref.tag)
        if tag_result:
            commit_sha, is_exact = tag_result
            if is_exact:
                result.steps.append(f"[3/5] Exact tag match: {commit_sha[:12]}")
            else:
                result.steps.append(f"[3/5] Prefix match (e.g. v2.10 -> v2.10.x): {commit_sha[:12]}")
            result.commit = commit_sha
            result.commit_url = f"{result.repo}/commit/{commit_sha}"
            result.status = "resolved"
            result.resolution_method = "tag_match"
            result.confidence = "exact" if is_exact else "approximate"
            return result
        result.steps.append("[3/5] No matching git tag found")
        result.status = "repo_found_tag_not_matched"
        return result

    # Step 4: For GHCR images, try the packages API for digest or :latest
    if ref.registry == "ghcr.io":
        if _DIGEST_RE.match(ref.tag):
            result.steps.append(f"[4/5] Trying GHCR packages API for digest {ref.tag[:20]}...")
            pkg_result = resolve_ghcr_digest_via_packages(ref.namespace, ref.name, ref.tag)
            pkg_confidence = "exact"  # digest is immutable
        elif ref.tag == "latest" or not ref.tag:
            result.steps.append("[4/5] Trying GHCR packages API for :latest tag")
            pkg_result = resolve_ghcr_latest_via_packages(ref.namespace, ref.name)
            pkg_confidence = "approximate"  # :latest is mutable
        else:
            pkg_result = None
            pkg_confidence = None

        if pkg_result:
            repo_full = pkg_result["repo"]
            result.repo = f"https://github.com/{repo_full}"
            if pkg_result.get("commit"):
                commit = pkg_result["commit"]
                result.steps.append(f"[4/5] Packages API: repo={repo_full}, commit={commit[:12]}")
                result.commit = commit
                result.commit_url = f"{result.repo}/commit/{result.commit}"
                result.status = "resolved"
                result.resolution_method = "packages_api"
                result.confidence = pkg_confidence
                return result
            result.steps.append("[4/5] Packages API: found package but no resolvable tags")
            tags = pkg_result.get("tags", [])
            resolvable = [t for t in tags if t != "latest"]
            result.status = "repo_found_tag_not_matched" if resolvable else "no_tag"
            return result

    # Step 5: For :latest on any registry, try the latest GitHub release,
    # then fall back to the latest commit on the default branch
    if (ref.tag == "latest" or not ref.tag) and owner and repo_name:
        result.steps.append(f"[5/5] Trying latest GitHub release for {owner}/{repo_name}")
        release_result = get_latest_release_commit(owner, repo_name)
        if release_result:
            commit_sha, tag_name = release_result
            result.steps.append(f"[5/5] Latest release: tag={tag_name}, commit={commit_sha[:12]}")
            result.commit = commit_sha
            result.commit_url = f"{result.repo}/commit/{commit_sha}"
            result.status = "resolved"
            result.resolution_method = "latest_release"
            result.confidence = "approximate"
            return result

        # No releases — fall back to latest commit on default branch
        result.steps.append("[5/5] No release found, trying latest commit on default branch")
        latest_sha = get_latest_commit(owner, repo_name)
        if latest_sha:
            result.steps.append(f"[5/5] Latest commit: {latest_sha[:12]}")
            result.commit = latest_sha
            result.commit_url = f"{result.repo}/commit/{latest_sha}"
            result.status = "resolved"
            result.resolution_method = "latest_commit"
            result.confidence = "approximate"
            return result

    result.steps.append("[5/5] Could not resolve to a commit")
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
