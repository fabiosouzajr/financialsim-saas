import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { PreviewPayload, PreviewResponse } from "@/routes/simulacao/types";

const DEBOUNCE_MS = 400;

export function useSimulationPreview() {
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const request = useCallback((payload: PreviewPayload) => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      setLoading(true);
      setError(null);
      try {
        const res = await api.post<PreviewResponse>(
          "/api/v1/simulations/preview",
          payload,
          { signal: abortRef.current.signal }
        );
        setPreview(res.data);
      } catch (e: unknown) {
        if ((e as { name?: string }).name !== "CanceledError") {
          setError("Preview failed");
        }
      } finally {
        setLoading(false);
      }
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return { preview, loading, error, request };
}
