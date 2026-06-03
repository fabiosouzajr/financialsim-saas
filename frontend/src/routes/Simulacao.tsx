import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { SimulacaoForm, useSimulationPreview } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import type { SimulationFormValues, SimulationOut } from "./simulacao/types";

export default function Simulacao() {
  useEffect(() => { document.title = "Simulações — FinacialSim"; }, []);
  const navigate = useNavigate();
  const { preview, loading } = useSimulationPreview();

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
      <div className="max-w-5xl mx-auto py-8 px-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors cursor-pointer mb-4">
            ← Voltar
          </button>
          <h1 className="text-xl font-bold text-zinc-900 mb-6">Nova Simulação</h1>
          <SimulacaoForm onSave={(v) => save.mutate(v)} />
          {save.error && (
            <p className="mt-3 text-sm text-red-600">
              Erro ao salvar. Verifique os dados e tente novamente.
            </p>
          )}
        </div>

        <div className="space-y-8">
          {preview ? (
            <>
              <ResultCards summary={preview.summary} loading={loading} />
              <SimulacaoCharts rows={preview.rows} />
              <ScheduleTable rows={preview.rows} />
            </>
          ) : (
            <div className="text-sm text-zinc-400 text-center mt-16">
              Preencha o formulário para ver o resultado.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
