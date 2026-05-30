import { api } from "./api";

export interface VehicleOut {
  id: string;
  tenant_id: string;
  fonte: string;
  tipo: string;
  marca: string;
  modelo: string;
  ano_modelo: number;
  combustivel: string | null;
  codigo_fipe: string | null;
  valor_fipe: string | null;
  valor_referencia: string | null;
  mes_referencia_fipe: string | null;
  cor: string | null;
  placa: string | null;
  odometro_km: number | null;
  status: "ativo" | "reservado" | "vendido" | "inativo";
  snapshot_json: Record<string, unknown> | null;
  criado_por: string;
  criado_em: string;
  atualizado_em: string;
}

export interface VehicleListPage {
  items: VehicleOut[];
  next_cursor: string | null;
}

export interface VehicleIn {
  fonte: string;
  tipo: string;
  marca: string;
  modelo: string;
  ano_modelo: number;
  combustivel?: string | null;
  codigo_fipe?: string | null;
  valor_fipe?: string | null;
  valor_referencia?: string | null;
  mes_referencia_fipe?: string | null;
  cor?: string | null;
  placa?: string | null;
  odometro_km?: number | null;
  snapshot_json?: Record<string, unknown> | null;
}

export async function listVehicles(params?: { status?: string; placa?: string; cursor?: string }): Promise<VehicleListPage> {
  const { data } = await api.get<VehicleListPage>("/api/v1/vehicles", { params });
  return data;
}

export async function createVehicle(body: VehicleIn): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>("/api/v1/vehicles", body);
  return data;
}

export async function getVehicle(id: string): Promise<VehicleOut> {
  const { data } = await api.get<VehicleOut>(`/api/v1/vehicles/${id}`);
  return data;
}

export async function setVehicleStatus(id: string, status: string): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>(`/api/v1/vehicles/${id}/status`, { status });
  return data;
}

export async function refreshVehicleFipe(id: string): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>(`/api/v1/vehicles/${id}/refresh-fipe`);
  return data;
}
