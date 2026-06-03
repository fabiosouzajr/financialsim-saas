import { useQuery } from "@tanstack/react-query";
import { getAdminSettings } from "../../lib/admin-settings";

export default function PixSettings() {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: getAdminSettings,
  });

  if (isLoading || !data) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-xl font-semibold mb-2">Configurações Pix</h1>
      <p className="text-sm text-[#64748B] mb-6">
        As configurações Pix são definidas por variáveis de ambiente e não podem ser alteradas pelo painel.
      </p>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1E293B]">
          <div>
            <p className="text-xs text-[#64748B]">Provedor Pix</p>
            <p className="text-sm text-[#F8FAFC] mt-0.5">{data.pix_provider?.value ?? "—"}</p>
          </div>
          <span className="text-xs bg-[#1E293B] text-[#475569] px-2 py-0.5 rounded">env</span>
        </div>
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <p className="text-xs text-[#64748B]">Webhook Secret</p>
            <p className="text-sm text-[#F8FAFC] mt-0.5">
              {data.pix_webhook_secret?.value ? "••••••••" : "não configurado"}
            </p>
          </div>
          <span className="text-xs bg-[#1E293B] text-[#475569] px-2 py-0.5 rounded">env</span>
        </div>
      </div>
    </div>
  );
}
