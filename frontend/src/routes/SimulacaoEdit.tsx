import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { SimulacaoForm } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import type { SimulationFormValues, SimulationOut } from "./simulacao/types";

function isoToDateStr(isoOrDate: string): string {
  return isoOrDate.slice(0, 10);
}

export default function SimulacaoEdit() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: sim, isLoading } = useQuery<SimulationOut>({
    queryKey: ["simulation", id],
    queryFn: async () => {
      const res = await api.get<SimulationOut>(`/api/v1/simulations/${id}`);
      return res.data;
    },
    enabled: !!id,
  });

  const save = useMutation({
    mutationFn: async (values: SimulationFormValues) => {
      const res = await api.patch<SimulationOut>(`/api/v1/simulations/${id}`, {
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
    onSuccess: () => qc.invalidateQueries({ queryKey: ["simulation", id] }),
  });

  if (isLoading || !sim) {
    return <div className="p-8 text-zinc-400">Carregando…</div>;
  }

  const isEditable = sim.status === "rascunho";

  const initialValues: Partial<SimulationFormValues> = {
    client_id: sim.client_id ?? "",
    vehicle_id: sim.vehicle_id ?? "",
    cliente_nome: sim.cliente_nome ?? "",
    veiculo_descricao: sim.veiculo_descricao ?? "",
    valor_veiculo: sim.valor_veiculo,
    valor_entrada_brl: sim.valor_entrada,
    valor_entrada_pct: (
      (parseFloat(sim.valor_entrada) / parseFloat(sim.valor_veiculo)) * 100
    ).toFixed(2),
    taxa_mensal: sim.taxa_mensal,
    prazo_meses: sim.prazo_meses,
    data_liberacao: isoToDateStr(sim.data_liberacao),
    primeiro_vencimento: isoToDateStr(sim.primeiro_vencimento),
    incluir_iof: sim.incluir_iof,
    fees: sim.fees?.map((f) => ({
      nome: f.nome, valor: f.valor, incluir_no_principal: f.incluir_no_principal,
    })) ?? [],
    extras: sim.extras?.map((e) => ({
      tipo: e.tipo, nome: e.nome, valor_total: e.valor_total,
      modalidade: e.modalidade,
      duracao_meses: e.duracao_meses, ordem: e.ordem,
    })) ?? [],
  };

  return (
    <div className="min-h-screen bg-zinc-50">
      <div className="max-w-5xl mx-auto py-8 px-4 grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-xl font-bold text-zinc-900">{sim.codigo}</h1>
              <span className={`text-xs px-2 py-0.5 rounded-full ${
                sim.status === "rascunho" ? "bg-yellow-100 text-yellow-800" :
                sim.status === "arquivado" ? "bg-zinc-100 text-zinc-500" :
                "bg-green-100 text-green-800"
              }`}>{sim.status}</span>
            </div>
            <button
              onClick={() => navigate("/simulacao")}
              className="text-sm text-zinc-500 hover:text-zinc-900"
            >
              Nova simulação
            </button>
          </div>
          {isEditable ? (
            <SimulacaoForm initialValues={initialValues} onSave={(v) => save.mutate(v)} />
          ) : (
            <SimulacaoForm initialValues={initialValues} />
          )}
        </div>

        <div className="space-y-8">
          {sim.summary && (
            <>
              <ResultCards summary={sim.summary} />
              <SimulacaoCharts rows={sim.rows} />
              <ScheduleTable rows={sim.rows} codigo={sim.codigo} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
