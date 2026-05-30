export interface RateCurvePoint {
  ate_meses: number;
  taxa_mensal: string;
}

export interface BusinessRules {
  entrada_minima_pct: string;
  prazo_minimo_meses: number;
  prazo_maximo_meses: number;
  taxa_minima_mes: string;
  taxa_maxima_mes: string;
  dias_max_carencia: number;
  valor_minimo_financiado: string;
  iof_fixo_pct: string;
  iof_diario_pct: string;
  iof_diario_max_dias: number;
  incluir_iof_default: boolean;
  rateio_ipva_meses_default: number;
  rateio_emplacamento_meses_default: number;
  taxa_por_prazo_curva: RateCurvePoint[];
}

export interface FeeInput {
  nome: string;
  valor: string;
  incluir_no_principal: boolean;
}

export interface ExtraInput {
  tipo: string;
  nome: string;
  valor_total: string;
  modalidade: "mensal_continuo" | "rateio_meses" | "unico_inicial";
  duracao_meses: number;
  ordem: number;
}

export interface SimulationFormValues {
  client_id: string;
  vehicle_id: string;
  cliente_nome: string;
  veiculo_descricao: string;
  valor_veiculo: string;
  valor_entrada_brl: string;
  valor_entrada_pct: string;
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;
  primeiro_vencimento: string;
  incluir_iof: boolean;
  fees: FeeInput[];
  extras: ExtraInput[];
}

export interface AmortizationRowOut {
  numero_parcela: number;
  data_vencimento: string;
  dias_periodo: number;
  saldo_anterior: string;
  juros: string;
  amortizacao: string;
  parcela: string;
  saldo_devedor: string;
  extras_total: string;
  parcela_total: string;
  ajuste_arredondamento: string;
}

export interface SimulationSummary {
  parcela_financiamento: string;
  parcela_total_primeiro_ano: string;
  parcela_total_apos_rateio: string;
  valor_financiado: string;
  total_pago: string;
  total_juros: string;
  pct_juros: string;
  cet_mensal: string;
  cet_anual: string;
  total_pago_pelo_cliente: string;
  iof_total: string;
}

export interface PreviewResponse {
  summary: SimulationSummary;
  rows: AmortizationRowOut[];
}

export interface SimulationOut extends PreviewResponse {
  id: string;
  tenant_id: string;
  codigo: string;
  client_id: string | null;
  vehicle_id: string | null;
  cliente_nome: string | null;
  veiculo_descricao: string | null;
  valor_veiculo: string;
  valor_entrada: string;
  valor_financiado: string;
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;
  primeiro_vencimento: string;
  incluir_iof: boolean;
  status: string;
  criado_em: string;
  fees: Array<{ nome: string; valor: string; incluir_no_principal: boolean }>;
  extras: Array<{
    tipo: string;
    nome: string;
    valor_total: string;
    modalidade: "mensal_continuo" | "rateio_meses" | "unico_inicial";
    duracao_meses: number;
    ordem: number;
  }>;
}

export interface PreviewPayload {
  valor_veiculo: string;
  valor_entrada: string;
  taxa_mensal: string;
  prazo_meses: number;
  data_liberacao: string;
  primeiro_vencimento: string;
  incluir_iof: boolean;
  fees: FeeInput[];
  extras: ExtraInput[];
}
