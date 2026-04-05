function githubHeaders(): Record<string, string> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
  };
  const token = process.env.GITHUB_TOKEN;
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  return headers;
}

function normalizeTag(tag: string): string {
  return tag.replace(/^v+/, "");
}

function isPrefixMatch(imageTag: string, gitTag: string): boolean {
  const normImage = normalizeTag(imageTag);
  const normGit = normalizeTag(gitTag);
  return normGit.startsWith(normImage + ".");
}

function parseVersionTuple(tag: string): number[] | null {
  let norm = normalizeTag(tag);
  // Strip pre-release suffixes like -rc1, -beta2
  norm = norm.split(/[-+]/)[0];
  const parts = norm.split(".");
  try {
    const nums = parts.map((p) => {
      const n = parseInt(p, 10);
      if (isNaN(n)) throw new Error();
      return n;
    });
    return nums;
  } catch {
    return null;
  }
}

function compareVersions(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    const av = a[i] ?? 0;
    const bv = b[i] ?? 0;
    if (av !== bv) return av - bv;
  }
  return 0;
}

/**
 * Parse the Link header for pagination.
 * Returns the "next" URL or null.
 */
function parseNextLink(linkHeader: string | null): string | null {
  if (!linkHeader) return null;
  const match = linkHeader.match(/<([^>]+)>;\s*rel="next"/);
  return match ? match[1] : null;
}

interface GitTag {
  name: string;
  commit: { sha: string };
}

/**
 * Resolve an image tag to a commit SHA by matching against git tags.
 * Tries exact match first, then prefix match (e.g., v2.10 -> highest v2.10.x).
 * Returns [commit_sha, is_exact_match] or null.
 */
export async function resolveTagToCommit(
  owner: string,
  repo: string,
  tag: string
): Promise<[string, boolean] | null> {
  const headers = githubHeaders();
  let url: string | null =
    `https://api.github.com/repos/${owner}/${repo}/tags?per_page=100`;

  const prefixCandidates: [number[], string][] = [];

  while (url) {
    const resp = await fetch(url, {
      headers,
      signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) return null;

    const gitTags: GitTag[] = await resp.json() as GitTag[];

    for (const gitTag of gitTags) {
      const name = gitTag.name;
      // Exact match (with/without v prefix)
      if (
        name === tag ||
        name === `v${tag}` ||
        normalizeTag(name) === normalizeTag(tag)
      ) {
        return [gitTag.commit.sha, true];
      }

      // Collect prefix match candidates
      if (isPrefixMatch(tag, name)) {
        const version = parseVersionTuple(name);
        if (version !== null) {
          prefixCandidates.push([version, gitTag.commit.sha]);
        }
      }
    }

    url = parseNextLink(resp.headers.get("link"));
  }

  // Return the highest version among prefix matches
  if (prefixCandidates.length > 0) {
    prefixCandidates.sort((a, b) => compareVersions(b[0], a[0]));
    return [prefixCandidates[0][1], false];
  }

  return null;
}

/**
 * Get the latest commit on a specific branch.
 * Returns commit SHA or null if branch doesn't exist.
 */
export async function getBranchCommit(
  owner: string,
  repo: string,
  branch: string
): Promise<string | null> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/branches/${encodeURIComponent(branch)}`,
      { headers, signal: AbortSignal.timeout(10000) }
    );
    if (!resp.ok) return null;
    const data = (await resp.json()) as { commit?: { sha?: string } };
    return data.commit?.sha ?? null;
  } catch {
    return null;
  }
}

/**
 * Get the commit SHA of the latest GitHub release.
 * Returns [commit_sha, tag_name] or null.
 */
export async function getLatestReleaseCommit(
  owner: string,
  repo: string
): Promise<[string, string] | null> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/releases/latest`,
      { headers, signal: AbortSignal.timeout(10000) }
    );
    if (!resp.ok) return null;
    const data = (await resp.json()) as { tag_name?: string };
    const tagName = data.tag_name;
    if (!tagName) return null;

    const tagResult = await resolveTagToCommit(owner, repo, tagName);
    if (tagResult) {
      return [tagResult[0], tagName];
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Get the latest commit SHA on the default branch.
 */
export async function getLatestCommit(
  owner: string,
  repo: string
): Promise<string | null> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}/commits?per_page=1`,
      { headers, signal: AbortSignal.timeout(10000) }
    );
    if (!resp.ok) return null;
    const commits = (await resp.json()) as { sha: string }[];
    if (commits.length > 0) return commits[0].sha;
  } catch {
    // ignore
  }
  return null;
}

/**
 * Check if a GitHub repo exists.
 */
export async function checkGithubRepoExists(
  owner: string,
  repo: string
): Promise<boolean> {
  const headers = githubHeaders();
  try {
    const resp = await fetch(
      `https://api.github.com/repos/${owner}/${repo}`,
      { headers, signal: AbortSignal.timeout(10000) }
    );
    return resp.status === 200;
  } catch {
    return false;
  }
}

