import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getFipeBrands, getFipeModels, getFipeYears, getFipePrice, type FipePrice } from "@/lib/fipe";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

interface Props {
  tipo: string;
  onPriceSelected: (price: FipePrice, brandId: string, modelId: string, yearId: string) => void;
}

export default function FipeCascadePicker({ tipo, onPriceSelected }: Props) {
  const [brandId, setBrandId] = useState("");
  const [modelId, setModelId] = useState("");
  const [yearId, setYearId] = useState("");
  const [fipeError, setFipeError] = useState<string | null>(null);

  const brands = useQuery({
    queryKey: ["fipe-brands", tipo],
    queryFn: () => getFipeBrands(tipo),
    staleTime: 30 * 60 * 1000,
  });

  const models = useQuery({
    queryKey: ["fipe-models", tipo, brandId],
    queryFn: () => getFipeModels(tipo, brandId),
    enabled: !!brandId,
    staleTime: 30 * 60 * 1000,
  });

  const years = useQuery({
    queryKey: ["fipe-years", tipo, brandId, modelId],
    queryFn: () => getFipeYears(tipo, brandId, modelId),
    enabled: !!brandId && !!modelId,
    staleTime: 30 * 60 * 1000,
  });

  async function handleGetPrice() {
    if (!brandId || !modelId || !yearId) return;
    setFipeError(null);
    try {
      const price = await getFipePrice(tipo, brandId, modelId, yearId);
      onPriceSelected(price, brandId, modelId, yearId);
    } catch {
      setFipeError("Falha ao consultar FIPE. Tente novamente ou preencha manualmente.");
    }
  }

  function handleBrandChange(v: string) {
    setBrandId(v);
    setModelId("");
    setYearId("");
  }

  function handleModelChange(v: string) {
    setModelId(v);
    setYearId("");
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        <Label htmlFor="marca-select">Marca</Label>
        <select
          id="marca-select"
          aria-label="Marca"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={brandId}
          onChange={e => handleBrandChange(e.target.value)}
          disabled={brands.isLoading}
        >
          <option value="">{brands.isLoading ? "Carregando..." : "Selecione a marca"}</option>
          {brands.data?.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}
        </select>
      </div>

      <div className="grid gap-2">
        <Label>Modelo</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={modelId}
          onChange={e => handleModelChange(e.target.value)}
          disabled={!brandId || models.isLoading}
        >
          <option value="">{models.isLoading ? "Carregando..." : "Selecione o modelo"}</option>
          {models.data?.map(m => <option key={m.id} value={m.id}>{m.nome}</option>)}
        </select>
      </div>

      <div className="grid gap-2">
        <Label>Ano/Combustível</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={yearId}
          onChange={e => setYearId(e.target.value)}
          disabled={!modelId || years.isLoading}
        >
          <option value="">{years.isLoading ? "Carregando..." : "Selecione o ano"}</option>
          {years.data?.map(y => <option key={y.id} value={y.id}>{y.nome}</option>)}
        </select>
      </div>

      {fipeError && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-50 border border-yellow-200 p-3">
          <span className="text-yellow-700 text-sm">{fipeError}</span>
          <Button size="sm" variant="outline" onClick={handleGetPrice}>Tentar novamente</Button>
        </div>
      )}

      <Button
        type="button"
        onClick={handleGetPrice}
        disabled={!brandId || !modelId || !yearId}
        className="w-full"
      >
        Consultar FIPE
      </Button>
    </div>
  );
}
