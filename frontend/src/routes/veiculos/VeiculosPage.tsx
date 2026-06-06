import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  listVehicles, createVehicle, setVehicleStatus, refreshVehicleFipe,
  type VehicleIn,
} from "@/lib/vehicles";
import { type FipePrice } from "@/lib/fipe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import FipeCascadePicker from "./FipeCascadePicker";

const TIPOS = ["carro", "moto", "caminhao"] as const;

const vehicleSchema = z.object({
  modo: z.enum(["fipe", "manual"]),
  tipo: z.enum(TIPOS),
  marca: z.string().min(1, "Obrigatório"),
  modelo: z.string().min(1, "Obrigatório"),
  ano_modelo: z.coerce.number().min(1900).max(2100),
  combustivel: z.string().optional(),
  codigo_fipe: z.string().optional(),
  valor_fipe: z.string().optional(),
  cor: z.string().optional(),
  placa: z.string().optional(),
  odometro_km: z.coerce.number().optional(),
});

type VehicleForm = z.infer<typeof vehicleSchema>;

const TIPO_LABELS: Record<string, string> = {
  carro: "Carro",
  moto: "Moto",
  caminhao: "Caminhão",
};

function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  labels,
}: {
  options: readonly T[];
  value: T;
  onChange: (v: T) => void;
  labels?: Record<string, string>;
}) {
  return (
    <div className="flex gap-1 p-1 bg-gray-100 rounded-lg">
      {options.map(opt => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-all duration-150 cursor-pointer ${
            value === opt
              ? "bg-white text-gray-900 shadow-sm border border-gray-200"
              : "text-gray-500 hover:text-gray-700"
          }`}
        >
          {labels?.[opt] ?? opt}
        </button>
      ))}
    </div>
  );
}

function FormField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-gray-700 font-medium">{label}</Label>
      {children}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

export function VehicleModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [modo, setModo] = useState<"fipe" | "manual">("fipe");
  const [tipo, setTipo] = useState<"carro" | "moto" | "caminhao">("carro");
  const [fipeData, setFipeData] = useState<{
    price: FipePrice; brandId: string; modelId: string; yearId: string;
  } | null>(null);

  const { register, handleSubmit, setValue, formState: { errors } } = useForm<VehicleForm>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(vehicleSchema) as any,
    defaultValues: { modo: "fipe", tipo: "carro" },
  });

  const create = useMutation({
    mutationFn: (body: VehicleIn) => createVehicle(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["vehicles"] }); onClose(); },
  });

  function handlePriceSelected(price: FipePrice, brandId: string, modelId: string, yearId: string) {
    setFipeData({ price, brandId, modelId, yearId });
    setValue("marca", price.marca);
    setValue("modelo", price.modelo);
    setValue("ano_modelo", price.ano_modelo);
    setValue("combustivel", price.combustivel);
    setValue("codigo_fipe", price.codigo_fipe);
    setValue("valor_fipe", price.valor);
  }

  function onSubmit(data: VehicleForm) {
    const snapshot = fipeData
      ? { year_id: fipeData.yearId, ...fipeData.price }
      : null;

    create.mutate({
      fonte: fipeData ? fipeData.price.fonte : "manual",
      tipo: data.tipo,
      marca: data.marca,
      modelo: data.modelo,
      ano_modelo: data.ano_modelo,
      combustivel: data.combustivel || null,
      codigo_fipe: data.codigo_fipe || null,
      valor_fipe: data.valor_fipe || null,
      cor: data.cor || null,
      placa: data.placa || null,
      odometro_km: data.odometro_km || null,
      snapshot_json: snapshot,
    });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
      {/* Tipo de veículo */}
      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">Tipo de Veículo</Label>
        <ToggleGroup
          options={TIPOS}
          value={tipo}
          onChange={t => { setTipo(t); setValue("tipo", t); }}
          labels={TIPO_LABELS}
        />
        <input type="hidden" {...register("tipo")} value={tipo} />
      </div>

      {/* Modo de entrada */}
      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">Fonte do Valor</Label>
        <ToggleGroup
          options={["fipe", "manual"] as const}
          value={modo}
          onChange={m => { setModo(m); setValue("modo", m); setFipeData(null); }}
          labels={{ fipe: "Tabela FIPE", manual: "Manual" }}
        />
        <input type="hidden" {...register("modo")} value={modo} />
      </div>

      <div className="border-t border-gray-100" />

      {/* FIPE or manual fields */}
      {modo === "fipe" ? (
        <div className="space-y-4">
          <FipeCascadePicker tipo={tipo} onPriceSelected={handlePriceSelected} />

          {fipeData && (
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <p className="text-sm font-semibold text-emerald-900">
                  {fipeData.price.marca} {fipeData.price.modelo} {fipeData.price.ano_modelo}
                </p>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="text-xs text-emerald-700">Valor FIPE</span>
                <span className="text-lg font-bold text-emerald-800">
                  R$ {Number(fipeData.price.valor).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="flex items-center justify-between text-xs text-emerald-600">
                <span>{fipeData.price.combustivel}</span>
                <span>Ref: {fipeData.price.mes_referencia}</span>
              </div>
              {fipeData.price.codigo_fipe && (
                <p className="text-xs text-emerald-500">Cód. FIPE: {fipeData.price.codigo_fipe}</p>
              )}
            </div>
          )}

          {!fipeData && (
            <p className="text-xs text-gray-400 text-center">
              Selecione marca, modelo e ano, depois clique em "Consultar FIPE"
            </p>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Marca" error={errors.marca?.message}>
              <Input {...register("marca")} placeholder="Ex: Toyota" className="bg-white border-gray-300 text-gray-900" />
            </FormField>
            <FormField label="Modelo" error={errors.modelo?.message}>
              <Input {...register("modelo")} placeholder="Ex: Corolla" className="bg-white border-gray-300 text-gray-900" />
            </FormField>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Ano">
              <Input type="number" {...register("ano_modelo")} placeholder="2023" className="bg-white border-gray-300 text-gray-900" />
            </FormField>
            <FormField label="Combustível">
              <Input {...register("combustivel")} placeholder="Gasolina" className="bg-white border-gray-300 text-gray-900" />
            </FormField>
          </div>
          <FormField label="Valor de Referência (R$)">
            <Input {...register("valor_fipe")} placeholder="0,00" className="bg-white border-gray-300 text-gray-900" />
          </FormField>
        </div>
      )}

      <div className="border-t border-gray-100" />

      {/* Additional fields */}
      <div className="grid grid-cols-2 gap-3">
        <FormField label="Cor">
          <Input {...register("cor")} placeholder="Prata" className="bg-white border-gray-300 text-gray-900" />
        </FormField>
        <FormField label="Placa">
          <Input {...register("placa")} placeholder="ABC1D23" className="bg-white border-gray-300 text-gray-900 uppercase" />
        </FormField>
      </div>
      <FormField label="Odômetro (km)">
        <Input type="number" {...register("odometro_km")} placeholder="0" className="bg-white border-gray-300 text-gray-900" />
      </FormField>

      {create.error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">
            {(create.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Erro ao salvar veículo"}
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose} className="cursor-pointer">
          Cancelar
        </Button>
        <Button
          type="submit"
          disabled={create.isPending || (modo === "fipe" && !fipeData)}
          className="bg-slate-800 hover:bg-slate-700 text-white cursor-pointer"
        >
          {create.isPending ? "Salvando..." : "Registrar Veículo"}
        </Button>
      </div>
    </form>
  );
}

const STATUS_COLORS: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ativo: "success",
  reservado: "warning",
  vendido: "destructive",
  inativo: "outline",
};

export default function VeiculosPage() {
  useEffect(() => { document.title = "Veículos — FinacialSim"; }, []);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["vehicles", statusFilter],
    queryFn: () => listVehicles({ status: statusFilter || undefined }),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => setVehicleStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  const refreshFipe = useMutation({
    mutationFn: (id: string) => refreshVehicleFipe(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  return (
    <div className="p-6 space-y-4">
      <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors cursor-pointer">
        ← Voltar
      </button>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Veículos</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>+ Novo Veículo</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto bg-white text-gray-900">
            <DialogHeader>
              <DialogTitle className="text-gray-900 text-lg font-semibold">Registrar Veículo</DialogTitle>
            </DialogHeader>
            <VehicleModal onClose={() => setOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex gap-2 flex-wrap">
        {["", "ativo", "reservado", "vendido", "inativo"].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs border cursor-pointer transition-colors ${
              statusFilter === s
                ? "bg-slate-800 text-white border-slate-800"
                : "border-gray-300 text-gray-600 hover:border-gray-500 hover:text-gray-800"
            }`}
          >
            {s || "Todos"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Veículo</th>
                <th className="text-left px-4 py-3 font-medium">Placa</th>
                <th className="text-left px-4 py-3 font-medium">Valor FIPE</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted-foreground">
                    Nenhum veículo encontrado
                  </td>
                </tr>
              )}
              {data?.items.map(v => (
                <tr key={v.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{v.marca} {v.modelo}</div>
                    <div className="text-xs text-muted-foreground">{v.ano_modelo} · {v.tipo}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{v.placa ?? "—"}</td>
                  <td className="px-4 py-3">
                    {v.valor_fipe
                      ? `R$ ${Number(v.valor_fipe).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_COLORS[v.status]}>{v.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 justify-end flex-wrap">
                      {v.status === "ativo" && (
                        <Button size="sm" variant="outline"
                          onClick={() => setStatus.mutate({ id: v.id, status: "reservado" })}>
                          Reservar
                        </Button>
                      )}
                      {v.status === "reservado" && (
                        <>
                          <Button size="sm" variant="outline"
                            onClick={() => setStatus.mutate({ id: v.id, status: "vendido" })}>
                            Vender
                          </Button>
                          <Button size="sm" variant="ghost"
                            onClick={() => setStatus.mutate({ id: v.id, status: "ativo" })}>
                            Cancelar
                          </Button>
                        </>
                      )}
                      {v.status === "ativo" && v.fonte !== "manual" && (
                        <Button size="sm" variant="ghost"
                          onClick={() => refreshFipe.mutate(v.id)}>
                          Atualizar FIPE
                        </Button>
                      )}
                      {v.status === "ativo" && (
                        <Button size="sm" variant="ghost"
                          onClick={() => setStatus.mutate({ id: v.id, status: "inativo" })}>
                          Inativar
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
