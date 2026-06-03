import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";

interface IndicatorOut {
  codigo: string;
  valor: string;
  unidade: string;
  data: string;
}

const LABELS: Record<string, string> = { SELIC: "SELIC", CDI: "CDI", IPCA: "IPCA" };

export default function Indicators() {
  const [refreshing, setRefreshing] = useState(false);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["indicators-admin"],
    queryFn: async () => {
      const { data } = await api.get<IndicatorOut[]>("/v1/indicators");
      return data;
    },
    // Poll every 3s while refreshing so new data surfaces quickly
    refetchInterval: refreshing ? 3000 : false,
    refetchOnWindowFocus: false,
  });

  const { mutate: doRefresh, isPending } = useMutation({
    mutationFn: async () => { await api.post("/v1/indicators/refresh"); },
    onSuccess: () => {
      setRefreshing(true);
      // Poll for up to 30s then stop regardless
      setTimeout(() => setRefreshing(false), 30_000);
      refetch();
    },
  });

  // Stop polling once data arrives
  if (refreshing && data && data.length > 0) {
    setTimeout(() => setRefreshing(false), 0);
  }

  const loading = isLoading || isPending || refreshing;

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">Indicadores BACEN</h1>
          {refreshing && (
            <p className="text-xs text-[#64748B] mt-0.5">Buscando dados do BACEN...</p>
          )}
        </div>
        <Button
          size="sm"
          onClick={() => doRefresh()}
          disabled={isPending || refreshing}
          className="bg-[#22C55E] text-[#020617] hover:bg-[#16a34a]"
        >
          <RefreshCw size={14} className={`mr-1.5 ${loading ? "animate-spin" : ""}`} />
          Atualizar agora
        </Button>
      </div>

      {!isLoading && (!data || data.length === 0) ? (
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg p-8 text-center">
          {refreshing ? (
            <p className="text-sm text-[#64748B]">Aguardando resposta do BACEN...</p>
          ) : (
            <>
              <p className="text-sm text-[#64748B] mb-2">Nenhum indicador carregado.</p>
              <p className="text-xs text-[#475569]">
                Clique em "Atualizar agora" para buscar SELIC, CDI e IPCA do BACEN.
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {(data ?? []).map((ind) => (
            <div key={ind.codigo} className="bg-[#0F172A] border border-[#1E293B] rounded-lg p-5">
              <p className="text-xs text-[#64748B] uppercase tracking-wider">
                {LABELS[ind.codigo] ?? ind.codigo}
              </p>
              <p className="text-2xl font-semibold text-[#F8FAFC] mt-1">
                {ind.valor}
                <span className="text-sm text-[#64748B] ml-1">{ind.unidade}</span>
              </p>
              <p className="text-xs text-[#475569] mt-2">{ind.data}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
