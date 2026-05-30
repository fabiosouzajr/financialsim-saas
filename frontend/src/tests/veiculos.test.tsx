import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import FipeCascadePicker from "../routes/veiculos/FipeCascadePicker";
import * as fipeLib from "../lib/fipe";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("FipeCascadePicker", () => {
  it("clears model/year selects when brand changes", async () => {
    vi.spyOn(fipeLib, "getFipeBrands").mockResolvedValue([
      { id: "21", nome: "Toyota" },
      { id: "22", nome: "Honda" },
    ]);
    vi.spyOn(fipeLib, "getFipeModels").mockResolvedValue([
      { id: "4591", nome: "Corolla" },
    ]);
    vi.spyOn(fipeLib, "getFipeYears").mockResolvedValue([]);

    const onPrice = vi.fn();
    render(<FipeCascadePicker tipo="carro" onPriceSelected={onPrice} />, {
      wrapper: makeWrapper(),
    });

    await waitFor(() => screen.getByText("Toyota"));
    fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "21" } });
    await waitFor(() => screen.getByText("Corolla"));
    fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "22" } });
    await waitFor(() => expect(screen.queryByText("Corolla")).toBeNull());
  });
});
