import { useEffect, useState } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery } from "@tanstack/react-query";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { useBusinessRules, suggestRate } from "@/hooks/useBusinessRules";
import { useSimulationPreview } from "@/hooks/useSimulationPreview";
import { listClients } from "@/lib/clients";
import { listVehicles } from "@/lib/vehicles";
import type { SimulationFormValues, PreviewPayload } from "./types";

const schema = z.object({
  client_id: z.string().optional().default(""),
  vehicle_id: z.string().optional().default(""),
  cliente_nome: z.string().optional().default(""),
  veiculo_descricao: z.string().optional().default(""),
  valor_veiculo: z.string().min(1),
  valor_entrada_brl: z.string().min(1),
  valor_entrada_pct: z.string(),
  taxa_mensal: z.string().min(1),
  prazo_meses: z.number().int().min(1),
  data_liberacao: z.string().min(1),
  primeiro_vencimento: z.string().min(1),
  incluir_iof: z.boolean(),
  fees: z.array(z.object({
    nome: z.string(),
    valor: z.string(),
    incluir_no_principal: z.boolean(),
  })).default([]),
  extras: z.array(z.object({
    tipo: z.string(),
    nome: z.string(),
    valor_total: z.string(),
    modalidade: z.enum(["mensal_continuo", "rateio_meses", "unico_inicial"]),
    duracao_meses: z.number().int(),
    ordem: z.number().int(),
  })).default([]),
});

function todayIso(): string {
  return new Date().toISOString().split("T")[0];
}

function addDays(iso: string, n: number): string {
  const d = new Date(iso + "T00:00:00");
  d.setDate(d.getDate() + n);
  return d.toISOString().split("T")[0];
}

function toPayload(values: SimulationFormValues): PreviewPayload {
  return {
    valor_veiculo: values.valor_veiculo,
    valor_entrada: values.valor_entrada_brl,
    taxa_mensal: values.taxa_mensal,
    prazo_meses: values.prazo_meses,
    data_liberacao: values.data_liberacao,
    primeiro_vencimento: values.primeiro_vencimento,
    incluir_iof: values.incluir_iof,
    fees: values.fees,
    extras: values.extras,
  };
}

function ClientPicker({ value, onChange, error }: {
  value: string; onChange: (id: string) => void; error?: string;
}) {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["clients", q],
    queryFn: () => listClients({ q: q || undefined }),
    staleTime: 30_000,
  });
  return (
    <div className="grid gap-2">
      <label className="block text-sm font-medium mb-1">Cliente</label>
      <input
        className="w-full border rounded px-3 py-2 text-sm"
        placeholder="Buscar cliente por nome ou CPF..."
        value={q}
        onChange={e => setQ(e.target.value)}
      />
      {data?.items.length ? (
        <div className="border rounded-md max-h-40 overflow-y-auto">
          {data.items.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => { onChange(c.id); setQ(c.nome); }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-50 ${value === c.id ? "bg-zinc-100 font-medium" : ""}`}
            >
              {c.nome} <span className="text-zinc-400 text-xs">{c.cpf_cnpj}</span>
            </button>
          ))}
        </div>
      ) : null}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

function VehiclePicker({ value, onChange, error }: {
  value: string; onChange: (id: string) => void; error?: string;
}) {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["vehicles", { status: "ativo", placa: q || undefined }],
    queryFn: () => listVehicles({ status: "ativo", placa: q || undefined }),
    staleTime: 30_000,
  });
  return (
    <div className="grid gap-2">
      <label className="block text-sm font-medium mb-1">Veículo</label>
      <input
        className="w-full border rounded px-3 py-2 text-sm"
        placeholder="Buscar veículo por placa..."
        value={q}
        onChange={e => setQ(e.target.value)}
      />
      {data?.items.length ? (
        <div className="border rounded-md max-h-40 overflow-y-auto">
          {data.items.map(v => (
            <button
              key={v.id}
              type="button"
              onClick={() => {
                onChange(v.id);
                setQ(`${v.marca} ${v.modelo} ${v.ano_modelo}`);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-zinc-50 ${value === v.id ? "bg-zinc-100 font-medium" : ""}`}
            >
              {v.marca} {v.modelo} {v.ano_modelo}
              {v.placa && <span className="text-zinc-400 text-xs ml-1">· {v.placa}</span>}
            </button>
          ))}
        </div>
      ) : null}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

