import { api } from "./api";

export interface TenantProfileOut {
  nome: string;
  cnpj: string | null;
  telefone: string | null;
  endereco: string | null;
  logo_url: string | null;
  proposta_validade_dias: number;
}

export interface TenantProfileIn {
  nome: string;
  cnpj?: string | null;
  telefone?: string | null;
  endereco?: string | null;
  proposta_validade_dias: number;
}

export async function getTenantProfile(): Promise<TenantProfileOut> {
  const { data } = await api.get<TenantProfileOut>("/v1/admin/tenant-profile");
  return data;
}

export async function updateTenantProfile(body: TenantProfileIn): Promise<TenantProfileOut> {
  const { data } = await api.put<TenantProfileOut>("/v1/admin/tenant-profile", body);
  return data;
}

export async function uploadLogo(file: File): Promise<TenantProfileOut> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<TenantProfileOut>("/v1/admin/tenant-profile/logo", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}
