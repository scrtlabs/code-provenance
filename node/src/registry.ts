import type { ImageRef } from "./types.js";

/**
 * Get an anonymous pull token from an OCI registry.
 */
export async function getRegistryToken(
  registry: string,
  repoPath: string
): Promise<string | null> {
  let url: string;

  if (registry === "ghcr.io") {
    url = `https://ghcr.io/token?scope=repository:${encodeURIComponent(repoPath)}:pull`;
  } else if (registry === "docker.io") {
    url =
      `https://auth.docker.io/token?service=registry.docker.io` +
      `&scope=repository:${encodeURIComponent(repoPath)}:pull`;
  } else {
    return null;
  }

  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(10000) });
    if (!resp.ok) return null;
    const data = (await resp.json()) as { token?: string };
    return data.token ?? null;
  } catch {
    return null;
  }
}

function registryBaseUrl(registry: string): string {
  if (registry === "docker.io") return "https://registry-1.docker.io";
  return `https://${registry}`;
}

const MANIFEST_ACCEPT = [
  "application/vnd.docker.distribution.manifest.v2+json",
  "application/vnd.oci.image.manifest.v1+json",
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.oci.image.index.v1+json",
].join(", ");

const INDEX_MEDIA_TYPES = new Set([
  "application/vnd.docker.distribution.manifest.list.v2+json",
  "application/vnd.oci.image.index.v1+json",
]);

interface ManifestPlatform {
  os?: string;
  architecture?: string;
}

interface ManifestEntry {
  digest: string;
  platform?: ManifestPlatform;
}

/**
 * Resolve a manifest reference to a config blob digest, handling multi-arch indexes.
 */
async function resolveManifestToConfigDigest(
  baseUrl: string,
  repoPath: string,
  reference: string,
  token: string,
  depth: number = 0
): Promise<string | null> {
  try {
    const resp = await fetch(
      `${baseUrl}/v2/${repoPath}/manifests/${reference}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: MANIFEST_ACCEPT,
        },
        signal: AbortSignal.timeout(10000),
      }
    );
    if (!resp.ok) return null;
    const data = await resp.json();
    const mediaType: string = data.mediaType ?? "";

    // If it's an index/manifest list, pick amd64/linux
    if (INDEX_MEDIA_TYPES.has(mediaType)) {
      const manifests: ManifestEntry[] = data.manifests ?? [];
      let platformDigest: string | null = null;

      // Try amd64/linux first
      for (const m of manifests) {
        const platform = m.platform ?? {};
        if (platform.os === "unknown") continue;
        if (platform.architecture === "amd64" && platform.os === "linux") {
          platformDigest = m.digest;
          break;
        }
      }

      // Fall back to first non-attestation manifest
      if (!platformDigest) {
        for (const m of manifests) {
          if (m.platform?.os !== "unknown") {
            platformDigest = m.digest;
            break;
          }
        }
      }

      if (!platformDigest) return null;
      if (depth >= 3) return null;
      return resolveManifestToConfigDigest(baseUrl, repoPath, platformDigest, token, depth + 1);
    }

    // Single manifest - extract config digest
    return data.config?.digest ?? null;
  } catch {
    return null;
  }
}

/**
 * Fetch OCI labels from an image's config blob without pulling the image.
 */
export async function fetchOciLabels(
  ref: ImageRef
): Promise<Record<string, string>> {
  const repoPath = `${ref.namespace}/${ref.name}`;
  const token = await getRegistryToken(ref.registry, repoPath);
  if (!token) return {};

  const baseUrl = registryBaseUrl(ref.registry);
  const configDigest = await resolveManifestToConfigDigest(
    baseUrl,
    repoPath,
    ref.tag,
    token
  );
  if (!configDigest) return {};

  try {
    const resp = await fetch(`${baseUrl}/v2/${repoPath}/blobs/${configDigest}`, {
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.docker.container.image.v1+json",
      },
      redirect: "follow",
      signal: AbortSignal.timeout(10000),
    });
    if (!resp.ok) return {};
    const data = await resp.json();
    return data.config?.Labels ?? {};
  } catch {
    return {};
  }
}
