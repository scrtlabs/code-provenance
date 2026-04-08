#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { parseCompose, parseImageRef } from "./composeParser.js";
import { resolveImage } from "./resolver.js";
import { formatJson, formatText } from "./output.js";

function printHelp(): void {
  console.log(`usage: code-provenance [-h] [--json] [--image IMAGE] [compose_file]

Resolve Docker images to their source code commits on GitHub.

positional arguments:
  compose_file     Path to docker-compose file (default: docker-compose.yml)

options:
  -h, --help       show this help message and exit
  --image IMAGE    Resolve a single image reference instead of a compose file
  --json           Output results as JSON
  -v, --verbose    Show resolution steps`);
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);

  if (args.includes("-h") || args.includes("--help")) {
    printHelp();
    return 0;
  }

  const jsonOutput = args.includes("--json");
  const verbose = args.includes("--verbose") || args.includes("-v");

  const imageIdx = args.indexOf("--image");
  const imageArg = imageIdx !== -1 ? args[imageIdx + 1] : undefined;

  if (!process.env.GITHUB_TOKEN) {
    console.error(
      "Warning: GITHUB_TOKEN is not set. Some resolution methods (digest, :latest) will not work.\n" +
      "Set it with: export GITHUB_TOKEN=ghp_your_token_here\n" +
      "Create a token at https://github.com/settings/tokens with read:packages scope.\n"
    );
  }

  let results;

  if (imageArg) {
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
