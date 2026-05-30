import { describe, it, expect } from "vitest";
import { fmtBRL, fmtPct } from "@/lib/decimal";
import { buildCsv } from "@/lib/csv";
import { suggestRate } from "@/hooks/useBusinessRules";

describe("fmtBRL", () => {
  it("formats decimal string as BRL", () => {
    expect(fmtBRL("1234.56")).toBe("R$ 1.234,56");
  });
  it("handles zero", () => {
    expect(fmtBRL("0.00")).toBe("R$ 0,00");
  });
});

describe("fmtPct", () => {
  it("formats rate as percentage", () => {
    expect(fmtPct("0.0199")).toBe("1,99%");
  });
});

describe("buildCsv", () => {
  it("uses semicolon separator", () => {
    const csv = buildCsv(
      ["col1", "col2"],
      [{ col1: "a", col2: "b" }]
    );
    expect(csv).toContain(";");
    expect(csv).not.toMatch(/[^;],/);
  });
  it("first row is headers", () => {
    const csv = buildCsv(["A", "B"], [{ A: "1", B: "2" }]);
    expect(csv.split("\n")[0]).toBe("A;B");
  });
});

describe("suggestRate", () => {
  const curva = [
    { ate_meses: 24, taxa_mensal: "0.0159" },
    { ate_meses: 36, taxa_mensal: "0.0179" },
    { ate_meses: 48, taxa_mensal: "0.0199" },
  ];

  it("returns rate for exact match", () => {
    expect(suggestRate(24, curva)).toBe("0.0159");
  });
  it("returns rate for prazo within band", () => {
    expect(suggestRate(30, curva)).toBe("0.0179");
  });
  it("returns last rate for prazo beyond curve", () => {
    expect(suggestRate(72, curva)).toBe("0.0199");
  });
});
