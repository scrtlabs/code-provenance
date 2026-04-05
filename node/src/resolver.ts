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
): Promise<[string | null, string | null]> {
  if (ref.registry === "ghcr.io") {
    return [ref.namespace, ref.name];
  }

  if (ref.registry === "docker.io") {
    const hubResult = await inferRepoFromDockerhub(ref.namespace, ref.name);
    if (hubResult) return hubResult;
  }

  return [null, null];
}

/**
 * Run the resolution chain for a single image.
 */
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
    steps: [],
  };

  // Step 1: Check OCI labels
  result.steps.push(`[1/5] Fetching OCI labels from ${ref.registry}/${ref.namespace}/${ref.name}:${ref.tag}`);
  const labels = await fetchOciLabels(ref);
  const source = labels["org.opencontainers.image.source"];
  const revision = labels["org.opencontainers.image.revision"];
  if (source && revision) {
    result.steps.push(`[1/5] Found OCI labels: source=${source}, revision=${revision.slice(0, 12)}`);
    result.repo = source;
    result.commit = revision;
    result.commit_url = `${source}/commit/${revision}`;
    result.status = "resolved";
    result.resolution_method = "oci_labels";
    result.confidence = ref.tag === "latest" ? "approximate" : "exact";
    return result;
  } else {
    result.steps.push("[1/5] No OCI labels found");
  }

  // Step 2: Infer repo
  result.steps.push(`[2/5] Inferring GitHub repo from ${ref.registry}/${ref.namespace}/${ref.name}`);
  const [owner, repoName] = await inferRepo(ref);
  if (owner && repoName) {
    result.steps.push(`[2/5] Repo inferred: ${owner}/${repoName}`);
    result.repo = `https://github.com/${owner}/${repoName}`;
  } else {
    result.steps.push("[2/5] Could not infer GitHub repo");
    result.status = "repo_not_found";
    return result;
  }

  // Check if tag is a commit SHA
  if (COMMIT_SHA_RE.test(ref.tag)) {
    result.steps.push("[2/5] Tag is a commit SHA, using directly");
    result.commit = ref.tag;
    result.commit_url = `${result.repo}/commit/${ref.tag}`;
    result.status = "resolved";
    result.resolution_method = "commit_sha_tag";
    result.confidence = "exact";
    return result;
  }

  // Step 3: Tag-to-commit resolution
  if (isResolvableTag(ref.tag)) {
    result.steps.push(`[3/5] Matching tag "${ref.tag}" against git tags in ${owner}/${repoName}`);
    const tagResult = await resolveTagToCommit(owner, repoName, ref.tag);
    if (tagResult) {
      const [commitSha, isExact] = tagResult;
      if (isExact) {
        result.steps.push(`[3/5] Exact tag match: ${commitSha.slice(0, 12)}`);
      } else {
        result.steps.push(`[3/5] Prefix match (e.g. v2.10 -> v2.10.x): ${commitSha.slice(0, 12)}`);
      }
      result.commit = commitSha;
      result.commit_url = `${result.repo}/commit/${commitSha}`;
      result.status = "resolved";
      result.resolution_method = "tag_match";
      result.confidence = isExact ? "exact" : "approximate";
      return result;
    }
    result.steps.push("[3/5] No matching git tag found");
    result.status = "repo_found_tag_not_matched";
    return result;
  }

  // Step 4: For GHCR images, try the packages API for digest or :latest
  if (ref.registry === "ghcr.io") {
    let pkgResult: { repo: string; commit: string | null; tags: string[] } | null = null;
    let pkgConfidence: string | null = null;

    if (!process.env.GITHUB_TOKEN) {
      result.steps.push("[4/5] GITHUB_TOKEN not set — skipping packages API (required for digest/:latest resolution)");
      if (DIGEST_RE.test(ref.tag) || ref.tag === "latest" || !ref.tag) {
        result.status = "error_no_token";
        return result;
      }
    } else if (DIGEST_RE.test(ref.tag)) {
      result.steps.push(`[4/5] Trying GHCR packages API for digest ${ref.tag.slice(0, 20)}...`);
      pkgResult = await resolveGhcrDigestViaPackages(
        ref.namespace,
        ref.name,
        ref.tag
      );
      pkgConfidence = "exact";
    } else if (ref.tag === "latest" || !ref.tag) {
      result.steps.push("[4/5] Trying GHCR packages API for :latest tag");
      pkgResult = await resolveGhcrLatestViaPackages(ref.namespace, ref.name);
      pkgConfidence = "approximate";
    }

    if (pkgResult) {
      const repoFull = pkgResult.repo;
      result.repo = `https://github.com/${repoFull}`;
      if (pkgResult.commit) {
        const commit = pkgResult.commit;
        result.steps.push(`[4/5] Packages API: repo=${repoFull}, commit=${commit.slice(0, 12)}`);
        result.commit = commit;
        result.commit_url = `${result.repo}/commit/${result.commit}`;
        result.status = "resolved";
        result.resolution_method = "packages_api";
        result.confidence = pkgConfidence;
        return result;
      }
      result.steps.push("[4/5] Packages API: found package but no resolvable tags");
      const tags = pkgResult.tags ?? [];
      const resolvable = tags.filter((t) => t !== "latest");
      result.status = resolvable.length > 0 ? "repo_found_tag_not_matched" : "no_tag";
      return result;
    }
  }

  // Step 5: For :latest on any registry, try the latest GitHub release,
  // then fall back to the latest commit on the default branch
  if ((ref.tag === "latest" || !ref.tag) && owner && repoName) {
    result.steps.push(`[5/5] Trying latest GitHub release for ${owner}/${repoName}`);
    const releaseResult = await getLatestReleaseCommit(owner, repoName);
    if (releaseResult) {
      const [commitSha, tagName] = releaseResult;
      result.steps.push(`[5/5] Latest release: tag=${tagName}, commit=${commitSha.slice(0, 12)}`);
      result.commit = commitSha;
      result.commit_url = `${result.repo}/commit/${commitSha}`;
      result.status = "resolved";
      result.resolution_method = "latest_release";
      result.confidence = "approximate";
      return result;
    }

    // No releases - fall back to latest commit on default branch
    result.steps.push("[5/5] No release found, trying latest commit on default branch");
    const latestSha = await getLatestCommit(owner, repoName);
    if (latestSha) {
      result.steps.push(`[5/5] Latest commit: ${latestSha.slice(0, 12)}`);
      result.commit = latestSha;
      result.commit_url = `${result.repo}/commit/${latestSha}`;
      result.status = "resolved";
      result.resolution_method = "latest_commit";
      result.confidence = "approximate";
      return result;
    }
  }

  result.steps.push("[5/5] Could not resolve to a commit");
  result.status = "no_tag";
  return result;
}
