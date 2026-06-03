import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";

interface ProviderInfo {
  success: boolean;
  latency_ms: number | null;
  error: string | null;
  checked_at: string;
}

interface AdminHealth {
  postgres: string;
  redis: string;
  providers: Record<string, ProviderInfo>;
}

function StatusPill({ ok }: { ok: boolean }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${ok ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400"}`}>
      {ok ? "ok" : "error"}
    </span>
  );
}

export default function SystemHealth() {
  const { data, isLoading, dataUpdatedAt } = useQuery({
    queryKey: ["admin-health"],
    queryFn: async () => {
      const { data } = await api.get<AdminHealth>("/v1/admin/health");
      return data;
    },
    refetchInterval: 30_000,
  });

  if (isLoading) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Saúde do Sistema</h1>
        <span className="text-xs text-[#475569]">
          {dataUpdatedAt ? `Atualizado: ${new Date(dataUpdatedAt).toLocaleTimeString("pt-BR")}` : ""}
        </span>
      </div>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <span className="text-sm text-[#94A3B8]">PostgreSQL</span>
          <StatusPill ok={data?.postgres === "ok"} />
        </div>
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <span className="text-sm text-[#94A3B8]">Redis</span>
          <StatusPill ok={data?.redis === "ok"} />
        </div>
        {Object.entries(data?.providers ?? {}).map(([name, info]) => (
          <div key={name} className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B] last:border-0">
            <div>
              <span className="text-sm text-[#94A3B8]">{name}</span>
              {info.latency_ms !== null && (
                <span className="text-xs text-[#475569] ml-2">{info.latency_ms}ms</span>
              )}
              {info.error && <p className="text-xs text-red-400 mt-0.5">{info.error}</p>}
            </div>
            <StatusPill ok={info.success} />
          </div>
        ))}
        {Object.keys(data?.providers ?? {}).length === 0 && (
          <div className="px-4 py-3 text-xs text-[#475569]">Nenhum dado de provider disponível ainda.</div>
        )}
      </div>
    </div>
  );
}
