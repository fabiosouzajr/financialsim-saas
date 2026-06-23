import { useEffect, useRef, useState } from "react";
import {
  type TenantProfileOut,
  getTenantProfile,
  updateTenantProfile,
  uploadLogo,
} from "@/lib/tenant-profile";

const MAX_LOGO_BYTES = 2 * 1024 * 1024;

export default function TenantProfile() {
  useEffect(() => { document.title = "Perfil da Empresa — FinacialSim"; }, []);

  const [profile, setProfile] = useState<TenantProfileOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [nome, setNome] = useState("");
  const [cnpj, setCnpj] = useState("");
  const [telefone, setTelefone] = useState("");
  const [endereco, setEndereco] = useState("");
  const [validadeDias, setValidadeDias] = useState(15);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    void getTenantProfile().then((p) => {
      setProfile(p);
      setNome(p.nome);
      setCnpj(p.cnpj ?? "");
      setTelefone(p.telefone ?? "");
      setEndereco(p.endereco ?? "");
      setValidadeDias(p.proposta_validade_dias);
      setLoading(false);
    });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const updated = await updateTenantProfile({
        nome,
        cnpj: cnpj || null,
        telefone: telefone || null,
        endereco: endereco || null,
        proposta_validade_dias: validadeDias,
      });
      setProfile(updated);
      setSuccess("Perfil salvo com sucesso.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao salvar perfil");
    } finally {
      setSaving(false);
    }
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_LOGO_BYTES) {
      setError("Logo deve ter no máximo 2 MB.");
      return;
    }
    setLogoUploading(true);
    setError(null);
    try {
      const updated = await uploadLogo(file);
      setProfile(updated);
      setSuccess("Logo enviado com sucesso.");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao enviar logo");
    } finally {
      setLogoUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  if (loading) return <div className="p-8 text-muted-foreground">Carregando…</div>;

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-xl font-semibold mb-6">Perfil da Empresa</h1>

      {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
      {success && <p className="mb-4 text-sm text-green-600">{success}</p>}

      {/* Company info card */}
      <div className="rounded-lg border p-5 mb-6 space-y-4">
        <h2 className="text-sm font-semibold">Dados da empresa</h2>
        <div className="space-y-3">
          {(
            [
              { label: "Nome", value: nome, set: setNome, type: "text" },
              { label: "CNPJ", value: cnpj, set: setCnpj, type: "text" },
              { label: "Telefone", value: telefone, set: setTelefone, type: "text" },
              { label: "Endereço", value: endereco, set: setEndereco, type: "text" },
            ] as const
          ).map(({ label, value, set }) => (
            <div key={label}>
              <label className="block text-xs font-medium text-muted-foreground mb-1">{label}</label>
              <input
                value={value}
                onChange={(e) => set(e.target.value)}
                className="w-full rounded border px-3 py-1.5 text-sm"
              />
            </div>
          ))}
          <div>
            <label className="block text-xs font-medium text-muted-foreground mb-1">
              Validade da proposta (dias, máx. 30)
            </label>
            <input
              type="number"
              min={1}
              max={30}
              value={validadeDias}
              onChange={(e) => setValidadeDias(Number(e.target.value))}
              className="w-32 rounded border px-3 py-1.5 text-sm"
            />
          </div>
        </div>
        <button
          onClick={() => void handleSave()}
          disabled={saving}
          className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground disabled:opacity-50"
        >
          {saving ? "Salvando…" : "Salvar"}
        </button>
      </div>

      {/* Logo card */}
      <div className="rounded-lg border p-5 space-y-3">
        <h2 className="text-sm font-semibold">Logo da empresa</h2>
        {profile?.logo_url && (
          <img
            src={profile.logo_url}
            alt="Logo atual"
            className="max-h-16 object-contain border rounded p-1"
          />
        )}
        <div className="flex items-center gap-3">
          <input
            ref={fileRef}
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => void handleLogoUpload(e)}
            className="text-sm"
          />
          {logoUploading && <span className="text-xs text-muted-foreground">Enviando…</span>}
        </div>
        <p className="text-xs text-muted-foreground">PNG ou JPEG, máx. 2 MB.</p>
      </div>
    </div>
  );
}
