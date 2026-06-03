import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Health from "./routes/Health";
import Index from "./routes/Index";
import Login from "./routes/Login";
import ForgotPassword from "./routes/ForgotPassword";
import ResetPassword from "./routes/ResetPassword";
import AdminLayout from "./routes/admin/AdminLayout";
import AdminUsers from "./routes/admin/Users";
import BusinessRules from "./routes/admin/BusinessRules";
import Indicators from "./routes/admin/Indicators";
import AuditLog from "./routes/admin/AuditLog";
import SystemHealth from "./routes/admin/SystemHealth";
import SmtpSettings from "./routes/admin/SmtpSettings";
import PixSettings from "./routes/admin/PixSettings";
import RequireRole from "./components/RequireRole";
import Simulacao from "./routes/Simulacao";
import SimulacaoEdit from "./routes/SimulacaoEdit";
import ClientesPage from "./routes/clientes/ClientesPage";
import VeiculosPage from "./routes/veiculos/VeiculosPage";
import PropostasPage from "./routes/propostas/PropostasPage";

const queryClient = new QueryClient();

function ProtectedIndex() {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <Index />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<ProtectedIndex />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password/:token" element={<ResetPassword />} />
            <Route path="/healthz" element={<Health />} />
            <Route
              path="/admin"
              element={
                <RequireRole roles={["admin"]}>
                  <AdminLayout />
                </RequireRole>
              }
            >
              <Route index element={<Navigate to="regras" replace />} />
              <Route path="regras" element={<BusinessRules />} />
              <Route path="indicadores" element={<Indicators />} />
              <Route path="auditoria" element={<AuditLog />} />
              <Route path="saude" element={<SystemHealth />} />
              <Route path="smtp" element={<SmtpSettings />} />
              <Route path="pix" element={<PixSettings />} />
              <Route path="users" element={<AdminUsers />} />
            </Route>
            <Route path="/simulacao" element={<Simulacao />} />
            <Route path="/simulacao/:id" element={<SimulacaoEdit />} />
            <Route path="/clientes" element={<ClientesPage />} />
            <Route path="/veiculos" element={<VeiculosPage />} />
            <Route
              path="/propostas"
              element={
                <RequireRole roles={["admin", "manager", "user"]}>
                  <PropostasPage />
                </RequireRole>
              }
            />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
