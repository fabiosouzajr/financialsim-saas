import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { SimulacaoForm } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import type { SimulationFormValues, SimulationOut, PreviewResponse } from "./simulacao/types";

export default function Simulacao() {
  useEffect(() => { document.title = "Simulações — FinacialSim"; }, []);
  const navigate = useNavigate();
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [simInfo, setSimInfo] = useState({ clienteName: "", vehicleDesc: "" });
  const resultsRef = useRef<HTMLDivElement>(null);

  const handleVisualize = () => {
    resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const save = useMutation({
    mutationFn: async (values: SimulationFormValues) => {
      const res = await api.post<SimulationOut>("/v1/simulations", {
        client_id: values.client_id || undefined,
        vehicle_id: values.vehicle_id || undefined,
        cliente_nome: values.cliente_nome || null,
        veiculo_descricao: values.veiculo_descricao || null,
        valor_veiculo: values.valor_veiculo,
        valor_entrada: values.valor_entrada_brl,
        taxa_mensal: values.taxa_mensal,
        prazo_meses: values.prazo_meses,
        data_liberacao: values.data_liberacao,
        primeiro_vencimento: values.primeiro_vencimento,
        incluir_iof: values.incluir_iof,
        fees: values.fees,
        extras: values.extras,
      });
      return res.data;
    },
    onSuccess: (data) => navigate(`/simulacao/${data.id}`),
  });

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="max-w-5xl mx-auto py-8 px-4 grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
        <div>
          <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors cursor-pointer mb-4">
            ← Voltar
          </button>
          <h1 className="text-xl font-bold text-zinc-900 mb-6">Nova Simulação</h1>
          <SimulacaoForm
            onSave={(v) => save.mutate(v)}
            onVisualize={handleVisualize}
            onPreviewChange={(p, l) => { setPreview(p); setLoading(l); }}
            onInfoChange={(clienteName, vehicleDesc) => setSimInfo({ clienteName, vehicleDesc })}
          />
          {save.error && (
            <p className="mt-3 text-sm text-red-600">
              Erro ao salvar. Verifique os dados e tente novamente.
            </p>
          )}
        </div>

        <div ref={resultsRef} className="lg:sticky lg:top-8 space-y-6">
          {preview ? (
            <>
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-zinc-500 uppercase tracking-wide">Resultado</h2>
                {loading && (
                  <span className="text-xs text-zinc-400 flex items-center gap-1">
                    <span className="h-3 w-3 rounded-full border-2 border-zinc-300 border-t-zinc-600 animate-spin inline-block" />
                    Calculando
                  </span>
                )}
              </div>
              {(simInfo.clienteName || simInfo.vehicleDesc) && (
                <div className="text-sm text-zinc-600 space-y-0.5 border-b border-zinc-100 pb-3">
                  {simInfo.clienteName && (
                    <p><span className="font-medium text-zinc-400">Cliente</span> {simInfo.clienteName}</p>
                  )}
                  {simInfo.vehicleDesc && (
                    <p><span className="font-medium text-zinc-400">Veículo</span> {simInfo.vehicleDesc}</p>
                  )}
                </div>
              )}
              <ResultCards summary={preview.summary} loading={loading} />
              <SimulacaoCharts rows={preview.rows} />
              <ScheduleTable rows={preview.rows} />
            </>
          ) : (
            <div className="flex flex-col items-center justify-center text-center py-20 px-6 rounded-xl border border-dashed border-zinc-200 bg-white">
              <svg className="mb-4 h-10 w-10 text-zinc-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 7h6m0 10v-3m-3 3h.01M9 17h.01M9 11h.01M12 11h.01M15 11h.01M4.929 4.929A10 10 0 1 0 19.07 19.07" />
              </svg>
              <p className="text-sm font-medium text-zinc-400">Nenhuma simulação ainda</p>
              <p className="mt-1 text-xs text-zinc-300">Preencha o formulário e clique em <strong className="text-zinc-400">Visualizar</strong></p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
