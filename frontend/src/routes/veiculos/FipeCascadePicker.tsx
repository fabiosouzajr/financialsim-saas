import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getFipeBrands, getFipeModels, getFipeYears, getFipePrice, type FipePrice } from "@/lib/fipe";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Loader2, AlertCircle, RefreshCw } from "lucide-react";

interface Props {
  tipo: string;
  onPriceSelected: (price: FipePrice, brandId: string, modelId: string, yearId: string) => void;
}

const selectClass =
  "flex h-10 w-full rounded-md border border-gray-300 bg-white text-gray-900 px-3 text-sm focus:outline-none focus:ring-2 focus:ring-slate-700 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer";

function QuerySelect({
  id,
  label,
  hint,
  value,
  onChange,
  isLoading,
  isError,
  onRetry,
  placeholder,
  disabled,
  children,
}: {
  id?: string;
  label: string;
  hint?: string;
  value: string;
  onChange: (v: string) => void;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  placeholder: string;
  disabled: boolean;
  children: React.ReactNode;
}) {
  if (isError) {
    return (
      <div className="grid gap-1.5">
        <Label className="text-gray-700 font-medium">{label}</Label>
        <div className="flex items-center gap-2 rounded-md bg-red-50 border border-red-200 px-3 py-2">
          <AlertCircle className="h-4 w-4 text-red-500 shrink-0" />
          <span className="text-sm text-red-700 flex-1">Falha ao carregar {label.toLowerCase()}</span>
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-1 text-xs text-red-600 hover:text-red-800 font-medium cursor-pointer"
          >
            <RefreshCw className="h-3 w-3" />
            Tentar novamente
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-1.5">
      <Label htmlFor={id} className="text-gray-700 font-medium">
        {label}
        {hint && <span className="ml-1 text-xs text-gray-400 font-normal">{hint}</span>}
      </Label>
      <div className="relative">
        <select
          id={id}
          className={selectClass}
          value={value}
          onChange={e => onChange(e.target.value)}
          disabled={disabled || isLoading}
        >
          <option value="">
            {isLoading ? `Carregando ${label.toLowerCase()}...` : placeholder}
          </option>
          {children}
        </select>
        {isLoading && (
          <Loader2 className="absolute right-3 top-3 h-4 w-4 animate-spin text-gray-400 pointer-events-none" />
        )}
      </div>
    </div>
  );
}

export default function FipeCascadePicker({ tipo, onPriceSelected }: Props) {
  const [brandId, setBrandId] = useState("");
  const [modelId, setModelId] = useState("");
  const [yearId, setYearId] = useState("");
  const [fipeError, setFipeError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const brands = useQuery({
    queryKey: ["fipe-brands", tipo],
    queryFn: () => getFipeBrands(tipo),
    staleTime: 30 * 60 * 1000,
    retry: 2,
  });

  const models = useQuery({
    queryKey: ["fipe-models", tipo, brandId],
    queryFn: () => getFipeModels(tipo, brandId),
    enabled: !!brandId,
    staleTime: 30 * 60 * 1000,
    retry: 2,
  });

  const years = useQuery({
    queryKey: ["fipe-years", tipo, brandId, modelId],
    queryFn: () => getFipeYears(tipo, brandId, modelId),
    enabled: !!brandId && !!modelId,
    staleTime: 30 * 60 * 1000,
    retry: 2,
  });

  async function handleGetPrice() {
    if (!brandId || !modelId || !yearId) return;
    setFipeError(null);
    setLoading(true);
    try {
      const price = await getFipePrice(tipo, brandId, modelId, yearId);
      onPriceSelected(price, brandId, modelId, yearId);
    } catch {
      setFipeError("Falha ao consultar FIPE. Tente novamente ou preencha manualmente.");
    } finally {
      setLoading(false);
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
      <QuerySelect
        id="marca-select"
        label="Marca"
        value={brandId}
        onChange={handleBrandChange}
        isLoading={brands.isLoading}
        isError={brands.isError}
        onRetry={() => brands.refetch()}
        placeholder="Selecione a marca"
        disabled={false}
      >
        {brands.data?.map(b => (
          <option key={b.id} value={b.id}>{b.nome}</option>
        ))}
      </QuerySelect>

      <QuerySelect
        label="Modelo"
        hint={!brandId ? "(selecione a marca primeiro)" : undefined}
        value={modelId}
        onChange={handleModelChange}
        isLoading={models.isFetching}
        isError={!!brandId && models.isError}
        onRetry={() => models.refetch()}
        placeholder="Selecione o modelo"
        disabled={!brandId}
      >
        {models.data?.map(m => (
          <option key={m.id} value={m.id}>{m.nome}</option>
        ))}
      </QuerySelect>

      <QuerySelect
        label="Ano / Combustível"
        hint={!modelId ? "(selecione o modelo primeiro)" : undefined}
        value={yearId}
        onChange={v => setYearId(v)}
        isLoading={years.isFetching}
        isError={!!modelId && years.isError}
        onRetry={() => years.refetch()}
        placeholder="Selecione o ano"
        disabled={!modelId}
      >
        {years.data?.map(y => (
          <option key={y.id} value={y.id}>{y.nome}</option>
        ))}
      </QuerySelect>

      {fipeError && (
        <div className="flex items-center justify-between gap-2 rounded-md bg-amber-50 border border-amber-200 p-3">
          <span className="text-amber-800 text-sm">{fipeError}</span>
          <Button size="sm" variant="outline" onClick={handleGetPrice} className="shrink-0">
            Tentar novamente
          </Button>
        </div>
      )}

      <Button
        type="button"
        onClick={handleGetPrice}
        disabled={!brandId || !modelId || !yearId || loading}
        className="w-full bg-slate-800 hover:bg-slate-700 text-white cursor-pointer"
      >
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Consultando...
          </>
        ) : (
          "Consultar FIPE"
        )}
      </Button>
    </div>
  );
}
