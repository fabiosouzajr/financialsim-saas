import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function Health() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["healthz"],
    queryFn: () => api.get<unknown>("/healthz").then((r) => r.data),
  });

  if (isLoading) return <p className="p-4 text-gray-500">Checking backend…</p>;
  if (isError) return <p className="p-4 text-red-500">API unreachable</p>;

  return (
    <pre className="m-4 rounded-lg bg-gray-100 p-4 font-mono text-sm">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
