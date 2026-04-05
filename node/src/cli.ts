#!/usr/bin/env node

import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { parseCompose, parseImageRef } from "./composeParser.js";
import { resolveImage } from "./resolver.js";
import { formatJson, formatTable } from "./output.js";

function printHelp(): void {
  console.log(`usage: code-provenance [-h] [--json] [compose_file]

Resolve Docker images to their source code commits on GitHub.

positional arguments:
  compose_file  Path to docker-compose file (default: docker-compose.yml)

options:
  -h, --help    show this help message and exit
  --json        Output results as JSON`);
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);

  if (args.includes("-h") || args.includes("--help")) {
    printHelp();
    return 0;
  }

  const jsonOutput = args.includes("--json");
  const positionalArgs = args.filter((a) => a !== "--json");
  const composeFile = positionalArgs[0] || "docker-compose.yml";

  if (!existsSync(composeFile)) {
    console.error(`Error: ${composeFile} not found`);
    return 1;
  }

  const yamlContent = readFileSync(composeFile, "utf-8");
  const services = parseCompose(yamlContent);

  if (services.length === 0) {
    console.error("No services with images found.");
    return 0;
  }

  // Resolve all images in parallel
  const results = await Promise.all(
    services.map(([serviceName, imageString]) => {
      const ref = parseImageRef(imageString);
      return resolveImage(serviceName, ref);
    })
  );

  if (jsonOutput) {
    console.log(formatJson(results));
  } else {
    console.log(formatTable(results));
  }

  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error(err);
    process.exit(1);
  });
