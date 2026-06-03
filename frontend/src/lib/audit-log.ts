import { api } from "./api";

export interface AuditLogItem {
  id: string;
  timestamp: string;
  usuario_id: string | null;
  usuario_email: string | null;
  acao: string;
  entidade: string | null;
  entidade_id: string | null;
  diff_json: Record<string, unknown> | null;
}

export interface AuditLogPage {
  items: AuditLogItem[];
  next_cursor: string | null;
}

export interface AuditLogParams {
  acao?: string;
  cursor?: string;
}

export async function listAuditLog(params: AuditLogParams = {}): Promise<AuditLogPage> {
  const { data } = await api.get<AuditLogPage>("/v1/audit-log", { params });
  return data;
}
