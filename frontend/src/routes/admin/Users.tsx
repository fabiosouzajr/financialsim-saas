import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { api } from "../../lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { UserPlus, Pencil, ShieldCheck, ShieldOff } from "lucide-react";

// ── Types ────────────────────────────────────────────────────────────────────

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// ── API helpers ──────────────────────────────────────────────────────────────

async function listUsers(): Promise<UserItem[]> {
  const { data } = await api.get<UserItem[]>("/v1/users");
  return data;
}

async function createUser(body: { email: string; name: string; password: string; role: string }): Promise<UserItem> {
  const { data } = await api.post<UserItem>("/v1/users", body);
  return data;
}

async function patchUser(id: string, body: { role?: string; is_active?: boolean }): Promise<UserItem> {
  const { data } = await api.patch<UserItem>(`/v1/users/${id}`, body);
  return data;
}

// ── Constants ────────────────────────────────────────────────────────────────

const ROLES = ["admin", "manager", "user"] as const;
type StaffRole = typeof ROLES[number];

const ROLE_LABELS: Record<StaffRole, string> = {
  admin: "Admin",
  manager: "Gerente",
  user: "Usuário",
};

const ROLE_COLORS: Record<string, string> = {
  admin:   "bg-purple-100 text-purple-800",
  manager: "bg-blue-100 text-blue-800",
  user:    "bg-gray-100 text-gray-700",
};

// ── Schemas ──────────────────────────────────────────────────────────────────

const createSchema = z.object({
  email:    z.string().email("E-mail inválido"),
  name:     z.string().min(2, "Nome obrigatório"),
  password: z.string().min(6, "Mínimo 6 caracteres"),
  role:     z.enum(ROLES),
});

const editSchema = z.object({
  role:      z.enum(ROLES),
  is_active: z.boolean(),
});

type CreateForm = z.infer<typeof createSchema>;
type EditForm   = z.infer<typeof editSchema>;

// ── FormField helper ─────────────────────────────────────────────────────────

function FormField({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1.5">
      <Label className="text-gray-700 font-medium">{label}</Label>
      {children}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

// ── Role select ──────────────────────────────────────────────────────────────

function RoleSelect({ value, onChange }: { value: string; onChange: (v: StaffRole) => void }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value as StaffRole)}
      className="flex h-10 w-full rounded-md border border-gray-300 bg-white text-gray-900 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-700 cursor-pointer"
    >
      {ROLES.map(r => (
        <option key={r} value={r}>{ROLE_LABELS[r]}</option>
      ))}
    </select>
  );
}

// ── Create modal ─────────────────────────────────────────────────────────────

function CreateUserModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<CreateForm>({
    resolver: zodResolver(createSchema) as never,
    defaultValues: { role: "user" },
  });
  const role = watch("role");

  const create = useMutation({
    mutationFn: createUser,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); onClose(); },
  });

  return (
    <form onSubmit={handleSubmit(d => create.mutate(d))} className="space-y-4">
      <FormField label="Nome" error={errors.name?.message}>
        <Input {...register("name")} placeholder="Ana Silva" className="bg-white border-gray-300 text-gray-900" />
      </FormField>

      <FormField label="E-mail" error={errors.email?.message}>
        <Input {...register("email")} type="email" placeholder="ana@empresa.com" className="bg-white border-gray-300 text-gray-900" />
      </FormField>

      <FormField label="Senha temporária" error={errors.password?.message}>
        <Input {...register("password")} type="password" placeholder="••••••" className="bg-white border-gray-300 text-gray-900" />
      </FormField>

      <FormField label="Perfil">
        <RoleSelect value={role} onChange={v => setValue("role", v)} />
        <input type="hidden" {...register("role")} />
      </FormField>

      {create.error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">
            {(create.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Erro ao criar usuário"}
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose} className="cursor-pointer">Cancelar</Button>
        <Button type="submit" disabled={create.isPending}
          className="bg-slate-800 hover:bg-slate-700 text-white cursor-pointer">
          {create.isPending ? "Criando..." : "Criar Usuário"}
        </Button>
      </div>
    </form>
  );
}

// ── Edit modal ────────────────────────────────────────────────────────────────

function EditUserModal({ user, onClose }: { user: UserItem; onClose: () => void }) {
  const qc = useQueryClient();
  const { handleSubmit, setValue, watch } = useForm<EditForm>({
    resolver: zodResolver(editSchema) as never,
    defaultValues: { role: user.role as StaffRole, is_active: user.is_active },
  });
  const role      = watch("role");
  const is_active = watch("is_active");

  const patch = useMutation({
    mutationFn: (body: EditForm) => patchUser(user.id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["users"] }); onClose(); },
  });

  return (
    <form onSubmit={handleSubmit(d => patch.mutate(d))} className="space-y-4">
      <div className="rounded-lg bg-gray-50 border border-gray-200 px-4 py-3 space-y-0.5">
        <p className="text-sm font-medium text-gray-900">{user.name}</p>
        <p className="text-xs text-gray-500">{user.email}</p>
      </div>

      <FormField label="Perfil">
        <RoleSelect value={role} onChange={v => setValue("role", v)} />
      </FormField>

      <FormField label="Status da conta">
        <div className="flex gap-2">
          {[true, false].map(v => (
            <button
              key={String(v)}
              type="button"
              onClick={() => setValue("is_active", v)}
              className={`flex-1 px-3 py-2 rounded-md text-sm font-medium border transition-all duration-150 cursor-pointer ${
                is_active === v
                  ? v ? "bg-emerald-50 border-emerald-300 text-emerald-800" : "bg-red-50 border-red-300 text-red-800"
                  : "border-gray-200 text-gray-500 hover:text-gray-700"
              }`}
            >
              {v ? "Ativo" : "Inativo"}
            </button>
          ))}
        </div>
      </FormField>

      {patch.error && (
        <div className="rounded-md bg-red-50 border border-red-200 p-3">
          <p className="text-sm text-red-700">
            {(patch.error as { response?: { data?: { message?: string } } })?.response?.data?.message ?? "Erro ao atualizar"}
          </p>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" onClick={onClose} className="cursor-pointer">Cancelar</Button>
        <Button type="submit" disabled={patch.isPending}
          className="bg-slate-800 hover:bg-slate-700 text-white cursor-pointer">
          {patch.isPending ? "Salvando..." : "Salvar"}
        </Button>
      </div>
    </form>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminUsers() {
  useEffect(() => { document.title = "Usuários — FinacialSim"; }, []);

  const navigate = useNavigate();
  const [createOpen, setCreateOpen] = useState(false);
  const [editUser,   setEditUser]   = useState<UserItem | null>(null);
  const qc = useQueryClient();

  const { data: users, isLoading, isError } = useQuery({
    queryKey: ["users"],
    queryFn: listUsers,
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      patchUser(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="p-6 space-y-4">
      <button onClick={() => navigate("/")} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-800 transition-colors cursor-pointer">
        ← Voltar
      </button>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">Usuários</h1>
          <p className="text-sm text-gray-500 mt-0.5">Gerencie os usuários da sua conta</p>
        </div>

        <Dialog open={createOpen} onOpenChange={setCreateOpen}>
          <DialogTrigger asChild>
            <Button className="bg-slate-800 hover:bg-slate-700 text-white cursor-pointer">
              <UserPlus className="mr-2 h-4 w-4" />
              Novo Usuário
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-md bg-white text-gray-900">
            <DialogHeader>
              <DialogTitle className="text-gray-900">Criar Usuário</DialogTitle>
            </DialogHeader>
            <CreateUserModal onClose={() => setCreateOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {/* Edit modal */}
      <Dialog open={!!editUser} onOpenChange={open => { if (!open) setEditUser(null); }}>
        <DialogContent className="max-w-md bg-white text-gray-900">
          <DialogHeader>
            <DialogTitle className="text-gray-900">Editar Usuário</DialogTitle>
          </DialogHeader>
          {editUser && <EditUserModal user={editUser} onClose={() => setEditUser(null)} />}
        </DialogContent>
      </Dialog>

      {/* States */}
      {isLoading && <p className="text-gray-500 text-sm">Carregando...</p>}
      {isError   && <p className="text-red-600 text-sm">Erro ao carregar usuários.</p>}

      {/* Table */}
      {users && (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Usuário</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Perfil</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Status</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">Criado em</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-gray-400">
                    Nenhum usuário encontrado
                  </td>
                </tr>
              )}
              {users.map(u => (
                <tr key={u.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-gray-900">{u.name}</div>
                    <div className="text-xs text-gray-500">{u.email}</div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${ROLE_COLORS[u.role] ?? ROLE_COLORS.user}`}>
                      {ROLE_LABELS[u.role as StaffRole] ?? u.role}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {u.is_active ? (
                      <span className="inline-flex items-center gap-1 text-xs text-emerald-700 font-medium">
                        <ShieldCheck className="h-3.5 w-3.5" /> Ativo
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-xs text-gray-400 font-medium">
                        <ShieldOff className="h-3.5 w-3.5" /> Inativo
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-gray-500">
                    {new Date(u.created_at).toLocaleDateString("pt-BR")}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 justify-end">
                      <Button
                        size="sm" variant="outline"
                        onClick={() => setEditUser(u)}
                        className="cursor-pointer"
                      >
                        <Pencil className="h-3.5 w-3.5 mr-1" /> Editar
                      </Button>
                      <Button
                        size="sm"
                        variant={u.is_active ? "ghost" : "outline"}
                        disabled={toggleActive.isPending}
                        onClick={() => toggleActive.mutate({ id: u.id, is_active: !u.is_active })}
                        className="cursor-pointer"
                      >
                        {u.is_active ? "Desativar" : "Ativar"}
                      </Button>
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
