import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { listAuditLog, type AuditLogItem } from "../../lib/audit-log";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ACAO_OPTIONS = [
  { label: "Todas as ações", value: "_all" },
  { label: "create", value: "create" },
  { label: "update", value: "update" },
  { label: "delete", value: "delete" },
];

export default function AuditLog() {
  const [acao, setAcao] = useState("_all");
  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", acao, cursor],
    queryFn: () =>
      listAuditLog({ acao: acao === "_all" ? undefined : acao, cursor }),
  });

  function handleExportCsv() {
    window.open("/api/v1/audit-log?format=csv", "_blank");
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Log de Auditoria</h1>
        <div className="flex items-center gap-3">
          <Select
            value={acao}
            onValueChange={(v) => { setAcao(v); setCursor(undefined); }}
          >
            <SelectTrigger className="w-40 h-8 text-xs bg-[#0F172A] border-[#1E293B]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ACAO_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button size="sm" variant="outline" className="h-8 text-xs border-[#334155]" onClick={handleExportCsv}>
            Exportar CSV
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-[#64748B]">Carregando...</div>
      ) : (
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#1E293B] text-xs text-[#64748B]">
                <th className="text-left px-4 py-3 font-normal">Timestamp</th>
                <th className="text-left px-4 py-3 font-normal">Usuário</th>
                <th className="text-left px-4 py-3 font-normal">Ação</th>
                <th className="text-left px-4 py-3 font-normal">Entidade</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((item: AuditLogItem) => (
                <React.Fragment key={item.id}>
                  <tr className="border-b border-[#1E293B] hover:bg-[#1E293B] transition-colors">
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {new Date(item.timestamp).toLocaleString("pt-BR")}
                    </td>
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {item.usuario_email ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs bg-[#1E293B] px-2 py-0.5 rounded text-[#94A3B8]">
                        {item.acao}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-[#94A3B8] text-xs">
                      {item.entidade ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      {item.diff_json && (
                        <button
                          onClick={() =>
                            setExpandedId(expandedId === item.id ? null : item.id)
                          }
                          className="text-xs text-[#22C55E] hover:underline"
                        >
                          {expandedId === item.id ? "Fechar" : "Ver detalhes"}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === item.id && item.diff_json && (
                    <tr className="border-b border-[#1E293B]">
                      <td colSpan={5} className="px-4 py-3 bg-[#020617]">
                        <pre className="text-xs text-[#94A3B8] overflow-x-auto whitespace-pre-wrap">
                          {JSON.stringify(item.diff_json, null, 2)}
                        </pre>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
              {(data?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-xs text-[#475569]">
                    Nenhum registro encontrado.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          {data?.next_cursor && (
            <div className="p-4 border-t border-[#1E293B]">
              <Button
                size="sm"
                variant="outline"
                className="text-xs border-[#334155]"
                onClick={() => setCursor(data.next_cursor!)}
              >
                Carregar mais
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
