import { api } from "./api";

export interface FipeBrand { id: string; nome: string; }
export interface FipeModel { id: string; nome: string; }
export interface FipeYear  { id: string; nome: string; }

export interface FipePrice {
  tipo: string;
  marca: string;
  marca_id: string;
  modelo: string;
  modelo_id: string;
  ano_modelo: number;
  combustivel: string;
  codigo_fipe: string;
  valor: string;
  mes_referencia: string;
  fonte: string;
}

export async function getFipeBrands(tipo: string): Promise<FipeBrand[]> {
  const { data } = await api.get<FipeBrand[]>("/v1/fipe/brands", { params: { tipo } });
  return data;
}

export async function getFipeModels(tipo: string, brand_id: string): Promise<FipeModel[]> {
  const { data } = await api.get<FipeModel[]>("/v1/fipe/models", { params: { tipo, brand_id } });
  return data;
}

export async function getFipeYears(tipo: string, brand_id: string, model_id: string): Promise<FipeYear[]> {
  const { data } = await api.get<FipeYear[]>("/v1/fipe/years", { params: { tipo, brand_id, model_id } });
  return data;
}

export async function getFipePrice(tipo: string, brand_id: string, model_id: string, year_id: string): Promise<FipePrice> {
  const { data } = await api.get<FipePrice>("/v1/fipe/price", { params: { tipo, brand_id, model_id, year_id } });
  return data;
}
