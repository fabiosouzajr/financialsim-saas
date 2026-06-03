import { api } from "./api";

export interface CepResult {
  cep?: string;
  logradouro?: string;
  complemento?: string;
  bairro?: string;
  localidade?: string;
  uf?: string;
}

export async function lookupCep(cep: string): Promise<CepResult> {
  try {
    const { data } = await api.get<CepResult>(`/v1/cep/${cep.replace(/\D/g, "")}`);
    return data;
  } catch {
    return {};
  }
}
