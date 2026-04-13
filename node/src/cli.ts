#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { parseCompose, parseImageRef } from "./composeParser.js";
import { resolveImage } from "./resolver.js";
import { formatJson, formatText } from "./output.js";

/**
 * Extract YAML content from HTML-wrapped SecretVM response.
 */
function extractYamlFromHtml(text: string): string {
  const match = text.match(/<pre[^>]*>([\s\S]*)<\/pre>/);
  if (match) {
    text = match[1];
  }
  return text
    // Decode numeric HTML entities (&#NNN; and &#xHHH;)
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => String.fromCodePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)))
    // Decode named HTML entities
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    // Strip zero-width characters
    .replace(/[\u200b\u200c\u200d\ufeff]/g, "")
    .trim();
}

function printHelp(): void {
  console.log(`usage: code-provenance [-h] [--version] [--json] [--image IMAGE] [--secretvm URL] [compose_file]

Resolve Docker images to their source code commits on GitHub.

positional arguments:
  compose_file       Path to docker-compose file (default: docker-compose.yml)

options:
  -h, --help         show this help message and exit
  --version          show program's version number and exit
  --image IMAGE      Resolve a single image reference instead of a compose file
  --secretvm URL     Fetch docker-compose from a SecretVM at URL (port 29343)
  --json             Output results as JSON
  -v, --verbose      Show resolution steps

environment:
  GITHUB_TOKEN       GitHub personal access token (recommended). Enables digest
                     and :latest resolution, and raises API rate limit to 5000/hr.
                     Create one at https://github.com/settings/tokens with
                     read:packages scope. Set with: export GITHUB_TOKEN=ghp_...`);
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);

  if (args.includes("-h") || args.includes("--help")) {
    printHelp();
    return 0;
  }

  if (args.includes("--version")) {
    console.log("code-provenance 0.1.13");
    return 0;
  }

  const jsonOutput = args.includes("--json");
  const verbose = args.includes("--verbose") || args.includes("-v");

  const imageIdx = args.indexOf("--image");
  const imageArg = imageIdx !== -1 ? args[imageIdx + 1] : undefined;

  const secretvmIdx = args.indexOf("--secretvm");
  const secretvmArg = secretvmIdx !== -1 ? args[secretvmIdx + 1] : undefined;

  // Show help if no mode specified and no docker-compose.yml exists
  if (!imageArg && !secretvmArg) {
    const positionalArgs = args.filter(
      (a) => a !== "--json" && a !== "--verbose" && a !== "-v"
    );
    if (!positionalArgs[0] && !existsSync("docker-compose.yml")) {
      printHelp();
      return 0;
    }
  }

  if (!process.env.GITHUB_TOKEN) {
    // Try to auto-detect from gh CLI
    try {
      const token = execFileSync("gh", ["auth", "token"], {
        timeout: 5000,
        encoding: "utf-8",
        stdio: ["ignore", "pipe", "ignore"],
      }).trim();
      if (token) {
        process.env.GITHUB_TOKEN = token;
        console.error("Using GITHUB_TOKEN from gh CLI.");
      }
    } catch {
      // gh not installed or not logged in
    }
  }

  if (!process.env.GITHUB_TOKEN) {
    console.error(
      "Warning: GITHUB_TOKEN is not set. Some resolution methods (digest, :latest) will not work.\n" +
      "Set it with: export GITHUB_TOKEN=ghp_your_token_here\n" +
      "Or install gh CLI and run: gh auth login\n"
    );
  }

  let results;

  if (secretvmArg) {
    // SecretVM mode — fetch docker-compose from the VM
    let url = secretvmArg.replace(/\/+$/, "");
    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      url = `https://${url}`;
    }
    const composeUrl = `${url}:29343/docker-compose`;
    console.error(`Fetching docker-compose from ${composeUrl} ...`);

    let yamlContent: string;
    try {
      // SecretVMs use self-signed certs — temporarily disable TLS verification
      const prevTls = process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      process.env.NODE_TLS_REJECT_UNAUTHORIZED = "0";
      const resp = await fetch(composeUrl, {
        signal: AbortSignal.timeout(15000),
      });
      if (prevTls === undefined) {
        delete process.env.NODE_TLS_REJECT_UNAUTHORIZED;
      } else {
        process.env.NODE_TLS_REJECT_UNAUTHORIZED = prevTls;
      }
      if (!resp.ok) {
        console.error(`Error: failed to fetch docker-compose from ${composeUrl} — HTTP ${resp.status}`);
        return 1;
      }
      yamlContent = extractYamlFromHtml(await resp.text());
    } catch (err) {
      console.error(`Error: failed to fetch docker-compose from ${composeUrl} — ${err instanceof Error ? err.message : err}`);
      return 1;
    }

    let services: Array<[string, string]>;
    try {
      services = parseCompose(yamlContent);
    } catch (err) {
      console.error(`Error: failed to parse docker-compose from ${composeUrl} — ${err instanceof Error ? err.message : err}`);
      return 1;
    }

    if (services.length === 0) {
      console.error("No services with images found in the SecretVM docker-compose.");
      return 1;
    }

    results = await Promise.all(
      services.map(([serviceName, imageString]) => {
        const ref = parseImageRef(imageString);
        return resolveImage(serviceName, ref);
      })
    );
  } else if (imageArg) {
    // Single image mode
    const ref = parseImageRef(imageArg);
    results = [await resolveImage("image", ref)];
  } else {
    // Compose file mode
    const positionalArgs = args.filter((a) => a !== "--json" && a !== "--verbose" && a !== "-v");
    const composeFile = positionalArgs[0] || "docker-compose.yml";

    if (!existsSync(composeFile)) {
      console.error(`Error: ${composeFile} not found`);
      return 1;
    }

    const yamlContent = readFileSync(composeFile, "utf-8");

    let services: Array<[string, string]>;
    try {
      services = parseCompose(yamlContent);
    } catch (err) {
      console.error(`Error: failed to parse ${composeFile} — ${err instanceof Error ? err.message : err}`);
      return 1;
    }

    if (services.length === 0) {
      console.error("No services with images found. Is this a valid docker-compose file?");
      return 1;
    }

    // Resolve all images in parallel
    results = await Promise.all(
      services.map(([serviceName, imageString]) => {
        const ref = parseImageRef(imageString);
        return resolveImage(serviceName, ref);
      })
    );
  }

  if (verbose) {
    for (const r of results) {
      console.error(`\nResolving ${r.image} ...`);
      for (const step of r.steps) {
        console.error(`  ${step}`);
      }
      console.error(
        `  → ${r.status}` +
          (r.status === "resolved"
            ? ` (${r.resolution_method}, ${r.confidence})`
            : "")
      );
    }
    console.error();
  }

  if (jsonOutput) {
    console.log(formatJson(results));
  } else {
    console.log(formatText(results));
  }

  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
