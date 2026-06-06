import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import Index from "../routes/Index";

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ tokens: null, logout: vi.fn() }),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Index route", () => {
  it("renders the main navigation dashboard", () => {
    render(<Index />, { wrapper: Wrapper });
    expect(screen.getByText("Bem-vindo")).toBeInTheDocument();
    expect(screen.getByText("Simulação")).toBeInTheDocument();
    expect(screen.getByText("Clientes")).toBeInTheDocument();
    expect(screen.getByText("Veículos")).toBeInTheDocument();
  });
});
