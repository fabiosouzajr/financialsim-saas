import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../lib/api";
import EditableField from "../../components/EditableField";

interface BusinessRulesData {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  valor_minimo_financiado: string;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  taxa_por_prazo_curva: Array<{ ate_meses: number; taxa_mensal: string }>;
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

export default function BusinessRules() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["business-rules"], queryFn: fetchRules });

  if (isLoading || !data) {
    return <div className="p-8 text-[#64748B]">Carregando...</div>;
  }

  function makeSave(key: string) {
    return async (value: string, motivo?: string) => {
      await updateRule(key, value, motivo);
      await qc.invalidateQueries({ queryKey: ["business-rules"] });
    };
  }

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold mb-6">Regras de Negócio</h1>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Financiamento</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Entrada mínima (%)" value={String(data.entrada_minima_pct)} type="number" onSave={makeSave("entrada_minima_pct")} motivo />
          <EditableField label="Prazo mínimo (meses)" value={String(data.prazo_minimo_meses)} type="number" onSave={makeSave("prazo_minimo_meses")} motivo />
          <EditableField label="Prazo máximo (meses)" value={String(data.prazo_maximo_meses)} type="number" onSave={makeSave("prazo_maximo_meses")} motivo />
          <EditableField label="Valor mínimo financiado (R$)" value={String(data.valor_minimo_financiado)} type="number" onSave={makeSave("valor_minimo_financiado")} motivo />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">Taxas</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="Taxa mínima (% a.m.)" value={String(data.taxa_minima_mes)} type="number" onSave={makeSave("taxa_minima_mes")} motivo />
          <EditableField label="Taxa máxima (% a.m.)" value={String(data.taxa_maxima_mes)} type="number" onSave={makeSave("taxa_maxima_mes")} motivo />
          <div className="py-3 border-b border-[#1E293B] last:border-0">
            <p className="text-xs text-[#64748B] mb-2">Curva de taxas por prazo <span className="text-[#475569]">(somente leitura)</span></p>
            <table className="text-xs w-full">
              <thead>
                <tr>
                  <th className="text-left text-[#475569] pb-1 font-normal">Até (meses)</th>
                  <th className="text-left text-[#475569] pb-1 font-normal">Taxa mensal (%)</th>
                </tr>
              </thead>
              <tbody>
                {data.taxa_por_prazo_curva.map((p) => (
                  <tr key={p.ate_meses}>
                    <td className="text-[#94A3B8] py-0.5">{p.ate_meses}</td>
                    <td className="text-[#94A3B8] py-0.5">{p.taxa_mensal}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-xs font-semibold text-[#94A3B8] uppercase tracking-wider mb-3">IOF</h2>
        <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
          <EditableField label="IOF fixo (%)" value={String(data.iof_fixo_pct)} type="number" onSave={makeSave("iof_fixo_pct")} motivo />
          <EditableField label="IOF diário (%)" value={String(data.iof_diario_pct)} type="number" onSave={makeSave("iof_diario_pct")} motivo />
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
