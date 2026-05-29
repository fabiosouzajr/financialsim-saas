import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import Index from "../routes/Index";

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Index route", () => {
  it("renders the FinacialSim SaaS button", () => {
    render(<Index />, { wrapper: Wrapper });
    expect(screen.getByRole("button", { name: /FinacialSim SaaS/i })).toBeInTheDocument();
  });
});
