import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SimulacaoForm } from "@/routes/simulacao/SimulacaoForm";

vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn().mockResolvedValue({ data: { summary: {}, rows: [] } }),
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

vi.mock("@/hooks/useBusinessRules", () => ({
  useBusinessRules: () => ({
    data: {
      entrada_minima_pct: "0.10",
      prazo_minimo_meses: 12,
      prazo_maximo_meses: 72,
      taxa_minima_mes: "0.005",
      taxa_maxima_mes: "0.05",
      dias_max_carencia: 90,
      valor_minimo_financiado: "5000.00",
      iof_fixo_pct: "0.0038",
      iof_diario_pct: "0.000082",
      iof_diario_max_dias: 365,
      incluir_iof_default: true,
      rateio_ipva_meses_default: 12,
      rateio_emplacamento_meses_default: 3,
      taxa_por_prazo_curva: [{ ate_meses: 72, taxa_mensal: "0.0199" }],
    },
    isLoading: false,
    error: null,
  }),
  suggestRate: () => "0.0199",
}));

vi.mock("@/hooks/useSimulationPreview", () => ({
  useSimulationPreview: () => ({
    preview: null, loading: false, error: null,
    request: vi.fn(),
  }),
}));

vi.mock("@/lib/clients", () => ({
  listClients: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
}));

vi.mock("@/lib/vehicles", () => ({
  listVehicles: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("SimulacaoForm entrada sync", () => {
  it("updating valor_veiculo recalculates entrada_pct", async () => {
    render(<SimulacaoForm />, { wrapper: Wrapper });
    const vehicleInput = screen.getByLabelText(/valor do veículo/i);
    const pctInput = screen.getByLabelText(/entrada %/i);

    await userEvent.clear(vehicleInput);
    await userEvent.type(vehicleInput, "50000");
    fireEvent.blur(vehicleInput);

    expect(pctInput).toBeTruthy();
  });

  it("updating entrada_brl syncs entrada_pct", async () => {
    render(<SimulacaoForm />, { wrapper: Wrapper });
    const brlInput = screen.getByLabelText(/entrada r\$/i);
    const pctInput = screen.getByLabelText(/entrada %/i) as HTMLInputElement;

    await userEvent.clear(brlInput);
    await userEvent.type(brlInput, "10000");
    fireEvent.blur(brlInput);

    expect(pctInput.disabled).toBe(false);
  });
});
