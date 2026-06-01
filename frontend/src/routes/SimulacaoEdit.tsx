import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { SimulacaoForm } from "./simulacao/SimulacaoForm";
import { ResultCards } from "./simulacao/ResultCards";
import { ScheduleTable } from "./simulacao/ScheduleTable";
import { SimulacaoCharts } from "./simulacao/SimulacaoCharts";
import type { SimulationFormValues, SimulationOut } from "./simulacao/types";
import {
  type ProposalOut,
  approveProposal,
  cancelProposal,
  createProposal,
  downloadUrl,
  generateCarne,
  getProposal,
} from "@/lib/proposals";

function isoToDateStr(isoOrDate: string): string {
  return isoOrDate.slice(0, 10);
}

function ProposalSection({ simulationId }: { simulationId: string }) {
  const [proposal, setProposal] = useState<ProposalOut | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCancelDialog, setShowCancelDialog] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollCountRef = useRef(0);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (id: string) => {
      pollCountRef.current = 0;
      pollRef.current = setInterval(() => {
        pollCountRef.current += 1;
        if (pollCountRef.current >= 30) {
          stopPolling();
          setError("Render timeout — tente re-renderizar como admin.");
          return;
        }
        void getProposal(id)
          .then((p) => {
            setProposal(p);
            if (p.render_status === "ready" || p.render_status === "failed") {
              stopPolling();
            }
          })
          .catch(() => stopPolling());
      }, 2000);
    },
    [stopPolling]
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const handleGerar = async () => {
    setLoading(true);
    setError(null);
    try {
      const p = await createProposal(simulationId);
      setProposal(p);
      if (p.render_status === "pending" || p.render_status === "rendering") {
        startPolling(p.id);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao gerar proposta");
    } finally {
      setLoading(false);
    }
  };

  const handleApprove = async () => {
    if (!proposal) return;
    setLoading(true);
    setError(null);
    try {
      const p = await approveProposal(proposal.id);
      setProposal(p);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao aprovar");
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!proposal) return;
    setLoading(true);
    setError(null);
    try {
      const p = await cancelProposal(proposal.id);
      setProposal(p);
      setShowCancelDialog(false);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao cancelar");
    } finally {
      setLoading(false);
    }
  };

  const handleCarne = async () => {
    if (!proposal) return;
    setLoading(true);
    try {
      await generateCarne(proposal.id);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao gerar carnê");
    } finally {
      setLoading(false);
    }
  };

  const renderStatusPill = (status: ProposalOut["render_status"]) => {
    const map: Record<ProposalOut["render_status"], string> = {
      pending: "bg-yellow-100 text-yellow-800",
      rendering: "bg-blue-100 text-blue-800",
      ready: "bg-green-100 text-green-800",
      failed: "bg-red-100 text-red-800",
    };
    const label: Record<ProposalOut["render_status"], string> = {
      pending: "Aguardando…",
      rendering: "Renderizando…",
      ready: "Pronto",
      failed: "Falhou",
    };
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${map[status]}`}>
        {(status === "pending" || status === "rendering") && (
          <span className="h-2 w-2 animate-spin rounded-full border-2 border-current border-t-transparent" />
        )}
        {label[status]}
      </span>
    );
  };

  return (
    <div className="mt-6 rounded-lg border p-4">
      <h3 className="mb-3 text-base font-semibold">Proposta</h3>

      {!proposal && (
        <button
          onClick={() => void handleGerar()}
          disabled={loading}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {loading ? "Gerando…" : "Gerar proposta"}
        </button>
      )}

      {proposal && (
        <div className="space-y-3">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-medium">{proposal.codigo}</span>
            {renderStatusPill(proposal.render_status)}
            <span className="text-muted-foreground">
              Status: <strong>{proposal.status}</strong>
            </span>
          </div>

          {proposal.render_status === "failed" && proposal.render_error && (
            <p className="text-sm text-destructive">{proposal.render_error}</p>
          )}

          <div className="flex flex-wrap gap-2">
            {proposal.render_status === "ready" && (
              <>
                <a
                  href={downloadUrl(proposal.id, "proposta")}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Baixar proposta (PDF)
                </a>
                {proposal.status === "ready" && (
                  <button
                    onClick={() => void handleApprove()}
                    disabled={loading}
                    className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  >
                    Aprovar proposta
                  </button>
                )}
              </>
            )}

            {proposal.status === "aprovada" && (
              <>
                <button
                  onClick={() => void handleCarne()}
                  disabled={loading}
                  className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                >
                  Gerar carnê
                </button>
                {proposal.carne_key && (
                  <a
                    href={downloadUrl(proposal.id, "carne")}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded border px-3 py-1.5 text-sm font-medium hover:bg-muted"
                  >
                    Baixar carnê (PDF)
                  </a>
                )}
                <button
                  onClick={() => setShowCancelDialog(true)}
                  disabled={loading}
                  className="rounded border border-destructive px-3 py-1.5 text-sm font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
                >
                  Cancelar proposta
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}

      {showCancelDialog && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="rounded-lg bg-background p-6 shadow-lg max-w-sm w-full">
            <h4 className="font-semibold mb-2">Cancelar proposta</h4>
            <p className="text-sm text-muted-foreground mb-4">
              Esta ação cancelará todas as parcelas e desativará o acesso do cliente. Não pode ser desfeita.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowCancelDialog(false)}
                className="rounded border px-3 py-1.5 text-sm"
              >
                Voltar
              </button>
              <button
                onClick={() => void handleCancel()}
                disabled={loading}
                className="rounded bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground disabled:opacity-50"
              >
                Confirmar cancelamento
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
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
          <ProposalSection simulationId={sim.id} />
        </div>
      </div>
    </div>
  );
}
