import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  listClients, createClient, updateClient, deactivateClient,
  type ClientOut, type ClientIn,
} from "@/lib/clients";
import { lookupCep } from "@/lib/cep";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";

function isValidCpf(cpf: string): boolean {
  const d = cpf.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  const calc = (len: number) =>
    ([...d.slice(0, len)].reduce((s, x, i) => s + +x * (len + 1 - i), 0) * 10) % 11;
  return calc(9) % 10 === +d[9] && calc(10) % 10 === +d[10];
}

function isValidCnpj(cnpj: string): boolean {
  const d = cnpj.replace(/\D/g, "");
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
  const w1 = [5,4,3,2,9,8,7,6,5,4,3,2];
  const w2 = [6,...w1];
  const calc = (digits: number[], weights: number[]) => {
    const s = digits.slice(0, weights.length).reduce((a, x, i) => a + x * weights[i], 0);
    const r = s % 11;
    return r < 2 ? 0 : 11 - r;
  };
  const nums = [...d].map(Number);
  return calc(nums, w1) === nums[12] && calc(nums, w2) === nums[13];
}

const pfSchema = z.object({
  tipo: z.literal("pf"),
  nome: z.string().min(2, "Nome obrigatório"),
  cpf_cnpj: z.string().refine(v => isValidCpf(v), { message: "CPF inválido" }),
  rg: z.string().optional(),
  data_nasc: z.string().optional(),
  profissao: z.string().optional(),
  renda: z.string().optional(),
  telefone: z.string().optional(),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  cep: z.string().optional(),
  logradouro: z.string().optional(),
  bairro: z.string().optional(),
  localidade: z.string().optional(),
  uf: z.string().optional(),
  observacoes: z.string().optional(),
});

const pjSchema = z.object({
  tipo: z.literal("pj"),
  nome: z.string().min(2, "Nome obrigatório"),
  cpf_cnpj: z.string().refine(v => isValidCnpj(v), { message: "CNPJ inválido" }),
  renda: z.string().optional(),
  telefone: z.string().optional(),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  cep: z.string().optional(),
  logradouro: z.string().optional(),
  bairro: z.string().optional(),
  localidade: z.string().optional(),
  uf: z.string().optional(),
  observacoes: z.string().optional(),
});

const clientSchema = z.discriminatedUnion("tipo", [pfSchema, pjSchema]);
type ClientForm = z.infer<typeof clientSchema>;

function formToClientIn(data: ClientForm): ClientIn {
  const endereco = data.cep ? {
    cep: data.cep,
    logradouro: (data as Record<string, string>)["logradouro"] ?? "",
    bairro: (data as Record<string, string>)["bairro"] ?? "",
    localidade: (data as Record<string, string>)["localidade"] ?? "",
    uf: (data as Record<string, string>)["uf"] ?? "",
  } : null;
  return {
    nome: data.nome,
    cpf_cnpj: data.cpf_cnpj.replace(/\D/g, ""),
    tipo: data.tipo,
    rg: data.tipo === "pf" ? (data as Record<string, string>)["rg"] || null : null,
    data_nasc: data.tipo === "pf" ? (data as Record<string, string>)["data_nasc"] || null : null,
    profissao: data.tipo === "pf" ? (data as Record<string, string>)["profissao"] || null : null,
    renda: data.renda || null,
    telefone: data.telefone || null,
    email: data.email || null,
    endereco_json: endereco,
    observacoes: data.observacoes || null,
  };
}

