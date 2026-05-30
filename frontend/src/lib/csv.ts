export function buildCsv(
  headers: string[],
  rows: Record<string, string | number>[]
): string {
  const escape = (v: string | number) => {
    const s = String(v);
    return s.includes(";") || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [
    headers.join(";"),
    ...rows.map((r) => headers.map((h) => escape(r[h] ?? "")).join(";")),
  ];
  return lines.join("\n");
}

export function downloadCsv(filename: string, content: string): void {
  const bom = "﻿";
  const blob = new Blob([bom + content], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
