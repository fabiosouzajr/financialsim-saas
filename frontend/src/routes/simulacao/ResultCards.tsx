import { fmtBRL, fmtPct } from "@/lib/decimal";
import type { SimulationSummary } from "./types";

interface Props {
  summary: SimulationSummary;
  loading?: boolean;
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white border rounded-lg p-4">
      <p className="text-xs text-zinc-500 mb-1">{label}</p>
      <p className="text-lg font-semibold text-zinc-900">{value}</p>
    </div>
  );
}

export function ResultCards({ summary, loading }: Props) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {Array.from({ length: 9 }).map((_, i) => (
          <div key={i} className="bg-zinc-100 animate-pulse rounded-lg h-20" />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
      <Card label="Parcela do financiamento" value={fmtBRL(summary.parcela_financiamento)} />
      <Card label="Parcela total 1º ano" value={fmtBRL(summary.parcela_total_primeiro_ano)} />
      <Card label="Parcela total após rateio" value={fmtBRL(summary.parcela_total_apos_rateio)} />
      <Card label="Valor financiado" value={fmtBRL(summary.valor_financiado)} />
      <Card label="Total pago" value={fmtBRL(summary.total_pago)} />
      <Card label="Total juros" value={fmtBRL(summary.total_juros)} />
      <Card label="% juros" value={`${parseFloat(summary.pct_juros).toFixed(2)}%`} />
      <Card
        label="CET a.m. / a.a."
        value={`${fmtPct(summary.cet_mensal)} / ${fmtPct(summary.cet_anual)}`}
      />
      <Card label="Total pago pelo cliente" value={fmtBRL(summary.total_pago_pelo_cliente)} />
      {parseFloat(summary.iof_total) > 0 && (
        <Card label="IOF total" value={fmtBRL(summary.iof_total)} />
      )}
    </div>
  );
}
