import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Health from "./routes/Health";
import Index from "./routes/Index";
import Login from "./routes/Login";
import ForgotPassword from "./routes/ForgotPassword";
import ResetPassword from "./routes/ResetPassword";
import AdminUsers from "./routes/admin/Users";
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
              path="/admin/users"
              element={
                <RequireRole roles={["admin"]}>
                  <AdminUsers />
                </RequireRole>
              }
            />
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