function ClientModal({
  editing,
  onClose,
}: {
  editing: ClientOut | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [tipo, setTipo] = useState<"pf" | "pj">(editing?.tipo ?? "pf");
  const [cepLoading, setCepLoading] = useState(false);

  const { register, handleSubmit, setValue, formState: { errors } } = useForm<ClientForm>({
    resolver: zodResolver(clientSchema),
    defaultValues: editing
      ? {
          tipo: editing.tipo,
          nome: editing.nome,
          cpf_cnpj: editing.cpf_cnpj,
          ...(editing.tipo === "pf" ? {
            rg: editing.rg ?? "",
            data_nasc: editing.data_nasc ?? "",
            profissao: editing.profissao ?? "",
          } : {}),
          renda: editing.renda ?? "",
          telefone: editing.telefone ?? "",
          email: editing.email ?? "",
          cep: editing.endereco_json?.cep ?? "",
          logradouro: editing.endereco_json?.logradouro ?? "",
          bairro: editing.endereco_json?.bairro ?? "",
          localidade: editing.endereco_json?.localidade ?? "",
          uf: editing.endereco_json?.uf ?? "",
          observacoes: editing.observacoes ?? "",
        } as ClientForm
      : { tipo: "pf" } as ClientForm,
  });

  const mutation = useMutation({
    mutationFn: (data: ClientForm) =>
      editing
        ? updateClient(editing.id, formToClientIn(data))
        : createClient(formToClientIn(data)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      onClose();
    },
  });

  async function handleCepBlur(e: React.FocusEvent<HTMLInputElement>) {
    const cep = e.target.value.replace(/\D/g, "");
    if (cep.length !== 8) return;
    setCepLoading(true);
    const result = await lookupCep(cep);
    setCepLoading(false);
    if (result.logradouro) {
      setValue("logradouro" as keyof ClientForm, result.logradouro as never);
      setValue("bairro" as keyof ClientForm, (result.bairro ?? "") as never);
      setValue("localidade" as keyof ClientForm, (result.localidade ?? "") as never);
      setValue("uf" as keyof ClientForm, (result.uf ?? "") as never);
    }
  }

  return (
    <form onSubmit={handleSubmit(d => mutation.mutate(d))} className="space-y-4">
      <div className="flex gap-1 p-1 bg-gray-100 rounded-lg w-fit">
        {(["pf", "pj"] as const).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => { setTipo(t); setValue("tipo", t); }}
            className={`px-6 py-1.5 rounded-md text-sm font-medium transition-all duration-150 cursor-pointer ${
              tipo === t
                ? "bg-white text-gray-900 shadow-sm border border-gray-200"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      <input type="hidden" {...register("tipo")} value={tipo} />

      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">Nome</Label>
        <Input {...register("nome")} placeholder="Nome completo" className="bg-white border-gray-300 text-gray-900" />
        {errors.nome && <p className="text-xs text-red-500">{errors.nome.message}</p>}
      </div>

      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">{tipo === "pf" ? "CPF" : "CNPJ"}</Label>
        <Input {...register("cpf_cnpj")} placeholder={tipo === "pf" ? "000.000.000-00" : "00.000.000/0001-00"} className="bg-white border-gray-300 text-gray-900" />
        {errors.cpf_cnpj && <p className="text-xs text-red-500">{errors.cpf_cnpj.message}</p>}
      </div>

      {tipo === "pf" && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label className="text-gray-700 font-medium">RG</Label>
              <Input {...register("rg" as keyof ClientForm)} placeholder="RG" className="bg-white border-gray-300 text-gray-900" />
            </div>
            <div className="grid gap-2">
              <Label className="text-gray-700 font-medium">Data de Nascimento</Label>
              <Input type="date" {...register("data_nasc" as keyof ClientForm)} className="bg-white border-gray-300 text-gray-900" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label className="text-gray-700 font-medium">Profissão</Label>
            <Input {...register("profissao" as keyof ClientForm)} placeholder="Profissão" className="bg-white border-gray-300 text-gray-900" />
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label className="text-gray-700 font-medium">Renda / Faturamento</Label>
          <Input {...register("renda")} placeholder="0,00" className="bg-white border-gray-300 text-gray-900" />
        </div>
        <div className="grid gap-2">
          <Label className="text-gray-700 font-medium">Telefone</Label>
          <Input {...register("telefone")} placeholder="(11) 99999-9999" className="bg-white border-gray-300 text-gray-900" />
        </div>
      </div>

      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">Email</Label>
        <Input type="email" {...register("email")} placeholder="email@exemplo.com" className="bg-white border-gray-300 text-gray-900" />
        {errors.email && <p className="text-xs text-red-500">{errors.email.message}</p>}
      </div>

      <div className="border-t border-gray-100" />

      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">
          CEP {cepLoading && <span className="text-xs text-gray-400 font-normal">(buscando...)</span>}
        </Label>
        <Input {...register("cep")} placeholder="00000-000" onBlur={handleCepBlur} className="bg-white border-gray-300 text-gray-900" />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2 grid gap-2">
          <Label className="text-gray-700 font-medium">Logradouro</Label>
          <Input {...register("logradouro" as keyof ClientForm)} className="bg-white border-gray-300 text-gray-900" />
        </div>
        <div className="grid gap-2">
          <Label className="text-gray-700 font-medium">UF</Label>
          <Input {...register("uf" as keyof ClientForm)} maxLength={2} className="bg-white border-gray-300 text-gray-900" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="grid gap-2">
          <Label className="text-gray-700 font-medium">Bairro</Label>
          <Input {...register("bairro" as keyof ClientForm)} className="bg-white border-gray-300 text-gray-900" />
        </div>
        <div className="grid gap-2">
          <Label className="text-gray-700 font-medium">Cidade</Label>
          <Input {...register("localidade" as keyof ClientForm)} className="bg-white border-gray-300 text-gray-900" />
        </div>
      </div>

      <div className="grid gap-2">
        <Label className="text-gray-700 font-medium">Observações</Label>
        <textarea
          {...register("observacoes")}
          className="flex min-h-[60px] w-full rounded-md border border-gray-300 bg-white text-gray-900 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-700"
          placeholder="Observações"
        />
      </div>

      {mutation.error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">
            {(mutation.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Erro ao salvar"}
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose} className="cursor-pointer">Cancelar</Button>
        <Button type="submit" disabled={mutation.isPending} className="bg-slate-800 hover:bg-slate-700 text-white cursor-pointer">
          {mutation.isPending ? "Salvando..." : editing ? "Salvar" : "Criar Cliente"}
        </Button>
      </div>
    </form>
  );
}

const STATUS_VARIANT: Record<string, "success" | "outline"> = {
  ativo: "success",
  inativo: "outline",
};

export default function ClientesPage() {
  useEffect(() => { document.title = "Clientes — FinacialSim"; }, []);
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ClientOut | null>(null);
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["clients", q],
    queryFn: () => listClients({ q: q || undefined }),
  });

  const deactivate = useMutation({
    mutationFn: deactivateClient,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });

  function openCreate() { setEditing(null); setOpen(true); }
  function openEdit(c: ClientOut) { setEditing(c); setOpen(true); }
  function handleClose() { setOpen(false); setEditing(null); }

  return (
    <div className="p-6 space-y-4">
      <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors cursor-pointer">
        ← Voltar
      </button>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Clientes</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreate}>+ Novo Cliente</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto bg-white text-gray-900">
            <DialogHeader>
              <DialogTitle className="text-gray-900 text-lg font-semibold">{editing ? "Editar Cliente" : "Novo Cliente"}</DialogTitle>
            </DialogHeader>
            <ClientModal editing={editing} onClose={handleClose} />
          </DialogContent>
        </Dialog>
      </div>

      <Input
        placeholder="Buscar por nome ou CPF/CNPJ..."
        value={q}
        onChange={e => setQ(e.target.value)}
        className="max-w-sm"
      />

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Nome</th>
                <th className="text-left px-4 py-3 font-medium">CPF/CNPJ</th>
                <th className="text-left px-4 py-3 font-medium">Tipo</th>
                <th className="text-left px-4 py-3 font-medium">Telefone</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted-foreground">
                    Nenhum cliente encontrado
                  </td>
                </tr>
              )}
              {data?.items.map(c => (
                <tr key={c.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3 font-medium">{c.nome}</td>
                  <td className="px-4 py-3 text-muted-foreground">{c.cpf_cnpj}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{c.tipo.toUpperCase()}</Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{c.telefone ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[c.is_active ? "ativo" : "inativo"]}>
                      {c.is_active ? "Ativo" : "Inativo"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <Button size="sm" variant="outline" onClick={() => openEdit(c)}>Editar</Button>
                      {c.is_active && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => deactivate.mutate(c.id)}
                        >
                          Desativar
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
