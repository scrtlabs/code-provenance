import type { ImageResult } from "./types.js";

/**
 * Format results as a JSON array.
 */
export function formatJson(results: ImageResult[]): string {
  return JSON.stringify(results, null, 2);
}

/**
 * Format results as a box-drawing table.
 */
export function formatTable(results: ImageResult[]): string {
  const columns = ["SERVICE", "IMAGE", "REPO", "COMMIT", "STATUS", "CONFIDENCE"];

  // Build rows
  const rows: string[][] = results.map((r) => [
    r.service,
    r.image,
    r.repo ? r.repo.replace("https://", "") : "-",
    r.commit ? r.commit.slice(0, 12) : "-",
    r.status,
    r.confidence || "-",
  ]);

  // Calculate column widths
  const widths = columns.map((col, i) => {
    const dataMax = rows.reduce((max, row) => Math.max(max, row[i].length), 0);
    return Math.max(col.length, dataMax);
  });

  const pad = (s: string, w: number) => s + " ".repeat(w - s.length);

  // Build lines
  const topBorder =
    "┌" + widths.map((w) => "─".repeat(w + 2)).join("┬") + "┐";
  const headerSep =
    "├" + widths.map((w) => "─".repeat(w + 2)).join("┼") + "┤";
  const bottomBorder =
    "└" + widths.map((w) => "─".repeat(w + 2)).join("┴") + "┘";

  const headerRow =
    "│" +
    columns.map((col, i) => " " + pad(col, widths[i]) + " ").join("│") +
    "│";

  const dataRows = rows.map(
    (row) =>
      "│" +
      row.map((cell, i) => " " + pad(cell, widths[i]) + " ").join("│") +
      "│"
  );

  return [topBorder, headerRow, headerSep, ...dataRows, bottomBorder].join(
    "\n"
  );
}
