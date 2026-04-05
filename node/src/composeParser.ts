import YAML from "yaml";
import type { ImageRef } from "./types.js";

/**
 * Parse a Docker image string into an ImageRef.
 */
export function parseImageRef(imageString: string): ImageRef {
  const raw = imageString;
  let tag: string;
  let namePart: string;

  // Handle digest references (image@sha256:...)
  if (imageString.includes("@")) {
    const atIdx = imageString.indexOf("@");
    namePart = imageString.slice(0, atIdx);
    tag = imageString.slice(atIdx + 1);
  } else {
    const lastSegment = imageString.split("/").pop()!;
    if (lastSegment.includes(":")) {
      const colonPos = imageString.lastIndexOf(":");
      tag = imageString.slice(colonPos + 1);
      namePart = imageString.slice(0, colonPos);
    } else {
      tag = "latest";
      namePart = imageString;
    }
  }

  // Determine registry
  const parts = namePart.split("/");
  let registry: string;
  let remaining: string[];

  if (parts.length >= 2 && (parts[0].includes(".") || parts[0].includes(":"))) {
    registry = parts[0];
    remaining = parts.slice(1);
  } else {
    registry = "docker.io";
    remaining = parts;
  }

  // Determine namespace and name
  let namespace: string;
  let name: string;

  if (remaining.length === 1) {
    namespace = "library";
    name = remaining[0];
  } else if (remaining.length === 2) {
    namespace = remaining[0];
    name = remaining[1];
  } else {
    namespace = remaining[0];
    name = remaining.slice(1).join("/");
  }

  return { registry, namespace, name, tag, raw };
}

/**
 * Parse docker-compose YAML and return list of [serviceName, imageString] pairs.
 */
export function parseCompose(yamlContent: string): [string, string][] {
  const data = YAML.parse(yamlContent);
  const services = data?.services ?? {};
  const results: [string, string][] = [];

  for (const [serviceName, serviceConfig] of Object.entries(services)) {
    if (
      serviceConfig !== null &&
      typeof serviceConfig === "object" &&
      "image" in (serviceConfig as Record<string, unknown>)
    ) {
      results.push([serviceName, (serviceConfig as Record<string, unknown>).image as string]);
    }
  }

  return results;
}
