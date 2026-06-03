import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getAdminSettings, updateAdminSetting } from "../../lib/admin-settings";
import EditableField from "../../components/EditableField";

const EMAIL_PROVIDERS = [
  { label: "SMTP", value: "smtp" },
  { label: "SES (AWS)", value: "ses" },
  { label: "Resend", value: "resend" },
];

export default function SmtpSettings() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-settings"],
    queryFn: getAdminSettings,
  });

  if (isLoading || !data) return <div className="p-8 text-[#64748B]">Carregando...</div>;

  function makeSave(key: string) {
    return async (value: string) => {
      await updateAdminSetting(key, value);
      await qc.invalidateQueries({ queryKey: ["admin-settings"] });
    };
  }

  return (
    <div className="p-8 max-w-xl">
      <h1 className="text-xl font-semibold mb-6">Configurações SMTP</h1>
      <div className="bg-[#0F172A] border border-[#1E293B] rounded-lg px-4">
        <EditableField
          label="Provedor de e-mail"
          value={data.email_provider?.value ?? "smtp"}
          type="select"
          options={EMAIL_PROVIDERS}
          onSave={makeSave("email_provider")}
        />
        <EditableField
          label="Host SMTP"
          value={data.smtp_host?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_host")}
        />
        <EditableField
          label="Porta SMTP"
          value={data.smtp_port?.value ?? ""}
          type="number"
          onSave={makeSave("smtp_port")}
        />
        <EditableField
          label="Usuário SMTP"
          value={data.smtp_user?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_user")}
        />
        <EditableField
          label="Senha SMTP"
          value={data.smtp_password?.value ?? ""}
          type="password"
          onSave={makeSave("smtp_password")}
        />
        <EditableField
          label="Usar TLS"
          value={data.smtp_tls?.value ?? "false"}
          type="toggle"
          onSave={makeSave("smtp_tls")}
        />
        <EditableField
          label="Endereço remetente"
          value={data.smtp_from?.value ?? ""}
          type="text"
          onSave={makeSave("smtp_from")}
        />
      </div>
    </div>
  );
}
