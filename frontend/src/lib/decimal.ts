export function fmtBRL(value: string | number): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return n
    .toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    .replace(/\u00A0/g, " ");
}

export function fmtPct(value: string | number, decimals = 2): string {
  const n = typeof value === "string" ? parseFloat(value) : value;
  return (n * 100).toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }) + "%";
}

export function fmtRate(value: string | number): string {
  return fmtPct(value, 4);
}

export function parseBRL(formatted: string): string {
  return formatted.replace(/\./g, "").replace(",", ".");
}
