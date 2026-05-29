import { useEffect, useState } from "react";
import { api } from "../../lib/api";

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  is_active: boolean;
}

export default function AdminUsers() {
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.get<UserItem[]>("/v1/users")
      .then((r) => setUsers(r.data))
      .catch(() => setError("Erro ao carregar usuários."))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Carregando...</div>;
  if (error) return <div className="p-8 text-red-600">{error}</div>;

  return (
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Usuários</h1>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-gray-500">
            <th className="pb-2 pr-4">Email</th>
            <th className="pb-2 pr-4">Nome</th>
            <th className="pb-2 pr-4">Perfil</th>
            <th className="pb-2">Ativo</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-b last:border-0">
              <td className="py-3 pr-4 text-gray-900">{u.email}</td>
              <td className="py-3 pr-4 text-gray-700">{u.name}</td>
              <td className="py-3 pr-4">
                <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-800">
                  {u.role}
                </span>
              </td>
              <td className="py-3">
                {u.is_active ? (
                  <span className="text-green-600">✓</span>
                ) : (
                  <span className="text-gray-400">—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
