import { useState } from "react";
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

function VehicleModal({ onClose }: { onClose: () => void }) {
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
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid gap-2">
        <Label>Tipo de Veículo</Label>
        <div className="flex gap-2">
          {TIPOS.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => { setTipo(t); setValue("tipo", t); }}
              className={`px-3 py-1.5 rounded-md text-sm border ${tipo === t ? "bg-primary text-white border-primary" : "border-input"}`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <input type="hidden" {...register("tipo")} value={tipo} />
      </div>

      <div className="flex gap-2">
        {(["fipe", "manual"] as const).map(m => (
          <button
            key={m}
            type="button"
            onClick={() => { setModo(m); setValue("modo", m); setFipeData(null); }}
            className={`px-3 py-1.5 rounded-md text-sm border ${modo === m ? "bg-primary text-white border-primary" : "border-input"}`}
          >
            {m === "fipe" ? "Consultar FIPE" : "Preencher manualmente"}
          </button>
        ))}
      </div>
      <input type="hidden" {...register("modo")} value={modo} />

      {modo === "fipe" ? (
        <>
          <FipeCascadePicker tipo={tipo} onPriceSelected={handlePriceSelected} />
          {fipeData && (
            <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-800 space-y-1">
              <p className="font-medium">{fipeData.price.marca} {fipeData.price.modelo} {fipeData.price.ano_modelo}</p>
              <p>FIPE: R$ {Number(fipeData.price.valor).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</p>
              <p className="text-xs text-green-600">Referência: {fipeData.price.mes_referencia}</p>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label>Marca</Label>
              <Input {...register("marca")} placeholder="Ex: Toyota" />
              {errors.marca && <p className="text-xs text-red-500">{errors.marca.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label>Modelo</Label>
              <Input {...register("modelo")} placeholder="Ex: Corolla" />
              {errors.modelo && <p className="text-xs text-red-500">{errors.modelo.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label>Ano</Label>
              <Input type="number" {...register("ano_modelo")} placeholder="2023" />
            </div>
            <div className="grid gap-2">
              <Label>Combustível</Label>
              <Input {...register("combustivel")} placeholder="Gasolina" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Valor de referência</Label>
            <Input {...register("valor_fipe")} placeholder="0.00" />
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2">
          <Label>Cor</Label>
          <Input {...register("cor")} placeholder="Prata" />
        </div>
        <div className="grid gap-2">
          <Label>Placa</Label>
          <Input {...register("placa")} placeholder="ABC1D23" />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Odômetro (km)</Label>
        <Input type="number" {...register("odometro_km")} placeholder="0" />
      </div>

      {create.error && (
        <p className="text-sm text-red-500">
          {(create.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Erro ao salvar"}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
        <Button type="submit" disabled={create.isPending || (modo === "fipe" && !fipeData)}>
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
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Veículos</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>+ Novo Veículo</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Registrar Veículo</DialogTitle>
            </DialogHeader>
            <VehicleModal onClose={() => setOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex gap-2">
        {["", "ativo", "reservado", "vendido", "inativo"].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs border ${statusFilter === s ? "bg-primary text-white border-primary" : "border-input text-muted-foreground"}`}
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