interface PackageVersionResult {
  repo: string;
  commit: string | null;
  tags: string[];
}

/**
 * Find a GHCR package version by digest or tag via the GitHub Packages API.
 */
async function findGhcrPackageVersion(
  owner: string,
  packageName: string,
  options: { matchDigest?: string; matchTag?: string }
): Promise<PackageVersionResult | null> {
  const headers = githubHeaders();
  if (!headers.Authorization) return null;

  for (const entityType of ["orgs", "users"]) {
    const pkgBase = `https://api.github.com/${entityType}/${owner}/packages/container/${packageName}`;

    // Get package metadata for source repo
    let fullName: string | undefined;
    try {
      const pkgResp = await fetch(pkgBase, {
        headers,
        signal: AbortSignal.timeout(10000),
      });
      if (pkgResp.status === 403) return null;
      if (!pkgResp.ok) continue;
      const pkgData = await pkgResp.json();
      fullName = (pkgData as any)?.repository?.full_name;
      if (!fullName) continue;
    } catch {
      continue;
    }

    // Search versions
    let versionsUrl: string | null = `${pkgBase}/versions?per_page=50`;
    try {
      while (versionsUrl) {
        const resp = await fetch(versionsUrl, {
          headers,
          signal: AbortSignal.timeout(10000),
        });
        if (!resp.ok) break;

        const versions = (await resp.json()) as any[];

        for (const version of versions) {
          const name: string = version.name ?? "";
          const metadata = version.metadata?.container ?? {};
          const tags: string[] = metadata.tags ?? [];

          // Match by digest (version name is the digest)
          if (options.matchDigest && name !== options.matchDigest) {
            if (!options.matchTag) continue;
          }
          // Match by tag
          if (options.matchTag && !tags.includes(options.matchTag)) continue;

          // Found matching version - resolve tags to a commit
          const [repoOwner, repoName] = fullName!.split("/", 2);
          const resolvableTags = tags.filter((t) => t !== "latest");
          for (const t of resolvableTags) {
            const tagResult = await resolveTagToCommit(repoOwner, repoName, t);
            if (tagResult) {
              return { repo: fullName!, commit: tagResult[0], tags };
            }
          }

          return { repo: fullName!, commit: null, tags };
        }

        versionsUrl = parseNextLink(resp.headers.get("link"));
      }
    } catch {
      continue;
    }
  }

  return null;
}

/**
 * Find the commit for a GHCR image by its digest.
 */
export async function resolveGhcrDigestViaPackages(
  owner: string,
  packageName: string,
  digest: string
): Promise<PackageVersionResult | null> {
  return findGhcrPackageVersion(owner, packageName, { matchDigest: digest });
}

/**
 * Find the commit for a GHCR image's :latest tag.
 */
export async function resolveGhcrLatestViaPackages(
  owner: string,
  packageName: string
): Promise<PackageVersionResult | null> {
  return findGhcrPackageVersion(owner, packageName, { matchTag: "latest" });
}

/**
 * Try to find the GitHub repo for a Docker Hub image.
 */
export async function inferRepoFromDockerhub(
  namespace: string,
  name: string
): Promise<[string, string] | null> {
  // For official images (library/X), try the image name as org/repo directly
  if (namespace === "library") {
    if (await checkGithubRepoExists(name, name)) {
      return [name, name];
    }
  }

  // For namespaced images, try namespace/name on GitHub
  if (namespace !== "library") {
    if (await checkGithubRepoExists(namespace, name)) {
      return [namespace, name];
    }
  }

  // Fall back to scraping Docker Hub description for GitHub links
  try {
    const resp = await fetch(
      `https://hub.docker.com/v2/repositories/${namespace}/${name}`,
      { signal: AbortSignal.timeout(10000) }
    );
    if (!resp.ok) return null;

    const data = (await resp.json()) as {
      full_description?: string;
      description?: string;
    };
    const text =
      (data.full_description || "") + " " + (data.description || "");
    const match = text.match(/https?:\/\/github\.com\/([\w.-]+)\/([\w.-]+)/);
    if (match) {
      return [match[1], match[2]];
    }
  } catch {
    // ignore
  }

  return null;
}
