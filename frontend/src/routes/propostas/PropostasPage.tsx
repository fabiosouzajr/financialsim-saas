import { useEffect, useState } from "react";
import {
  type ProposalListItem,
  type ProposalListPage,
  listProposals,
} from "@/lib/proposals";

const STATUS_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "rascunho", label: "Rascunho" },
  { value: "ready", label: "Pronto" },
  { value: "aprovada", label: "Aprovada" },
  { value: "cancelada", label: "Cancelada" },
];

const STATUS_BADGE: Record<string, string> = {
  rascunho: "bg-gray-100 text-gray-700",
  ready: "bg-green-100 text-green-700",
  aprovada: "bg-blue-100 text-blue-700",
  cancelada: "bg-red-100 text-red-700",
};

export default function PropostasPage() {
  const [statusFilter, setStatusFilter] = useState("");
  const [page, setPage] = useState<ProposalListPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (cursor?: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await listProposals({
        status: statusFilter || undefined,
        cursor,
        limit: 20,
      });
      setPage(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao carregar propostas");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const fmtDate = (iso: string) =>
    new Date(iso).toLocaleDateString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <h1 className="text-2xl font-semibold mb-4">Propostas</h1>

      <div className="mb-4 flex items-center gap-3">
        <label className="text-sm font-medium">Status:</label>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded border px-2 py-1 text-sm"
        >
          {STATUS_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => void load()}
          disabled={loading}
          className="rounded border px-3 py-1 text-sm hover:bg-muted disabled:opacity-50"
        >
          Atualizar
        </button>
      </div>

      {error && <p className="text-sm text-destructive mb-3">{error}</p>}

      {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}

      {!loading && page && (
        <>
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b text-left text-muted-foreground">
                <th className="py-2 pr-4 font-medium">Código</th>
                <th className="py-2 pr-4 font-medium">Status</th>
                <th className="py-2 pr-4 font-medium">Render</th>
                <th className="py-2 font-medium">Gerada em</th>
              </tr>
            </thead>
            <tbody>
              {page.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="py-4 text-muted-foreground">
                    Nenhuma proposta encontrada.
                  </td>
                </tr>
              )}
              {page.items.map((p: ProposalListItem) => (
                <tr key={p.id} className="border-b hover:bg-muted/30">
                  <td className="py-2 pr-4 font-mono">{p.codigo}</td>
                  <td className="py-2 pr-4">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_BADGE[p.status] ?? "bg-gray-100 text-gray-700"
                      }`}
                    >
                      {p.status}
                    </span>
                  </td>
                  <td className="py-2 pr-4 text-muted-foreground">
                    {p.render_status}
                  </td>
                  <td className="py-2 text-muted-foreground">
                    {fmtDate(p.gerado_em)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {page.next_cursor && (
            <div className="mt-4">
              <button
                onClick={() => void load(page.next_cursor ?? undefined)}
                disabled={loading}
                className="rounded border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-50"
              >
                Próxima página →
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
