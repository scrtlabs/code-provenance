import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { parseImageRef, parseCompose } from "./composeParser.js";

describe("parseImageRef", () => {
  it("parses ghcr with tag", () => {
    const ref = parseImageRef("ghcr.io/excalidraw/excalidraw:v0.17.3");
    assert.equal(ref.registry, "ghcr.io");
    assert.equal(ref.namespace, "excalidraw");
    assert.equal(ref.name, "excalidraw");
    assert.equal(ref.tag, "v0.17.3");
  });

  it("parses docker hub official image", () => {
    const ref = parseImageRef("postgres:16");
    assert.equal(ref.registry, "docker.io");
    assert.equal(ref.namespace, "library");
    assert.equal(ref.name, "postgres");
    assert.equal(ref.tag, "16");
  });

  it("parses docker hub namespaced image", () => {
    const ref = parseImageRef("traefik/whoami:v1.10.3");
    assert.equal(ref.registry, "docker.io");
    assert.equal(ref.namespace, "traefik");
    assert.equal(ref.name, "whoami");
    assert.equal(ref.tag, "v1.10.3");
  });

  it("defaults to latest when no tag", () => {
    const ref = parseImageRef("nginx");
    assert.equal(ref.registry, "docker.io");
    assert.equal(ref.namespace, "library");
    assert.equal(ref.name, "nginx");
    assert.equal(ref.tag, "latest");
  });

  it("handles digest reference", () => {
    const ref = parseImageRef(
      "ghcr.io/org/app@sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    );
    assert.equal(ref.registry, "ghcr.io");
    assert.equal(ref.namespace, "org");
    assert.equal(ref.name, "app");
    assert.equal(
      ref.tag,
      "sha256:abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    );
  });
});

describe("parseCompose", () => {
  it("extracts services with image field", () => {
    const yaml = `
services:
  web:
    image: nginx:latest
  api:
    build: .
  db:
    image: postgres:16
`;
    const result = parseCompose(yaml);
    assert.equal(result.length, 2);
    assert.deepEqual(result[0], ["web", "nginx:latest"]);
    assert.deepEqual(result[1], ["db", "postgres:16"]);
  });

  it("handles empty services", () => {
    const yaml = `
services: {}
`;
    const result = parseCompose(yaml);
    assert.equal(result.length, 0);
  });
});
