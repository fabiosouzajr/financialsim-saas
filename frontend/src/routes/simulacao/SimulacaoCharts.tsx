import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer,
} from "recharts";
import type { AmortizationRowOut } from "./types";

interface Props {
  rows: AmortizationRowOut[];
}

export function SimulacaoCharts({ rows }: Props) {
  const barData = rows.map((r) => ({
    n: r.numero_parcela,
    juros: parseFloat(r.juros),
    amortizacao: parseFloat(r.amortizacao),
    extras: parseFloat(r.extras_total),
  }));

  const saldoData = rows.map((r) => ({
    n: r.numero_parcela,
    saldo: parseFloat(r.saldo_devedor),
  }));

  const parcelaData = rows.map((r) => ({
    n: r.numero_parcela,
    parcela_total: parseFloat(r.parcela_total),
    parcela_base: parseFloat(r.parcela),
  }));

  return (
    <div className="space-y-8">
      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Composição da parcela
        </h4>
        <ResponsiveContainer width="100%" height={200}>
          <BarChart data={barData} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={50} />
            <Tooltip formatter={(v: unknown) => `R$ ${Number(v).toFixed(2)}`} />
            <Legend iconSize={10} />
            <Bar dataKey="amortizacao" name="Amortização" stackId="a" fill="#18181b" />
            <Bar dataKey="juros" name="Juros" stackId="a" fill="#a1a1aa" />
            <Bar dataKey="extras" name="Extras" stackId="a" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Saldo devedor
        </h4>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={saldoData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
            <Tooltip formatter={(v: unknown) => `R$ ${Number(v).toFixed(2)}`} />
            <Line type="monotone" dataKey="saldo" stroke="#18181b" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <h4 className="text-xs font-semibold text-zinc-500 uppercase mb-3">
          Parcela total ao longo do tempo
        </h4>
        <ResponsiveContainer width="100%" height={160}>
          <LineChart data={parcelaData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" />
            <XAxis dataKey="n" tick={{ fontSize: 10 }} tickLine={false} />
            <YAxis tick={{ fontSize: 10 }} tickLine={false} axisLine={false} width={60} />
            <Tooltip formatter={(v: unknown) => `R$ ${Number(v).toFixed(2)}`} />
            <Line
              type="stepAfter" dataKey="parcela_total" name="Total" stroke="#3b82f6"
              dot={false} strokeWidth={2}
            />
            <Line
              type="monotone" dataKey="parcela_base" name="Financiamento"
              stroke="#a1a1aa" dot={false} strokeWidth={1} strokeDasharray="4 2"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
