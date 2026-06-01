import { api } from "./api";

export interface ProposalOut {
  id: string;
  tenant_id: string;
  simulation_id: string;
  codigo: string;
  gerado_por: string;
  gerado_em: string;
  validade_dias: number;
  render_status: "pending" | "rendering" | "ready" | "failed";
  render_error: string | null;
  status: "rascunho" | "ready" | "aprovada" | "cancelada";
  pdf_key: string | null;
  carne_key: string | null;
  aprovado_por: string | null;
  aprovado_em: string | null;
  cancelado_por: string | null;
  cancelado_em: string | null;
}

export interface ProposalListItem {
  id: string;
  codigo: string;
  simulation_id: string;
  render_status: ProposalOut["render_status"];
  status: ProposalOut["status"];
  gerado_em: string;
}

export interface ProposalListPage {
  items: ProposalListItem[];
  next_cursor: string | null;
}

export async function createProposal(simulationId: string): Promise<ProposalOut> {
  const { data } = await api.post<ProposalOut>("/api/v1/proposals", {
    simulation_id: simulationId,
  });
  return data;
}

export async function getProposal(id: string): Promise<ProposalOut> {
  const { data } = await api.get<ProposalOut>(`/api/v1/proposals/${id}`);
  return data;
}

export async function listProposals(params?: {
  status?: string;
  cursor?: string;
  limit?: number;
}): Promise<ProposalListPage> {
  const { data } = await api.get<ProposalListPage>("/api/v1/proposals", { params });
  return data;
}

export async function approveProposal(id: string): Promise<ProposalOut> {
  const { data } = await api.post<ProposalOut>(`/api/v1/proposals/${id}/approve`);
  return data;
}

export async function cancelProposal(id: string): Promise<ProposalOut> {
  const { data } = await api.post<ProposalOut>(`/api/v1/proposals/${id}/cancel`);
  return data;
}

export async function generateCarne(id: string): Promise<ProposalOut> {
  const { data } = await api.post<ProposalOut>(`/api/v1/proposals/${id}/render-carne`);
  return data;
}

export function downloadUrl(id: string, kind: "proposta" | "carne"): string {
  return `/api/v1/proposals/${id}/download?kind=${kind}`;
}
