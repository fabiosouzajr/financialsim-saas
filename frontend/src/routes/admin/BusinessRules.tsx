import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, Plus } from "lucide-react";
import { api } from "../../lib/api";
import EditableField from "../../components/EditableField";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface RateCurvePoint {
  ate_meses: number;
  taxa_mensal: string;
}

interface BusinessRulesData {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  valor_minimo_financiado: string;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  taxa_por_prazo_curva: RateCurvePoint[];
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  dias_max_carencia: number;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
}

async function fetchRules(): Promise<BusinessRulesData> {
  const { data } = await api.get<BusinessRulesData>("/v1/business-rules");
  return data;
}

async function updateRule(key: string, valor: unknown, motivo?: string): Promise<void> {
  await api.put(`/v1/business-rules/${key}`, { valor, motivo: motivo ?? null });
}

// Convert raw decimal to percentage string for display/edit (0.10 → "10.0000")
function toDisplayPct(raw: string | number, decimals = 4): string {
  return (parseFloat(String(raw)) * 100).toFixed(decimals);
}

// Build a save wrapper that converts percentage input back to decimal before saving
function makePctSave(
  key: string,
  updateFn: (key: string, valor: unknown, motivo?: string) => Promise<void>,
  invalidate: () => Promise<void>,
  decimals = 10
) {
  return async (pctValue: string, motivo?: string) => {
    const decimal = (parseFloat(pctValue) / 100).toFixed(decimals);
    await updateFn(key, decimal, motivo);
    await invalidate();
  };
}

