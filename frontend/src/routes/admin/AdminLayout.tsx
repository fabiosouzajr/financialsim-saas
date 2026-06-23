import { NavLink, Outlet } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  Building2,
  ClipboardList,
  CreditCard,
  Mail,
  Settings,
  TrendingUp,
  Users,
} from "lucide-react";

const NAV_ITEMS = [
  { label: "Perfil da Empresa", href: "/admin/perfil", icon: Building2 },
  { label: "Regras de Negócio", href: "/admin/regras", icon: Settings },
  { label: "Indicadores", href: "/admin/indicadores", icon: TrendingUp },
  { label: "Auditoria", href: "/admin/auditoria", icon: ClipboardList },
  { label: "Saúde do Sistema", href: "/admin/saude", icon: Activity },
  { label: "SMTP", href: "/admin/smtp", icon: Mail },
  { label: "Pix", href: "/admin/pix", icon: CreditCard },
  { label: "Usuários", href: "/admin/users", icon: Users },
];

export default function AdminLayout() {
  return (
    <div className="min-h-screen bg-[#020617] text-[#F8FAFC] flex font-[IBM_Plex_Sans,sans-serif]">
      <aside className="w-56 bg-[#0F172A] border-r border-[#1E293B] flex flex-col flex-shrink-0">
        <div className="p-4 border-b border-[#1E293B]">
          <span className="text-[#22C55E] font-semibold text-sm">FinacialSim</span>
          <p className="text-[#475569] text-xs mt-0.5">Painel Admin</p>
        </div>
        <nav className="flex-1 py-2">
          {NAV_ITEMS.map(({ label, href, icon: Icon }) => (
            <NavLink
              key={href}
              to={href}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-4 py-2.5 text-sm transition-colors ${
                  isActive
                    ? "text-[#22C55E] bg-[#22C55E10] border-l-2 border-[#22C55E]"
                    : "text-[#64748B] hover:text-[#94A3B8] hover:bg-[#1E293B]"
                }`
              }
            >
              <Icon size={15} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-4 border-t border-[#1E293B]">
          <NavLink
            to="/"
            className="flex items-center gap-2 text-xs text-[#475569] hover:text-[#94A3B8] transition-colors"
          >
            <ArrowLeft size={13} />
            Voltar ao Dashboard
          </NavLink>
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
