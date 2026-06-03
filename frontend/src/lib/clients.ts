import { api } from "./api";

export interface ClientOut {
  id: string;
  tenant_id: string;
  nome: string;
  cpf_cnpj: string;
  tipo: "pf" | "pj";
  rg: string | null;
  data_nasc: string | null;
  profissao: string | null;
  renda: string | null;
  telefone: string | null;
  email: string | null;
  endereco_json: Record<string, string> | null;
  observacoes: string | null;
  is_active: boolean;
  criado_por: string;
  criado_em: string;
  atualizado_em: string;
}

export interface ClientListPage {
  items: ClientOut[];
  next_cursor: string | null;
}

export interface ClientIn {
  nome: string;
  cpf_cnpj: string;
  tipo: "pf" | "pj";
  rg?: string | null;
  data_nasc?: string | null;
  profissao?: string | null;
  renda?: string | null;
  telefone?: string | null;
  email?: string | null;
  endereco_json?: Record<string, string> | null;
  observacoes?: string | null;
}

export async function listClients(params?: { q?: string; cursor?: string }): Promise<ClientListPage> {
  const { data } = await api.get<ClientListPage>("/v1/clients", { params });
  return data;
}

export async function createClient(body: ClientIn): Promise<ClientOut> {
  const { data } = await api.post<ClientOut>("/v1/clients", body);
  return data;
}

export async function getClient(id: string): Promise<ClientOut> {
  const { data } = await api.get<ClientOut>(`/v1/clients/${id}`);
  return data;
}

export async function updateClient(id: string, body: ClientIn): Promise<ClientOut> {
  const { data } = await api.patch<ClientOut>(`/v1/clients/${id}`, body);
  return data;
}

export async function deactivateClient(id: string): Promise<ClientOut> {
  const { data } = await api.post<ClientOut>(`/v1/clients/${id}/deactivate`);
  return data;
}
