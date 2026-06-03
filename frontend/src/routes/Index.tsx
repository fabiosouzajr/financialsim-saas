import { useNavigate, Link } from "react-router-dom";
import {
  Calculator,
  Users,
  Car,
  FileText,
  ShieldCheck,
  LogOut,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";

function decodeRole(token: string): string | null {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role ?? null;
  } catch {
    return null;
  }
}

const NAV_ITEMS = [
  {
    label: "Simulação",
    description: "Criar e consultar simulações de financiamento",
    href: "/simulacao",
    icon: Calculator,
    roles: null,
  },
  {
    label: "Clientes",
    description: "Cadastro e gestão de clientes",
    href: "/clientes",
    icon: Users,
    roles: null,
  },
  {
    label: "Veículos",
    description: "Cadastro e gestão de veículos",
    href: "/veiculos",
    icon: Car,
    roles: null,
  },
  {
    label: "Propostas",
    description: "Acompanhe o ciclo de vida das propostas",
    href: "/propostas",
    icon: FileText,
    roles: ["admin", "manager", "user"],
  },
  {
    label: "Usuários",
    description: "Gerenciar usuários e permissões",
    href: "/admin/users",
    icon: ShieldCheck,
    roles: ["admin"],
  },
];

export default function Index() {
  const { tokens, logout } = useAuth();
  const navigate = useNavigate();

  const role = tokens ? decodeRole(tokens.access) : null;

  const visibleItems = NAV_ITEMS.filter(
    (item) => !item.roles || (role && item.roles.includes(role))
  );

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="min-h-screen bg-[#020617] text-[#F8FAFC] font-[IBM_Plex_Sans,sans-serif]">
      <header className="flex items-center justify-between px-6 py-4 border-b border-[#1E293B]">
        <span className="text-lg font-semibold tracking-tight text-[#22C55E]">
          FinacialSim
        </span>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 text-sm text-[#94A3B8] hover:text-[#F8FAFC] transition-colors duration-200 cursor-pointer"
        >
          <LogOut size={16} />
          Sair
        </button>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-12">
        <h1 className="text-2xl font-semibold mb-2">Bem-vindo</h1>
        <p className="text-[#94A3B8] mb-10">
          Selecione uma área para começar
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {visibleItems.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                to={item.href}
                className="group block rounded-xl bg-[#0F172A] border border-[#1E293B] p-6 hover:border-[#22C55E]/50 hover:shadow-lg transition-all duration-200 cursor-pointer"
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="flex items-center justify-center w-10 h-10 rounded-lg bg-[#1E293B] group-hover:bg-[#22C55E]/10 transition-colors duration-200">
                    <Icon size={20} className="text-[#22C55E]" />
                  </span>
                  <span className="font-semibold">{item.label}</span>
                </div>
                <p className="text-sm text-[#94A3B8] leading-relaxed">
                  {item.description}
                </p>
              </Link>
            );
          })}
        </div>
      </main>
    </div>
  );
}