// Rate curve editor component
function RateCurveEditor({
  points,
  onSave,
}: {
  points: RateCurvePoint[];
  onSave: (updated: RateCurvePoint[]) => Promise<void>;
}) {
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [draftTaxa, setDraftTaxa] = useState("");
  const [newMeses, setNewMeses] = useState("");
  const [newTaxa, setNewTaxa] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function saveEdit(idx: number) {
    setSaving(true);
    setError(null);
    try {
      const updated = points.map((p, i) =>
        i === idx
          ? { ...p, taxa_mensal: (parseFloat(draftTaxa) / 100).toFixed(10) }
          : p
      );
      await onSave(updated);
      setEditingIdx(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao salvar");
    } finally {
      setSaving(false);
    }
  }

  async function deleteRow(idx: number) {
    setSaving(true);
    setError(null);
    try {
      await onSave(points.filter((_, i) => i !== idx));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao remover");
    } finally {
      setSaving(false);
    }
  }

  async function addRow() {
    const meses = parseInt(newMeses);
    const taxa = parseFloat(newTaxa);
    if (!meses || isNaN(taxa)) {
      setError("Preencha prazo (meses) e taxa (%)");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const updated = [...points, { ate_meses: meses, taxa_mensal: (taxa / 100).toFixed(10) }]
        .sort((a, b) => a.ate_meses - b.ate_meses);
      await onSave(updated);
      setNewMeses("");
      setNewTaxa("");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao adicionar");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="py-3 border-b border-[#1E293B] last:border-0">
      <p className="text-xs text-[#64748B] mb-3">Curva de taxas por prazo</p>

      <table className="text-xs w-full mb-3">
        <thead>
          <tr>
            <th className="text-left text-[#475569] pb-1 font-normal">Até (meses)</th>
            <th className="text-left text-[#475569] pb-1 font-normal">Taxa mensal (%)</th>
            <th className="w-16"></th>
          </tr>
        </thead>
        <tbody>
          {points.map((p, idx) => (
            <tr key={p.ate_meses} className="group">
              <td className="text-[#94A3B8] py-1">{p.ate_meses}</td>
              <td className="py-1">
                {editingIdx === idx ? (
                  <div className="flex items-center gap-1.5">
                    <Input
                      type="number"
                      value={draftTaxa}
                      onChange={(e) => setDraftTaxa(e.target.value)}
                      className="h-6 w-24 text-xs bg-[#0F172A] border-[#22C55E] px-1.5"
                      autoFocus
                      onKeyDown={(e) => e.key === "Enter" && saveEdit(idx)}
                    />
                    <button
                      onClick={() => saveEdit(idx)}
                      disabled={saving}
                      className="text-[#22C55E] text-xs hover:underline"
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => setEditingIdx(null)}
                      className="text-[#64748B] text-xs hover:underline"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => {
                      setEditingIdx(idx);
                      setDraftTaxa(toDisplayPct(p.taxa_mensal));
                    }}
                    className="text-[#94A3B8] hover:text-[#F8FAFC] text-left"
                  >
                    {toDisplayPct(p.taxa_mensal)}%
                  </button>
                )}
              </td>
              <td className="py-1 text-right">
                <button
                  onClick={() => deleteRow(idx)}
                  disabled={saving}
                  className="opacity-0 group-hover:opacity-100 text-[#475569] hover:text-red-400 transition-opacity"
                >
                  <Trash2 size={12} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Add row */}
      <div className="flex items-center gap-2">
        <Input
          type="number"
          placeholder="Meses"
          value={newMeses}
          onChange={(e) => setNewMeses(e.target.value)}
          className="h-7 w-24 text-xs bg-[#0F172A] border-[#334155] px-2"
        />
        <Input
          type="number"
          placeholder="Taxa %"
          value={newTaxa}
          onChange={(e) => setNewTaxa(e.target.value)}
          className="h-7 w-24 text-xs bg-[#0F172A] border-[#334155] px-2"
        />
        <Button
          size="sm"
          onClick={addRow}
          disabled={saving}
          className="h-7 text-xs bg-[#1E293B] text-[#94A3B8] hover:bg-[#22C55E] hover:text-[#020617] border-0"
        >
          <Plus size={12} className="mr-1" />
          Adicionar
        </Button>
      </div>

      {error && <p className="text-xs text-red-400 mt-1.5">{error}</p>}
    </div>
  );
}

export default function BusinessRules() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["business-rules"], queryFn: fetchRules });

  if (isLoading || !data) {
    return <div className="p-8 text-[#64748B]">Carregando...</div>;
  }

  async function invalidate() {
    await qc.invalidateQueries({ queryKey: ["business-rules"] });
  }

  function makeSave(key: string) {
    return async (value: string, motivo?: string) => {
      await updateRule(key, value, motivo);
      await invalidate();
    };
  }

  function makePct(key: string) {
    return makePctSave(key, updateRule, invalidate);
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold mb-6">Regras de Negócio</h1>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Financiamento</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Entrada mínima (%)" value={toDisplayPct(data.entrada_minima_pct)} type="number" onSave={makePct("entrada_minima_pct")} motivo />
          <EditableField label="Prazo mínimo (meses)" value={String(data.prazo_minimo_meses)} type="number" onSave={makeSave("prazo_minimo_meses")} motivo />
          <EditableField label="Prazo máximo (meses)" value={String(data.prazo_maximo_meses)} type="number" onSave={makeSave("prazo_maximo_meses")} motivo />
          <EditableField label="Valor mínimo financiado (R$)" value={String(data.valor_minimo_financiado)} type="number" onSave={makeSave("valor_minimo_financiado")} motivo />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Taxas</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Taxa mínima (% a.m.)" value={toDisplayPct(data.taxa_minima_mes)} type="number" onSave={makePct("taxa_minima_mes")} motivo />
          <EditableField label="Taxa máxima (% a.m.)" value={toDisplayPct(data.taxa_maxima_mes)} type="number" onSave={makePct("taxa_maxima_mes")} motivo />
          <RateCurveEditor
            points={data.taxa_por_prazo_curva}
            onSave={async (updated) => {
              await updateRule("taxa_por_prazo_curva", updated);
              await invalidate();
            }}
          />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">IOF</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="IOF fixo (%)" value={toDisplayPct(data.iof_fixo_pct)} type="number" onSave={makePct("iof_fixo_pct")} motivo />
          <EditableField label="IOF diário (%)" value={toDisplayPct(data.iof_diario_pct, 6)} type="number" onSave={makePct("iof_diario_pct")} motivo />
          <EditableField label="IOF diário máx. dias" value={String(data.iof_diario_max_dias)} type="number" onSave={makeSave("iof_diario_max_dias")} motivo />
          <EditableField label="Incluir IOF por padrão" value={String(data.incluir_iof_default)} type="toggle" onSave={makeSave("incluir_iof_default")} />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Padrões</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Carência máxima (dias)" value={String(data.dias_max_carencia)} type="number" onSave={makeSave("dias_max_carencia")} motivo />
          <EditableField label="Rateio IPVA (meses)" value={String(data.rateio_ipva_meses_default)} type="number" onSave={makeSave("rateio_ipva_meses_default")} motivo />
          <EditableField label="Rateio emplacamento (meses)" value={String(data.rateio_emplacamento_meses_default)} type="number" onSave={makeSave("rateio_emplacamento_meses_default")} motivo />
        </div>
      </section>
    </div>
  );
}
