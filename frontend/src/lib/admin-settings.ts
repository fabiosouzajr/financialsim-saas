import { api } from "./api";

export interface SettingItem {
  value: string;
  source: "db" | "env";
}

export async function getAdminSettings(): Promise<Record<string, SettingItem>> {
  const { data } = await api.get<Record<string, SettingItem>>("/v1/admin/settings");
  return data;
}

export async function updateAdminSetting(key: string, value: string): Promise<void> {
  await api.put(`/v1/admin/settings/${key}`, { value });
}