interface Props {
  initialValues?: Partial<SimulationFormValues>;
  onSave?: (values: SimulationFormValues) => void;
}

export function SimulacaoForm({ initialValues, onSave }: Props) {
  const { data: rules } = useBusinessRules();
  const { preview, loading: previewLoading, request: requestPreview } = useSimulationPreview();

  const today = todayIso();
  const defaultPrazo = rules?.prazo_minimo_meses ?? 24;
  const defaultTaxa = rules
    ? suggestRate(defaultPrazo, rules.taxa_por_prazo_curva)
    : "0.0199";

  const { register, watch, setValue, control, handleSubmit, formState } =
    useForm<SimulationFormValues>({
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      resolver: zodResolver(schema) as any,
      defaultValues: {
        client_id: "",
        vehicle_id: "",
        cliente_nome: "",
        veiculo_descricao: "",
        valor_veiculo: "",
        valor_entrada_brl: "",
        valor_entrada_pct: "",
        taxa_mensal: defaultTaxa,
        prazo_meses: defaultPrazo,
        data_liberacao: today,
        primeiro_vencimento: addDays(today, 30),
        incluir_iof: rules?.incluir_iof_default ?? true,
        fees: [],
        extras: [],
        ...initialValues,
      },
    });

  const { fields: feeFields, append: appendFee, remove: removeFee } = useFieldArray({
    control,
    name: "fees",
  });
  const { fields: extraFields, append: appendExtra, remove: removeExtra } = useFieldArray({
    control,
    name: "extras",
  });

  const watchAll = watch();
  const valorVeiculo = watch("valor_veiculo");
  const valorEntradaBrl = watch("valor_entrada_brl");
  const prazoMeses = watch("prazo_meses");

  useEffect(() => {
    const vv = parseFloat(valorVeiculo);
    const ve = parseFloat(valorEntradaBrl);
    if (vv > 0 && ve >= 0) {
      setValue("valor_entrada_pct", ((ve / vv) * 100).toFixed(2));
    }
  }, [valorVeiculo, valorEntradaBrl, setValue]);

  useEffect(() => {
    if (rules) {
      setValue("taxa_mensal", suggestRate(prazoMeses, rules.taxa_por_prazo_curva));
    }
  }, [prazoMeses, rules, setValue]);

  useEffect(() => {
    const vv = parseFloat(watchAll.valor_veiculo);
    const ve = parseFloat(watchAll.valor_entrada_brl);
    const taxa = parseFloat(watchAll.taxa_mensal);
    if (vv > 0 && ve >= 0 && taxa > 0 && watchAll.prazo_meses > 0) {
      requestPreview(toPayload(watchAll));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    watchAll.valor_veiculo, watchAll.valor_entrada_brl, watchAll.taxa_mensal,
    watchAll.prazo_meses, watchAll.data_liberacao, watchAll.primeiro_vencimento,
    watchAll.incluir_iof, watchAll.fees, watchAll.extras,
  ]);

  const handlePctBlur = () => {
    const vv = parseFloat(valorVeiculo);
    const pct = parseFloat(watch("valor_entrada_pct"));
    if (vv > 0 && pct >= 0) {
      setValue("valor_entrada_brl", (vv * pct / 100).toFixed(2));
    }
  };

  const onSubmit = (values: SimulationFormValues) => {
    onSave?.(values);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-6 max-w-xl mx-auto px-4 py-6">
      {/* Client / Vehicle pickers */}
      <ClientPicker
        value={watch("client_id") ?? ""}
        onChange={v => setValue("client_id", v)}
      />
      <VehiclePicker
        value={watch("vehicle_id") ?? ""}
        onChange={v => setValue("vehicle_id", v)}
      />

      {/* Valor do Veículo */}
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="valor_veiculo">
          Valor do Veículo (R$)
        </label>
        <input
          id="valor_veiculo"
          type="number"
          step="0.01"
          className="w-full border rounded px-3 py-2 text-sm"
          {...register("valor_veiculo")}
        />
      </div>

      {/* Entrada R$ / % */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="valor_entrada_brl">
            Entrada R$
          </label>
          <input
            id="valor_entrada_brl"
            type="number"
            step="0.01"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("valor_entrada_brl")}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="valor_entrada_pct">
            Entrada %
          </label>
          <input
            id="valor_entrada_pct"
            type="number"
            step="0.01"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("valor_entrada_pct")}
            onBlur={handlePctBlur}
          />
        </div>
      </div>

      {/* Prazo */}
      <div>
        <label className="block text-sm font-medium mb-2">
          Prazo: <span className="font-bold">{prazoMeses} meses</span>
        </label>
        <Slider
          min={rules?.prazo_minimo_meses ?? 12}
          max={rules?.prazo_maximo_meses ?? 72}
          step={1}
          value={[prazoMeses]}
          onValueChange={([v]) => setValue("prazo_meses", v)}
        />
        <div className="flex justify-between text-xs text-zinc-400 mt-1">
          <span>{rules?.prazo_minimo_meses ?? 12}m</span>
          <span>{rules?.prazo_maximo_meses ?? 72}m</span>
        </div>
      </div>

      {/* Taxa mensal */}
      <div>
        <label className="block text-sm font-medium mb-1" htmlFor="taxa_mensal">
          Taxa Mensal
          {rules && (
            <span className="ml-2 text-xs bg-zinc-100 text-zinc-600 px-2 py-0.5 rounded-full">
              sugerida: {(parseFloat(suggestRate(prazoMeses, rules.taxa_por_prazo_curva)) * 100).toFixed(2)}%
            </span>
          )}
        </label>
        <input
          id="taxa_mensal"
          type="number"
          step="0.0001"
          className="w-full border rounded px-3 py-2 text-sm"
          {...register("taxa_mensal")}
        />
      </div>

      {/* Datas */}
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="data_liberacao">
            Liberação
          </label>
          <input
            id="data_liberacao"
            type="date"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("data_liberacao")}
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1" htmlFor="primeiro_vencimento">
            1º Vencimento
          </label>
          <input
            id="primeiro_vencimento"
            type="date"
            className="w-full border rounded px-3 py-2 text-sm"
            {...register("primeiro_vencimento")}
          />
        </div>
      </div>

      {/* IOF Toggle */}
      <div className="flex items-center gap-3">
        <Switch
          id="incluir_iof"
          checked={watch("incluir_iof")}
          onCheckedChange={(v) => setValue("incluir_iof", v)}
        />
        <label htmlFor="incluir_iof" className="text-sm font-medium cursor-pointer">
          Incluir IOF
        </label>
      </div>

      {/* Tarifas (fees) */}
      <Collapsible>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
          <span>Tarifas</span>
          {feeFields.length > 0 && (
            <span className="text-xs bg-zinc-100 px-1.5 py-0.5 rounded-full">{feeFields.length}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3 space-y-2">
          {feeFields.map((field, i) => (
            <div key={field.id} className="flex gap-2 items-end">
              <input
                className="flex-1 border rounded px-2 py-1.5 text-sm"
                placeholder="Nome"
                {...register(`fees.${i}.nome`)}
              />
              <input
                className="w-28 border rounded px-2 py-1.5 text-sm"
                placeholder="Valor"
                type="number"
                step="0.01"
                {...register(`fees.${i}.valor`)}
              />
              <label className="flex items-center gap-1 text-xs">
                <input type="checkbox" {...register(`fees.${i}.incluir_no_principal`)} />
                +principal
              </label>
              <button type="button" onClick={() => removeFee(i)} className="text-red-500 text-sm">✕</button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => appendFee({ nome: "", valor: "0.00", incluir_no_principal: false })}
            className="text-sm text-zinc-600 hover:text-zinc-900"
          >
            + Adicionar tarifa
          </button>
        </CollapsibleContent>
      </Collapsible>

      {/* Extras */}
      <Collapsible>
        <CollapsibleTrigger className="flex items-center gap-2 text-sm font-medium text-zinc-700 hover:text-zinc-900">
          <span>Extras</span>
          {extraFields.length > 0 && (
            <span className="text-xs bg-zinc-100 px-1.5 py-0.5 rounded-full">{extraFields.length}</span>
          )}
        </CollapsibleTrigger>
        <CollapsibleContent className="mt-3 space-y-3">
          <div className="flex gap-2 flex-wrap">
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "protecao", nome: "Proteção Veicular",
                valor_total: "0.00", modalidade: "mensal_continuo",
                duracao_meses: watch("prazo_meses"), ordem: extraFields.length,
              })}
            >+ Proteção</button>
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "ipva", nome: "IPVA",
                valor_total: "0.00", modalidade: "rateio_meses",
                duracao_meses: rules?.rateio_ipva_meses_default ?? 12,
                ordem: extraFields.length,
              })}
            >+ IPVA</button>
            <button
              type="button"
              className="text-xs border rounded-full px-3 py-1 hover:bg-zinc-50"
              onClick={() => appendExtra({
                tipo: "emplacamento", nome: "Emplacamento",
                valor_total: "0.00", modalidade: "rateio_meses",
                duracao_meses: rules?.rateio_emplacamento_meses_default ?? 3,
                ordem: extraFields.length,
              })}
            >+ Emplacamento</button>
          </div>
          {extraFields.map((field, i) => (
            <div key={field.id} className="border rounded p-3 space-y-2">
              <div className="flex gap-2">
                <input
                  className="flex-1 border rounded px-2 py-1.5 text-sm"
                  placeholder="Nome"
                  {...register(`extras.${i}.nome`)}
                />
                <button type="button" onClick={() => removeExtra(i)} className="text-red-500 text-sm">✕</button>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="text-xs text-zinc-500">Valor total</label>
                  <input
                    className="w-full border rounded px-2 py-1.5 text-sm"
                    type="number" step="0.01"
                    {...register(`extras.${i}.valor_total`)}
                  />
                </div>
                <div>
                  <label className="text-xs text-zinc-500">Modalidade</label>
                  <select className="w-full border rounded px-2 py-1.5 text-sm" {...register(`extras.${i}.modalidade`)}>
                    <option value="mensal_continuo">Mensal contínuo</option>
                    <option value="rateio_meses">Rateio (meses)</option>
                    <option value="unico_inicial">Único inicial</option>
                  </select>
                </div>
                <div>
                  <label className="text-xs text-zinc-500">Duração (meses)</label>
                  <input
                    className="w-full border rounded px-2 py-1.5 text-sm"
                    type="number"
                    {...register(`extras.${i}.duracao_meses`, { valueAsNumber: true })}
                  />
                </div>
              </div>
            </div>
          ))}
          <button
            type="button"
            onClick={() => appendExtra({
              tipo: "custom", nome: "", valor_total: "0.00",
              modalidade: "mensal_continuo", duracao_meses: watch("prazo_meses"),
              ordem: extraFields.length,
            })}
            className="text-sm text-zinc-600 hover:text-zinc-900"
          >
            + Extra customizado
          </button>
        </CollapsibleContent>
      </Collapsible>

      {onSave && (
        <button
          type="submit"
          className="w-full bg-zinc-900 text-white rounded py-2.5 text-sm font-medium hover:bg-zinc-700"
          disabled={formState.isSubmitting}
        >
          Salvar simulação
        </button>
      )}

      {/* Hidden preview state for parent usage */}
      {previewLoading && <span style={{ display: "none" }}>preview-loading</span>}
      {preview && <span style={{ display: "none" }}>preview-ready</span>}
    </form>
  );
}

export { useSimulationPreview };
