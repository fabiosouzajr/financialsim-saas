import { fmtBRL } from "@/lib/decimal";
import { buildCsv, downloadCsv } from "@/lib/csv";
import type { AmortizationRowOut } from "./types";

interface Props {
  rows: AmortizationRowOut[];
  codigo?: string;
}

const CSV_HEADERS = [
  "numero_parcela", "data_vencimento", "dias_periodo",
  "saldo_anterior", "juros", "amortizacao", "parcela",
  "saldo_devedor", "extras_total", "parcela_total", "ajuste_arredondamento",
];

export function ScheduleTable({ rows, codigo }: Props) {
  const handleExport = () => {
    const csv = buildCsv(CSV_HEADERS, rows as unknown as Record<string, string | number>[]);
    downloadCsv(`simulacao-${codigo ?? "export"}.csv`, csv);
  };

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <h3 className="text-sm font-semibold text-zinc-700">Cronograma de parcelas</h3>
        <button
          onClick={handleExport}
          className="text-xs border rounded px-3 py-1.5 hover:bg-zinc-50"
        >
          Exportar CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-zinc-50">
              {["#", "Vencimento", "Parcela", "Juros", "Amort.", "Saldo Dev.", "Extras", "Total"].map((h) => (
                <th key={h} className="text-left px-2 py-2 border-b text-zinc-500 font-medium whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.numero_parcela} className="hover:bg-zinc-50 border-b border-zinc-100">
                <td className="px-2 py-1.5 text-zinc-400">{row.numero_parcela}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{row.data_vencimento}</td>
                <td className="px-2 py-1.5 font-mono">{fmtBRL(row.parcela)}</td>
                <td className="px-2 py-1.5 font-mono text-zinc-500">{fmtBRL(row.juros)}</td>
                <td className="px-2 py-1.5 font-mono text-zinc-500">{fmtBRL(row.amortizacao)}</td>
                <td className="px-2 py-1.5 font-mono">{fmtBRL(row.saldo_devedor)}</td>
                <td className="px-2 py-1.5 font-mono text-blue-600">
                  {parseFloat(row.extras_total) > 0 ? fmtBRL(row.extras_total) : "—"}
                </td>
                <td className="px-2 py-1.5 font-mono font-semibold">{fmtBRL(row.parcela_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
