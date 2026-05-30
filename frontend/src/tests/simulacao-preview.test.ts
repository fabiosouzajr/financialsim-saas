import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useSimulationPreview } from "@/hooks/useSimulationPreview";

vi.mock("@/lib/api", () => ({
  api: {
    post: vi.fn().mockResolvedValue({ data: { summary: {}, rows: [] } }),
    get: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

import { api } from "@/lib/api";

describe("useSimulationPreview debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("fires only once after rapid calls", async () => {
    const { result } = renderHook(() => useSimulationPreview());
    const payload = {
      valor_veiculo: "50000.00", valor_entrada: "10000.00",
      taxa_mensal: "0.0199", prazo_meses: 24,
      data_liberacao: "2026-06-01", primeiro_vencimento: "2026-07-01",
      incluir_iof: false, fees: [], extras: [],
    };
    act(() => {
      result.current.request(payload);
      result.current.request(payload);
      result.current.request(payload);
    });
    act(() => { vi.advanceTimersByTime(400); });
    await act(async () => {});
    expect(api.post).toHaveBeenCalledTimes(1);
  });
});
