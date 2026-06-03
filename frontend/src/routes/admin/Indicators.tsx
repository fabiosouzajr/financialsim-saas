import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Button } from "@/components/ui/button";
import { RefreshCw } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

interface IndicatorOut {
  codigo: string;
  valor: string;
  unidade: string;
  data: string;
}

const LABELS: Record<string, string> = { SELIC: "SELIC", CDI: "CDI", IPCA: "IPCA" };

export default function Indicators() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["indicators-admin"],
    queryFn: async () => {
      const { data } = await api.get<IndicatorOut[]>("/v1/indicators");
      return data;
    },
  });

  const { mutate: doRefresh, isPending } = useMutation({
    mutationFn: async () => { await api.post("/v1/indicators/refresh"); },
    onSuccess: () => { setTimeout(() => refetch(), 2000); },
  });

  if (isLoading) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-2xl">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Indicadores BACEN</h1>
        <Button
          size="sm"
          onClick={() => doRefresh()}
          disabled={isPending}
          className="bg-[#22C55E] text-[#020617] hover:bg-[#16a34a]"
        >
          <RefreshCw size={14} className={`mr-1.5 ${isPending ? "animate-spin" : ""}`} />
          Atualizar agora
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {(data ?? []).map((ind) => (
          <div key={ind.codigo} className="bg-[#0F172A] border border-[#1E293B] rounded-lg p-5">
            <p className="text-xs text-[#64748B] uppercase tracking-wider">{LABELS[ind.codigo] ?? ind.codigo}</p>
            <p className="text-2xl font-semibold text-[#F8FAFC] mt-1">
              {ind.valor}
              <span className="text-sm text-[#64748B] ml-1">{ind.unidade}</span>
            </p>
            <p className="text-xs text-[#475569] mt-2">{ind.data}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
