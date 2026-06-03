import { useState } from "react";
import { Check, Pencil, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";

export interface SelectOption {
  label: string;
  value: string;
}

interface EditableFieldProps {
  label: string;
  value: string;
  type?: "text" | "number" | "password" | "select" | "toggle";
  onSave: (value: string, motivo?: string) => Promise<void>;
  motivo?: boolean;
  options?: SelectOption[];
}

export default function EditableField({
  label,
  value,
  type = "text",
  onSave,
  motivo = false,
  options = [],
}: EditableFieldProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [motivoText, setMotivoText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  if (type === "toggle") {
    return (
      <div className="flex items-center justify-between py-3 border-b border-[#1E293B] last:border-0">
        <span className="text-sm text-[#94A3B8]">{label}</span>
        <Switch
          checked={value === "true"}
          disabled={saving}
          onCheckedChange={async (checked) => {
            setSaving(true);
            try {
              await onSave(String(checked));
            } catch (e: unknown) {
              const msg = e instanceof Error ? e.message : "Erro ao salvar";
              setError(msg);
            } finally {
              setSaving(false);
            }
          }}
        />
      </div>
    );
  }

  const displayValue = type === "password" ? (value ? "••••••••" : "") : value;

  if (!editing) {
    return (
      <div className="flex items-center justify-between py-3 border-b border-[#1E293B] last:border-0 group">
        <div>
          <p className="text-xs text-[#64748B]">{label}</p>
          <p className="text-sm text-[#F8FAFC] mt-0.5">{displayValue || "—"}</p>
        </div>
        <button
          onClick={() => {
            setEditing(true);
            setDraft(value);
            setError(null);
            setMotivoText("");
          }}
          className="opacity-0 group-hover:opacity-100 text-[#475569] hover:text-[#94A3B8] transition-opacity cursor-pointer"
        >
          <Pencil size={14} />
        </button>
      </div>
    );
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave(draft, motivo ? motivoText || undefined : undefined);
      setEditing(false);
    } catch (e: unknown) {
      const detail =
        (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? (e instanceof Error ? e.message : "Erro ao salvar"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="py-3 border-b border-[#1E293B] last:border-0 bg-[#22C55E08] rounded px-2 -mx-2">
      <p className="text-xs text-[#64748B] mb-1.5">{label}</p>
      {type === "select" ? (
        <Select value={draft} onValueChange={setDraft}>
          <SelectTrigger className="h-8 text-sm bg-[#0F172A] border-[#22C55E]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <Input
          type={type === "password" ? "password" : type}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="h-8 text-sm bg-[#0F172A] border-[#22C55E]"
          autoFocus
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
        />
      )}
      {motivo && (
        <Input
          placeholder="Motivo (opcional)"
          value={motivoText}
          onChange={(e) => setMotivoText(e.target.value)}
          className="h-7 text-xs bg-[#0F172A] border-[#334155] mt-1.5"
        />
      )}
      {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
      <div className="flex gap-2 mt-2">
        <Button
          size="sm"
          className="h-7 text-xs bg-[#22C55E] text-[#020617] hover:bg-[#16a34a]"
          onClick={handleSave}
          disabled={saving}
        >
          <Check size={12} className="mr-1" />
          Salvar
        </Button>
        <Button
          size="sm"
          variant="outline"
          className="h-7 text-xs border-[#334155] text-[#64748B]"
          onClick={() => setEditing(false)}
          disabled={saving}
        >
          <X size={12} className="mr-1" />
          Cancelar
        </Button>
      </div>
    </div>
  );
}
