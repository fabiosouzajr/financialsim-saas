import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { BusinessRules } from "@/routes/simulacao/types";

export function useBusinessRules() {
  return useQuery<BusinessRules>({
    queryKey: ["business-rules"],
    queryFn: async () => {
      const res = await api.get<BusinessRules>("/v1/business-rules");
      return res.data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function suggestRate(
  prazoMeses: number,
  curva: { ate_meses: number; taxa_mensal: string }[]
): string {
  const sorted = [...curva].sort((a, b) => a.ate_meses - b.ate_meses);
  for (const point of sorted) {
    if (prazoMeses <= point.ate_meses) return point.taxa_mensal;
  }
  return sorted[sorted.length - 1]?.taxa_mensal ?? "0.0199";
}
