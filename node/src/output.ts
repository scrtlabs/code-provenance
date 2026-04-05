import type { ImageResult } from "./types.js";

export function formatJson(results: ImageResult[]): string {
  return JSON.stringify(results, null, 2);
}

export function formatText(results: ImageResult[]): string {
  return results
    .map((r) => {
      const commit = r.commit ? r.commit.slice(0, 12) : "-";
      const repo = r.repo?.replace("https://", "") ?? "-";
      const confidence = r.confidence ?? "-";
      return (
        `${r.service}: ${r.image}\n` +
        `  repo:       ${repo}\n` +
        `  commit:     ${commit}\n` +
        `  status:     ${r.status}\n` +
        `  confidence: ${confidence}` +
        (r.commit_url ? `\n  url:        ${r.commit_url}` : "") +
        (r.matched_tag ? `\n  note:       commit is from matched tag '${r.matched_tag}', not the exact image digest` : "")
      );
    })
    .join("\n\n");
}
