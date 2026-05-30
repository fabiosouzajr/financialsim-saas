# Phase 3 — Cadastros Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Part 1 (Backend):** `docs/superpowers/plans/2026-05-30-saas-phase-3-backend.md` — must be complete before this part.

**Goal:** Build the Simulação form (Phase 2 prerequisite), then add `/clientes` and `/veículos` pages with FIPE cascade picker, and wire Client/Vehicle pickers into the Simulação form.

**Architecture:** Phase 2 frontend (Simulação form with live preview) is built first as a required block, using the existing Phase 2 plan. Phase 3 adds three new routes: `/clientes` (list + create/edit modal with PF/PJ toggle, mod-11 inline validation, CEP autocomplete), `/veiculos` (list + FIPE cascade create modal with manual fallback), and updates the Simulação form to use combobox pickers for client and vehicle instead of free-text inputs. TanStack Query for all server state; react-hook-form + zod for forms; shadcn/ui primitives (Dialog, Select, Input, Badge).

**Tech Stack:** React 19, Vite, TypeScript, Tailwind v4, shadcn/ui, react-hook-form, zod, TanStack Query v5, axios

---

## File Map

**Phase 2 prerequisite:**

- See `docs/superpowers/plans/2026-05-30-saas-phase-2-frontend.md` (Task 13 executes it)

**Create (Phase 3):**

- `frontend/src/lib/utils.ts` — shadcn `cn()` helper
- `frontend/src/lib/fipe.ts` — FIPE API calls
- `frontend/src/lib/cep.ts` — CEP API call
- `frontend/src/lib/clients.ts` — Client API calls
- `frontend/src/lib/vehicles.ts` — Vehicle API calls
- `frontend/src/components/ui/dialog.tsx` — shadcn Dialog primitive
- `frontend/src/components/ui/badge.tsx` — shadcn Badge primitive
- `frontend/src/components/ui/select.tsx` — shadcn Select primitive
- `frontend/src/components/ui/input.tsx` — shadcn Input primitive
- `frontend/src/components/ui/button.tsx` — shadcn Button primitive
- `frontend/src/components/ui/label.tsx` — shadcn Label primitive
- `frontend/src/routes/clientes/ClientesPage.tsx` — list + modal
- `frontend/src/routes/veiculos/VeiculosPage.tsx` — list + FIPE modal
- `frontend/src/routes/veiculos/FipeCascadePicker.tsx` — cascade selects component
- `frontend/src/tests/clientes.test.tsx`
- `frontend/src/tests/veiculos.test.tsx`

**Modify (Phase 3):**

- `frontend/package.json` — add shadcn peer deps
- `frontend/src/App.tsx` — add `/clientes`, `/veiculos`, `/simulacao`, `/simulacao/:id` routes
- `frontend/src/routes/simulacao/SimulacaoForm.tsx` — replace text inputs with client/vehicle pickers (after Phase 2 is built)

---

## Task 13: Phase 2 Frontend prerequisite — Simulação form

**Context:** The simulação form does not exist yet. It must be built before Phase 3 can add client/vehicle pickers to it. The full plan is at `docs/superpowers/plans/2026-05-30-saas-phase-2-frontend.md`.

- [ ] **Step 1: Execute the Phase 2 frontend plan**

Read and execute every task in `docs/superpowers/plans/2026-05-30-saas-phase-2-frontend.md` from start to finish.

The plan covers:

1. Install recharts + radix-ui peer deps
2. shadcn/ui init (cn helper, slider, switch, tabs components)
3. Form primitives (Input, Label, Button, Select)
4. `useBusinessRules` hook — `GET /api/v1/business-rules`
5. `useSimulationPreview` hook — debounced `POST /api/v1/simulations/preview`
6. `SimulacaoForm.tsx` — react-hook-form + zod, live preview, fees/extras
7. `ResultCards.tsx`, `ScheduleTable.tsx`, `SimulacaoCharts.tsx`
8. `Simulacao.tsx` page (create) + `SimulacaoEdit.tsx` page (edit existing)
9. Register `/simulacao` and `/simulacao/:id` routes in `App.tsx`
10. Vitest tests

- [ ] **Step 2: Verify Phase 2 frontend works**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run dev
```

Open `http://localhost:5173/simulacao`. Confirm: form renders, live preview updates on input change, save creates simulation.

- [ ] **Step 3: Run frontend tests**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run test
```

Expected: PASS

---

## Task 14: Install Phase 3 frontend dependencies

**Files:**

- Modify: `frontend/package.json`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/components/ui/dialog.tsx`
- Create: `frontend/src/components/ui/badge.tsx`
- Create: `frontend/src/components/ui/select.tsx`
- Create: `frontend/src/components/ui/input.tsx`
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/label.tsx`

**Note:** If Phase 2 already installed these deps and created these files, skip the install step and verify.

- [ ] **Step 1: Install shadcn peer deps**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm install \
  @radix-ui/react-dialog \
  @radix-ui/react-select \
  @radix-ui/react-label \
  @radix-ui/react-badge \
  class-variance-authority \
  clsx \
  tailwind-merge \
  lucide-react
```

- [ ] **Step 2: Create `frontend/src/lib/utils.ts`** (skip if already exists)

```typescript
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Create `frontend/src/components/ui/button.tsx`** (skip if already exists)

```typescript
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  )
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 4: Create `frontend/src/components/ui/input.tsx`** (skip if already exists)

```typescript
import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
        "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";

export { Input };
```

- [ ] **Step 5: Create `frontend/src/components/ui/label.tsx`** (skip if already exists)

```typescript
import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
);

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> & VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn(labelVariants(), className)} {...props} />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
```

- [ ] **Step 6: Create `frontend/src/components/ui/badge.tsx`**

```typescript
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        success: "border-transparent bg-green-100 text-green-800",
        warning: "border-transparent bg-yellow-100 text-yellow-800",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
```

- [ ] **Step 7: Create `frontend/src/components/ui/dialog.tsx`**

```typescript
import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

const Dialog = DialogPrimitive.Root;
const DialogTrigger = DialogPrimitive.Trigger;
const DialogPortal = DialogPrimitive.Portal;
const DialogClose = DialogPrimitive.Close;

const DialogOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cn(
      "fixed inset-0 z-50 bg-black/80 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
      className
    )}
    {...props}
  />
));
DialogOverlay.displayName = DialogPrimitive.Overlay.displayName;

const DialogContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content>
>(({ className, children, ...props }, ref) => (
  <DialogPortal>
    <DialogOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cn(
        "fixed left-[50%] top-[50%] z-50 grid w-full max-w-lg translate-x-[-50%] translate-y-[-50%] gap-4 bg-background p-6 shadow-lg duration-200 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 data-[state=closed]:slide-out-to-left-1/2 data-[state=open]:slide-in-from-left-1/2 rounded-lg",
        className
      )}
      {...props}
    >
      {children}
      <DialogClose className="absolute right-4 top-4 rounded-sm opacity-70 hover:opacity-100">
        <X className="h-4 w-4" />
      </DialogClose>
    </DialogPrimitive.Content>
  </DialogPortal>
));
DialogContent.displayName = DialogPrimitive.Content.displayName;

const DialogHeader = ({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("flex flex-col space-y-1.5 text-center sm:text-left", className)} {...props} />
);

const DialogTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cn("text-lg font-semibold leading-none tracking-tight", className)}
    {...props}
  />
));
DialogTitle.displayName = DialogPrimitive.Title.displayName;

export { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle, DialogClose };
```

- [ ] **Step 8: Create `frontend/src/components/ui/select.tsx`**

```typescript
import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const Select = SelectPrimitive.Root;
const SelectGroup = SelectPrimitive.Group;
const SelectValue = SelectPrimitive.Value;

const SelectTrigger = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Trigger>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Trigger>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Trigger
    ref={ref}
    className={cn(
      "flex h-10 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
      className
    )}
    {...props}
  >
    {children}
    <SelectPrimitive.Icon asChild>
      <ChevronDown className="h-4 w-4 opacity-50" />
    </SelectPrimitive.Icon>
  </SelectPrimitive.Trigger>
));
SelectTrigger.displayName = SelectPrimitive.Trigger.displayName;

const SelectContent = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Content>
>(({ className, children, position = "popper", ...props }, ref) => (
  <SelectPrimitive.Portal>
    <SelectPrimitive.Content
      ref={ref}
      className={cn(
        "relative z-50 max-h-96 min-w-[8rem] overflow-hidden rounded-md border bg-popover text-popover-foreground shadow-md data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95",
        position === "popper" && "translate-y-1",
        className
      )}
      position={position}
      {...props}
    >
      <SelectPrimitive.Viewport className="p-1">{children}</SelectPrimitive.Viewport>
    </SelectPrimitive.Content>
  </SelectPrimitive.Portal>
));
SelectContent.displayName = SelectPrimitive.Content.displayName;

const SelectItem = React.forwardRef<
  React.ElementRef<typeof SelectPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof SelectPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <SelectPrimitive.Item
    ref={ref}
    className={cn(
      "relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-8 pr-2 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
      className
    )}
    {...props}
  >
    <span className="absolute left-2 flex h-3.5 w-3.5 items-center justify-center">
      <SelectPrimitive.ItemIndicator>
        <Check className="h-4 w-4" />
      </SelectPrimitive.ItemIndicator>
    </span>
    <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
  </SelectPrimitive.Item>
));
SelectItem.displayName = SelectPrimitive.Item.displayName;

export { Select, SelectGroup, SelectValue, SelectTrigger, SelectContent, SelectItem };
```

- [ ] **Step 9: Add Vite path alias for `@/` (if not already set)**

In `frontend/vite.config.ts`, ensure the resolve alias is present:

```typescript
import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
```

In `frontend/tsconfig.app.json`, ensure:

```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["src/*"]
    }
  }
}
```

- [ ] **Step 10: Verify build**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run build
```

Expected: build succeeds with no errors.

- [ ] **Step 11: Commit**

```bash
git add frontend/package.json frontend/src/lib/utils.ts frontend/vite.config.ts \
  frontend/tsconfig.app.json frontend/src/components/
git commit -m "feat(ui): add shadcn/ui primitives (Button, Input, Label, Badge, Dialog, Select)"
```

---

## Task 15: API lib files (clients, vehicles, FIPE, CEP)

**Files:**

- Create: `frontend/src/lib/clients.ts`
- Create: `frontend/src/lib/vehicles.ts`
- Create: `frontend/src/lib/fipe.ts`
- Create: `frontend/src/lib/cep.ts`

- [ ] **Step 1: Create `frontend/src/lib/clients.ts`**

```typescript
import api from "./api";

export interface ClientOut {
  id: string;
  tenant_id: string;
  nome: string;
  cpf_cnpj: string;
  tipo: "pf" | "pj";
  rg: string | null;
  data_nasc: string | null;
  profissao: string | null;
  renda: string | null;
  telefone: string | null;
  email: string | null;
  endereco_json: Record<string, string> | null;
  observacoes: string | null;
  is_active: boolean;
  criado_por: string;
  criado_em: string;
  atualizado_em: string;
}

export interface ClientListPage {
  items: ClientOut[];
  next_cursor: string | null;
}

export interface ClientIn {
  nome: string;
  cpf_cnpj: string;
  tipo: "pf" | "pj";
  rg?: string | null;
  data_nasc?: string | null;
  profissao?: string | null;
  renda?: string | null;
  telefone?: string | null;
  email?: string | null;
  endereco_json?: Record<string, string> | null;
  observacoes?: string | null;
}

export async function listClients(params?: { q?: string; cursor?: string }): Promise<ClientListPage> {
  const { data } = await api.get<ClientListPage>("/api/v1/clients", { params });
  return data;
}

export async function createClient(body: ClientIn): Promise<ClientOut> {
  const { data } = await api.post<ClientOut>("/api/v1/clients", body);
  return data;
}

export async function getClient(id: string): Promise<ClientOut> {
  const { data } = await api.get<ClientOut>(`/api/v1/clients/${id}`);
  return data;
}

export async function updateClient(id: string, body: ClientIn): Promise<ClientOut> {
  const { data } = await api.patch<ClientOut>(`/api/v1/clients/${id}`, body);
  return data;
}

export async function deactivateClient(id: string): Promise<ClientOut> {
  const { data } = await api.post<ClientOut>(`/api/v1/clients/${id}/deactivate`);
  return data;
}
```

- [ ] **Step 2: Create `frontend/src/lib/vehicles.ts`**

```typescript
import api from "./api";

export interface VehicleOut {
  id: string;
  tenant_id: string;
  fonte: string;
  tipo: string;
  marca: string;
  modelo: string;
  ano_modelo: number;
  combustivel: string | null;
  codigo_fipe: string | null;
  valor_fipe: string | null;
  valor_referencia: string | null;
  mes_referencia_fipe: string | null;
  cor: string | null;
  placa: string | null;
  odometro_km: number | null;
  status: "ativo" | "reservado" | "vendido" | "inativo";
  snapshot_json: Record<string, unknown> | null;
  criado_por: string;
  criado_em: string;
  atualizado_em: string;
}

export interface VehicleListPage {
  items: VehicleOut[];
  next_cursor: string | null;
}

export interface VehicleIn {
  fonte: string;
  tipo: string;
  marca: string;
  modelo: string;
  ano_modelo: number;
  combustivel?: string | null;
  codigo_fipe?: string | null;
  valor_fipe?: string | null;
  valor_referencia?: string | null;
  mes_referencia_fipe?: string | null;
  cor?: string | null;
  placa?: string | null;
  odometro_km?: number | null;
  snapshot_json?: Record<string, unknown> | null;
}

export async function listVehicles(params?: { status?: string; placa?: string; cursor?: string }): Promise<VehicleListPage> {
  const { data } = await api.get<VehicleListPage>("/api/v1/vehicles", { params });
  return data;
}

export async function createVehicle(body: VehicleIn): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>("/api/v1/vehicles", body);
  return data;
}

export async function getVehicle(id: string): Promise<VehicleOut> {
  const { data } = await api.get<VehicleOut>(`/api/v1/vehicles/${id}`);
  return data;
}

export async function setVehicleStatus(id: string, status: string): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>(`/api/v1/vehicles/${id}/status`, { status });
  return data;
}

export async function refreshVehicleFipe(id: string): Promise<VehicleOut> {
  const { data } = await api.post<VehicleOut>(`/api/v1/vehicles/${id}/refresh-fipe`);
  return data;
}
```

- [ ] **Step 3: Create `frontend/src/lib/fipe.ts`**

```typescript
import api from "./api";

export interface FipeBrand { id: string; nome: string; }
export interface FipeModel { id: string; nome: string; }
export interface FipeYear  { id: string; nome: string; }

export interface FipePrice {
  tipo: string;
  marca: string;
  marca_id: string;
  modelo: string;
  modelo_id: string;
  ano_modelo: number;
  combustivel: string;
  codigo_fipe: string;
  valor: string;
  mes_referencia: string;
  fonte: string;
}

export async function getFipeBrands(tipo: string): Promise<FipeBrand[]> {
  const { data } = await api.get<FipeBrand[]>("/api/v1/fipe/brands", { params: { tipo } });
  return data;
}

export async function getFipeModels(tipo: string, brand_id: string): Promise<FipeModel[]> {
  const { data } = await api.get<FipeModel[]>("/api/v1/fipe/models", { params: { tipo, brand_id } });
  return data;
}

export async function getFipeYears(tipo: string, brand_id: string, model_id: string): Promise<FipeYear[]> {
  const { data } = await api.get<FipeYear[]>("/api/v1/fipe/years", { params: { tipo, brand_id, model_id } });
  return data;
}

export async function getFipePrice(tipo: string, brand_id: string, model_id: string, year_id: string): Promise<FipePrice> {
  const { data } = await api.get<FipePrice>("/api/v1/fipe/price", { params: { tipo, brand_id, model_id, year_id } });
  return data;
}
```

- [ ] **Step 4: Create `frontend/src/lib/cep.ts`**

```typescript
import api from "./api";

export interface CepResult {
  cep?: string;
  logradouro?: string;
  complemento?: string;
  bairro?: string;
  localidade?: string;
  uf?: string;
}

export async function lookupCep(cep: string): Promise<CepResult> {
  try {
    const { data } = await api.get<CepResult>(`/api/v1/cep/${cep.replace(/\D/g, "")}`);
    return data;
  } catch {
    return {};
  }
}
```

- [ ] **Step 5: Verify TypeScript**

```bash
cd /home/fj/git/financialsim-saas/frontend
npx tsc --noEmit
```

Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/clients.ts frontend/src/lib/vehicles.ts \
  frontend/src/lib/fipe.ts frontend/src/lib/cep.ts
git commit -m "feat(lib): add client, vehicle, FIPE, CEP API lib functions"
```

---

## Task 16: Clientes page

**Files:**

- Create: `frontend/src/routes/clientes/ClientesPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create `frontend/src/routes/clientes/ClientesPage.tsx`**

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  listClients, createClient, updateClient, deactivateClient,
  type ClientOut, type ClientIn,
} from "@/lib/clients";
import { lookupCep } from "@/lib/cep";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";

// CPF mod-11 inline validation
function isValidCpf(cpf: string): boolean {
  const d = cpf.replace(/\D/g, "");
  if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
  const calc = (len: number) =>
    ([...d.slice(0, len)].reduce((s, x, i) => s + +x * (len + 1 - i), 0) * 10) % 11;
  return calc(9) % 10 === +d[9] && calc(10) % 10 === +d[10];
}

// CNPJ mod-11 inline validation
function isValidCnpj(cnpj: string): boolean {
  const d = cnpj.replace(/\D/g, "");
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
  const w1 = [5,4,3,2,9,8,7,6,5,4,3,2];
  const w2 = [6,...w1];
  const calc = (digits: number[], weights: number[]) => {
    const s = digits.slice(0, weights.length).reduce((a, x, i) => a + x * weights[i], 0);
    const r = s % 11;
    return r < 2 ? 0 : 11 - r;
  };
  const nums = [...d].map(Number);
  return calc(nums, w1) === nums[12] && calc(nums, w2) === nums[13];
}

const pfSchema = z.object({
  tipo: z.literal("pf"),
  nome: z.string().min(2, "Nome obrigatório"),
  cpf_cnpj: z.string().refine(v => isValidCpf(v), { message: "CPF inválido" }),
  rg: z.string().optional(),
  data_nasc: z.string().optional(),
  profissao: z.string().optional(),
  renda: z.string().optional(),
  telefone: z.string().optional(),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  cep: z.string().optional(),
  logradouro: z.string().optional(),
  bairro: z.string().optional(),
  localidade: z.string().optional(),
  uf: z.string().optional(),
  observacoes: z.string().optional(),
});

const pjSchema = z.object({
  tipo: z.literal("pj"),
  nome: z.string().min(2, "Nome obrigatório"),
  cpf_cnpj: z.string().refine(v => isValidCnpj(v), { message: "CNPJ inválido" }),
  renda: z.string().optional(),
  telefone: z.string().optional(),
  email: z.string().email("Email inválido").optional().or(z.literal("")),
  cep: z.string().optional(),
  logradouro: z.string().optional(),
  bairro: z.string().optional(),
  localidade: z.string().optional(),
  uf: z.string().optional(),
  observacoes: z.string().optional(),
});

const clientSchema = z.discriminatedUnion("tipo", [pfSchema, pjSchema]);
type ClientForm = z.infer<typeof clientSchema>;

function formToClientIn(data: ClientForm): ClientIn {
  const endereco = data.cep ? {
    cep: data.cep,
    logradouro: (data as any).logradouro ?? "",
    bairro: (data as any).bairro ?? "",
    localidade: (data as any).localidade ?? "",
    uf: (data as any).uf ?? "",
  } : null;
  return {
    nome: data.nome,
    cpf_cnpj: data.cpf_cnpj.replace(/\D/g, ""),
    tipo: data.tipo,
    rg: data.tipo === "pf" ? (data as any).rg || null : null,
    data_nasc: data.tipo === "pf" ? (data as any).data_nasc || null : null,
    profissao: data.tipo === "pf" ? (data as any).profissao || null : null,
    renda: data.renda || null,
    telefone: data.telefone || null,
    email: data.email || null,
    endereco_json: endereco,
    observacoes: data.observacoes || null,
  };
}

function ClientModal({
  editing,
  onClose,
}: {
  editing: ClientOut | null;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [tipo, setTipo] = useState<"pf" | "pj">(editing?.tipo ?? "pf");
  const [cepLoading, setCepLoading] = useState(false);

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<ClientForm>({
    resolver: zodResolver(clientSchema),
    defaultValues: editing
      ? {
          tipo: editing.tipo,
          nome: editing.nome,
          cpf_cnpj: editing.cpf_cnpj,
          rg: editing.rg ?? "",
          data_nasc: editing.data_nasc ?? "",
          profissao: editing.profissao ?? "",
          renda: editing.renda ?? "",
          telefone: editing.telefone ?? "",
          email: editing.email ?? "",
          cep: editing.endereco_json?.cep ?? "",
          logradouro: editing.endereco_json?.logradouro ?? "",
          bairro: editing.endereco_json?.bairro ?? "",
          localidade: editing.endereco_json?.localidade ?? "",
          uf: editing.endereco_json?.uf ?? "",
          observacoes: editing.observacoes ?? "",
        }
      : { tipo: "pf" },
  });

  const mutation = useMutation({
    mutationFn: (data: ClientForm) =>
      editing
        ? updateClient(editing.id, formToClientIn(data))
        : createClient(formToClientIn(data)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["clients"] });
      onClose();
    },
  });

  async function handleCepBlur(e: React.FocusEvent<HTMLInputElement>) {
    const cep = e.target.value.replace(/\D/g, "");
    if (cep.length !== 8) return;
    setCepLoading(true);
    const result = await lookupCep(cep);
    setCepLoading(false);
    if (result.logradouro) {
      setValue("logradouro" as any, result.logradouro);
      setValue("bairro" as any, result.bairro ?? "");
      setValue("localidade" as any, result.localidade ?? "");
      setValue("uf" as any, result.uf ?? "");
    }
  }

  return (
    <form onSubmit={handleSubmit(d => mutation.mutate(d))} className="space-y-4">
      {/* PF/PJ toggle */}
      <div className="flex gap-2">
        {(["pf", "pj"] as const).map(t => (
          <button
            key={t}
            type="button"
            onClick={() => { setTipo(t); setValue("tipo", t); }}
            className={`px-4 py-1.5 rounded-md text-sm font-medium border ${tipo === t ? "bg-primary text-white border-primary" : "border-input"}`}
          >
            {t.toUpperCase()}
          </button>
        ))}
      </div>

      <input type="hidden" {...register("tipo")} value={tipo} />

      <div className="grid gap-2">
        <Label>Nome</Label>
        <Input {...register("nome")} placeholder="Nome completo" />
        {errors.nome && <p className="text-xs text-red-500">{errors.nome.message}</p>}
      </div>

      <div className="grid gap-2">
        <Label>{tipo === "pf" ? "CPF" : "CNPJ"}</Label>
        <Input {...register("cpf_cnpj")} placeholder={tipo === "pf" ? "000.000.000-00" : "00.000.000/0001-00"} />
        {errors.cpf_cnpj && <p className="text-xs text-red-500">{errors.cpf_cnpj.message}</p>}
      </div>

      {tipo === "pf" && (
        <>
          <div className="grid gap-2">
            <Label>RG</Label>
            <Input {...register("rg" as any)} placeholder="RG" />
          </div>
          <div className="grid gap-2">
            <Label>Data de Nascimento</Label>
            <Input type="date" {...register("data_nasc" as any)} />
          </div>
          <div className="grid gap-2">
            <Label>Profissão</Label>
            <Input {...register("profissao" as any)} placeholder="Profissão" />
          </div>
        </>
      )}

      <div className="grid grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label>Renda / Faturamento</Label>
          <Input {...register("renda")} placeholder="0.00" />
        </div>
        <div className="grid gap-2">
          <Label>Telefone</Label>
          <Input {...register("telefone")} placeholder="(11) 99999-9999" />
        </div>
      </div>

      <div className="grid gap-2">
        <Label>Email</Label>
        <Input type="email" {...register("email")} placeholder="email@exemplo.com" />
        {errors.email && <p className="text-xs text-red-500">{errors.email.message}</p>}
      </div>

      {/* CEP autocomplete */}
      <div className="grid gap-2">
        <Label>CEP {cepLoading && <span className="text-xs text-muted-foreground">(buscando...)</span>}</Label>
        <Input {...register("cep")} placeholder="00000-000" onBlur={handleCepBlur} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-2 grid gap-2">
          <Label>Logradouro</Label>
          <Input {...register("logradouro" as any)} />
        </div>
        <div className="grid gap-2">
          <Label>UF</Label>
          <Input {...register("uf" as any)} maxLength={2} />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="grid gap-2">
          <Label>Bairro</Label>
          <Input {...register("bairro" as any)} />
        </div>
        <div className="grid gap-2">
          <Label>Cidade</Label>
          <Input {...register("localidade" as any)} />
        </div>
      </div>

      <div className="grid gap-2">
        <Label>Observações</Label>
        <textarea
          {...register("observacoes")}
          className="flex min-h-[60px] w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
          placeholder="Observações"
        />
      </div>

      {mutation.error && (
        <p className="text-sm text-red-500">
          {(mutation.error as any)?.response?.data?.message ?? "Erro ao salvar"}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
        <Button type="submit" disabled={mutation.isPending}>
          {mutation.isPending ? "Salvando..." : editing ? "Salvar" : "Criar"}
        </Button>
      </div>
    </form>
  );
}

const STATUS_VARIANT: Record<string, "success" | "outline"> = {
  ativo: "success",
  inativo: "outline",
};

export default function ClientesPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<ClientOut | null>(null);
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["clients", q],
    queryFn: () => listClients({ q: q || undefined }),
  });

  const deactivate = useMutation({
    mutationFn: deactivateClient,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["clients"] }),
  });

  function openCreate() { setEditing(null); setOpen(true); }
  function openEdit(c: ClientOut) { setEditing(c); setOpen(true); }
  function handleClose() { setOpen(false); setEditing(null); }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Clientes</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreate}>+ Novo Cliente</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>{editing ? "Editar Cliente" : "Novo Cliente"}</DialogTitle>
            </DialogHeader>
            <ClientModal editing={editing} onClose={handleClose} />
          </DialogContent>
        </Dialog>
      </div>

      <Input
        placeholder="Buscar por nome ou CPF/CNPJ..."
        value={q}
        onChange={e => setQ(e.target.value)}
        className="max-w-sm"
      />

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Nome</th>
                <th className="text-left px-4 py-3 font-medium">CPF/CNPJ</th>
                <th className="text-left px-4 py-3 font-medium">Tipo</th>
                <th className="text-left px-4 py-3 font-medium">Telefone</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-muted-foreground">
                    Nenhum cliente encontrado
                  </td>
                </tr>
              )}
              {data?.items.map(c => (
                <tr key={c.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3 font-medium">{c.nome}</td>
                  <td className="px-4 py-3 text-muted-foreground">{c.cpf_cnpj}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline">{c.tipo.toUpperCase()}</Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{c.telefone ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_VARIANT[c.is_active ? "ativo" : "inativo"]}>
                      {c.is_active ? "Ativo" : "Inativo"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2 justify-end">
                      <Button size="sm" variant="outline" onClick={() => openEdit(c)}>Editar</Button>
                      {c.is_active && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => deactivate.mutate(c.id)}
                        >
                          Desativar
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Add `/clientes` route to `frontend/src/App.tsx`**

Import and add:

```typescript
import ClientesPage from "./routes/clientes/ClientesPage";
// inside the Routes:
<Route path="/clientes" element={<ClientesPage />} />
```

- [ ] **Step 3: Verify in browser**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run dev
```

Navigate to `http://localhost:5173/clientes`. Verify:

- Table renders (empty state shows "Nenhum cliente encontrado")
- "+ Novo Cliente" opens modal
- PF/PJ toggle switches fields
- CEP field: type `01310-100`, tab out → logradouro fills with "Av. Paulista" (requires backend running)
- Invalid CPF shows inline error on submit
- Valid CPF creates client, table refreshes

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/clientes/ frontend/src/App.tsx
git commit -m "feat(ui): add /clientes page with PF/PJ modal, mod-11 validation, CEP autocomplete"
```

---

## Task 17: FIPE cascade picker + Veículos page

**Files:**

- Create: `frontend/src/routes/veiculos/FipeCascadePicker.tsx`
- Create: `frontend/src/routes/veiculos/VeiculosPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing test for FipeCascadePicker**

Create `frontend/src/tests/veiculos.test.tsx`:

```typescript
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import FipeCascadePicker from "../routes/veiculos/FipeCascadePicker";
import * as fipeLib from "../lib/fipe";

const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <QueryClientProvider client={qc}>{children}</QueryClientProvider>
);

test("clears model/year selects when brand changes", async () => {
  vi.spyOn(fipeLib, "getFipeBrands").mockResolvedValue([
    { id: "21", nome: "Toyota" },
    { id: "22", nome: "Honda" },
  ]);
  vi.spyOn(fipeLib, "getFipeModels").mockResolvedValue([
    { id: "4591", nome: "Corolla" },
  ]);
  vi.spyOn(fipeLib, "getFipeYears").mockResolvedValue([]);

  const onPrice = vi.fn();
  render(<FipeCascadePicker tipo="carro" onPriceSelected={onPrice} />, { wrapper: Wrapper });

  await waitFor(() => screen.getByText("Toyota"));
  // select brand
  fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "21" } });
  await waitFor(() => screen.getByText("Corolla"));
  // change brand again
  fireEvent.change(screen.getByLabelText("Marca"), { target: { value: "22" } });
  // model select should be reset (empty/placeholder)
  await waitFor(() => expect(screen.queryByText("Corolla")).toBeNull());
});
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run test -- --reporter=verbose veiculos
```

Expected: FAIL (FipeCascadePicker not found)

- [ ] **Step 3: Create `frontend/src/routes/veiculos/FipeCascadePicker.tsx`**

```typescript
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getFipeBrands, getFipeModels, getFipeYears, getFipePrice, type FipePrice } from "@/lib/fipe";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

const TIPOS = [
  { value: "carro", label: "Carro" },
  { value: "moto", label: "Moto" },
  { value: "caminhao", label: "Caminhão" },
];

interface Props {
  tipo: string;
  onPriceSelected: (price: FipePrice, brandId: string, modelId: string, yearId: string) => void;
}

export default function FipeCascadePicker({ tipo, onPriceSelected }: Props) {
  const [brandId, setBrandId] = useState("");
  const [modelId, setModelId] = useState("");
  const [yearId, setYearId] = useState("");
  const [fipeError, setFipeError] = useState<string | null>(null);

  const brands = useQuery({
    queryKey: ["fipe-brands", tipo],
    queryFn: () => getFipeBrands(tipo),
    staleTime: 30 * 60 * 1000,
  });

  const models = useQuery({
    queryKey: ["fipe-models", tipo, brandId],
    queryFn: () => getFipeModels(tipo, brandId),
    enabled: !!brandId,
    staleTime: 30 * 60 * 1000,
  });

  const years = useQuery({
    queryKey: ["fipe-years", tipo, brandId, modelId],
    queryFn: () => getFipeYears(tipo, brandId, modelId),
    enabled: !!brandId && !!modelId,
    staleTime: 30 * 60 * 1000,
  });

  async function handleGetPrice() {
    if (!brandId || !modelId || !yearId) return;
    setFipeError(null);
    try {
      const price = await getFipePrice(tipo, brandId, modelId, yearId);
      onPriceSelected(price, brandId, modelId, yearId);
    } catch {
      setFipeError("Falha ao consultar FIPE. Tente novamente ou preencha manualmente.");
    }
  }

  function handleBrandChange(v: string) {
    setBrandId(v);
    setModelId("");
    setYearId("");
  }

  function handleModelChange(v: string) {
    setModelId(v);
    setYearId("");
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        <Label htmlFor="marca-select" id="brand-label">Marca</Label>
        <select
          id="marca-select"
          aria-labelledby="brand-label"
          aria-label="Marca"
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={brandId}
          onChange={e => handleBrandChange(e.target.value)}
          disabled={brands.isLoading}
        >
          <option value="">{brands.isLoading ? "Carregando..." : "Selecione a marca"}</option>
          {brands.data?.map(b => <option key={b.id} value={b.id}>{b.nome}</option>)}
        </select>
      </div>

      <div className="grid gap-2">
        <Label>Modelo</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={modelId}
          onChange={e => handleModelChange(e.target.value)}
          disabled={!brandId || models.isLoading}
        >
          <option value="">{models.isLoading ? "Carregando..." : "Selecione o modelo"}</option>
          {models.data?.map(m => <option key={m.id} value={m.id}>{m.nome}</option>)}
        </select>
      </div>

      <div className="grid gap-2">
        <Label>Ano/Combustível</Label>
        <select
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
          value={yearId}
          onChange={e => setYearId(e.target.value)}
          disabled={!modelId || years.isLoading}
        >
          <option value="">{years.isLoading ? "Carregando..." : "Selecione o ano"}</option>
          {years.data?.map(y => <option key={y.id} value={y.id}>{y.nome}</option>)}
        </select>
      </div>

      {fipeError && (
        <div className="flex items-center gap-2 rounded-md bg-yellow-50 border border-yellow-200 p-3">
          <span className="text-yellow-700 text-sm">{fipeError}</span>
          <Button size="sm" variant="outline" onClick={handleGetPrice}>Tentar novamente</Button>
        </div>
      )}

      <Button
        type="button"
        onClick={handleGetPrice}
        disabled={!brandId || !modelId || !yearId}
        className="w-full"
      >
        Consultar FIPE
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run test -- --reporter=verbose veiculos
```

Expected: PASS

- [ ] **Step 5: Create `frontend/src/routes/veiculos/VeiculosPage.tsx`**

```typescript
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  listVehicles, createVehicle, setVehicleStatus, refreshVehicleFipe,
  type VehicleOut, type VehicleIn,
} from "@/lib/vehicles";
import { type FipePrice } from "@/lib/fipe";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import FipeCascadePicker from "./FipeCascadePicker";

const TIPOS = ["carro", "moto", "caminhao"] as const;

const vehicleSchema = z.object({
  modo: z.enum(["fipe", "manual"]),
  tipo: z.enum(TIPOS),
  marca: z.string().min(1, "Obrigatório"),
  modelo: z.string().min(1, "Obrigatório"),
  ano_modelo: z.coerce.number().min(1900).max(2100),
  combustivel: z.string().optional(),
  codigo_fipe: z.string().optional(),
  valor_fipe: z.string().optional(),
  cor: z.string().optional(),
  placa: z.string().optional(),
  odometro_km: z.coerce.number().optional(),
});

type VehicleForm = z.infer<typeof vehicleSchema>;

function VehicleModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [modo, setModo] = useState<"fipe" | "manual">("fipe");
  const [tipo, setTipo] = useState<"carro" | "moto" | "caminhao">("carro");
  const [fipeData, setFipeData] = useState<{
    price: FipePrice; brandId: string; modelId: string; yearId: string;
  } | null>(null);

  const { register, handleSubmit, setValue, formState: { errors } } = useForm<VehicleForm>({
    resolver: zodResolver(vehicleSchema),
    defaultValues: { modo: "fipe", tipo: "carro" },
  });

  const create = useMutation({
    mutationFn: (body: VehicleIn) => createVehicle(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["vehicles"] }); onClose(); },
  });

  function handlePriceSelected(price: FipePrice, brandId: string, modelId: string, yearId: string) {
    setFipeData({ price, brandId, modelId, yearId });
    setValue("marca", price.marca);
    setValue("modelo", price.modelo);
    setValue("ano_modelo", price.ano_modelo);
    setValue("combustivel", price.combustivel);
    setValue("codigo_fipe", price.codigo_fipe);
    setValue("valor_fipe", price.valor);
  }

  function onSubmit(data: VehicleForm) {
    const snapshot = fipeData
      ? {
          marca_id: fipeData.brandId,
          modelo_id: fipeData.modelId,
          year_id: fipeData.yearId,
          ...fipeData.price,
        }
      : null;

    create.mutate({
      fonte: fipeData ? fipeData.price.fonte : "manual",
      tipo: data.tipo,
      marca: data.marca,
      modelo: data.modelo,
      ano_modelo: data.ano_modelo,
      combustivel: data.combustivel || null,
      codigo_fipe: data.codigo_fipe || null,
      valor_fipe: data.valor_fipe || null,
      cor: data.cor || null,
      placa: data.placa || null,
      odometro_km: data.odometro_km || null,
      snapshot_json: snapshot,
    });
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* Tipo selector */}
      <div className="grid gap-2">
        <Label>Tipo de Veículo</Label>
        <div className="flex gap-2">
          {TIPOS.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => { setTipo(t); setValue("tipo", t); }}
              className={`px-3 py-1.5 rounded-md text-sm border ${tipo === t ? "bg-primary text-white border-primary" : "border-input"}`}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <input type="hidden" {...register("tipo")} value={tipo} />
      </div>

      {/* FIPE / Manual toggle */}
      <div className="flex gap-2">
        {(["fipe", "manual"] as const).map(m => (
          <button
            key={m}
            type="button"
            onClick={() => { setModo(m); setValue("modo", m); setFipeData(null); }}
            className={`px-3 py-1.5 rounded-md text-sm border ${modo === m ? "bg-primary text-white border-primary" : "border-input"}`}
          >
            {m === "fipe" ? "Consultar FIPE" : "Preencher manualmente"}
          </button>
        ))}
      </div>
      <input type="hidden" {...register("modo")} value={modo} />

      {modo === "fipe" ? (
        <>
          <FipeCascadePicker tipo={tipo} onPriceSelected={handlePriceSelected} />
          {fipeData && (
            <div className="rounded-md bg-green-50 border border-green-200 p-3 text-sm text-green-800 space-y-1">
              <p className="font-medium">{fipeData.price.marca} {fipeData.price.modelo} {fipeData.price.ano_modelo}</p>
              <p>FIPE: R$ {Number(fipeData.price.valor).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</p>
              <p className="text-xs text-green-600">Referência: {fipeData.price.mes_referencia}</p>
            </div>
          )}
        </>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label>Marca</Label>
              <Input {...register("marca")} placeholder="Ex: Toyota" />
              {errors.marca && <p className="text-xs text-red-500">{errors.marca.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label>Modelo</Label>
              <Input {...register("modelo")} placeholder="Ex: Corolla" />
              {errors.modelo && <p className="text-xs text-red-500">{errors.modelo.message}</p>}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="grid gap-2">
              <Label>Ano</Label>
              <Input type="number" {...register("ano_modelo")} placeholder="2023" />
            </div>
            <div className="grid gap-2">
              <Label>Combustível</Label>
              <Input {...register("combustivel")} placeholder="Gasolina" />
            </div>
          </div>
          <div className="grid gap-2">
            <Label>Valor de referência</Label>
            <Input {...register("valor_fipe")} placeholder="0.00" />
          </div>
        </>
      )}

      {/* Common fields */}
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-2">
          <Label>Cor</Label>
          <Input {...register("cor")} placeholder="Prata" />
        </div>
        <div className="grid gap-2">
          <Label>Placa</Label>
          <Input {...register("placa")} placeholder="ABC1D23" />
        </div>
      </div>
      <div className="grid gap-2">
        <Label>Odômetro (km)</Label>
        <Input type="number" {...register("odometro_km")} placeholder="0" />
      </div>

      {create.error && (
        <p className="text-sm text-red-500">
          {(create.error as any)?.response?.data?.message ?? "Erro ao salvar"}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onClose}>Cancelar</Button>
        <Button type="submit" disabled={create.isPending || (modo === "fipe" && !fipeData)}>
          {create.isPending ? "Salvando..." : "Registrar Veículo"}
        </Button>
      </div>
    </form>
  );
}

const STATUS_COLORS: Record<string, "success" | "warning" | "destructive" | "outline"> = {
  ativo: "success",
  reservado: "warning",
  vendido: "destructive",
  inativo: "outline",
};

export default function VeiculosPage() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["vehicles", statusFilter],
    queryFn: () => listVehicles({ status: statusFilter || undefined }),
  });

  const setStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => setVehicleStatus(id, status),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  const refreshFipe = useMutation({
    mutationFn: (id: string) => refreshVehicleFipe(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["vehicles"] }),
  });

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Veículos</h1>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button>+ Novo Veículo</Button>
          </DialogTrigger>
          <DialogContent className="max-w-xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
              <DialogTitle>Registrar Veículo</DialogTitle>
            </DialogHeader>
            <VehicleModal onClose={() => setOpen(false)} />
          </DialogContent>
        </Dialog>
      </div>

      {/* Status filter */}
      <div className="flex gap-2">
        {["", "ativo", "reservado", "vendido", "inativo"].map(s => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`px-3 py-1 rounded-full text-xs border ${statusFilter === s ? "bg-primary text-white border-primary" : "border-input text-muted-foreground"}`}
          >
            {s || "Todos"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-muted-foreground">Carregando...</p>
      ) : (
        <div className="border rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-4 py-3 font-medium">Veículo</th>
                <th className="text-left px-4 py-3 font-medium">Placa</th>
                <th className="text-left px-4 py-3 font-medium">Valor FIPE</th>
                <th className="text-left px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-muted-foreground">
                    Nenhum veículo encontrado
                  </td>
                </tr>
              )}
              {data?.items.map(v => (
                <tr key={v.id} className="hover:bg-muted/50">
                  <td className="px-4 py-3">
                    <div className="font-medium">{v.marca} {v.modelo}</div>
                    <div className="text-xs text-muted-foreground">{v.ano_modelo} · {v.tipo}</div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{v.placa ?? "—"}</td>
                  <td className="px-4 py-3">
                    {v.valor_fipe
                      ? `R$ ${Number(v.valor_fipe).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`
                      : "—"}
                  </td>
                  <td className="px-4 py-3">
                    <Badge variant={STATUS_COLORS[v.status]}>{v.status}</Badge>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1 justify-end flex-wrap">
                      {v.status === "ativo" && (
                        <Button size="sm" variant="outline"
                          onClick={() => setStatus.mutate({ id: v.id, status: "reservado" })}>
                          Reservar
                        </Button>
                      )}
                      {v.status === "reservado" && (
                        <>
                          <Button size="sm" variant="outline"
                            onClick={() => setStatus.mutate({ id: v.id, status: "vendido" })}>
                            Vender
                          </Button>
                          <Button size="sm" variant="ghost"
                            onClick={() => setStatus.mutate({ id: v.id, status: "ativo" })}>
                            Cancelar
                          </Button>
                        </>
                      )}
                      {v.status === "ativo" && v.fonte !== "manual" && (
                        <Button size="sm" variant="ghost"
                          onClick={() => refreshFipe.mutate(v.id)}>
                          Atualizar FIPE
                        </Button>
                      )}
                      {v.status === "ativo" && (
                        <Button size="sm" variant="ghost"
                          onClick={() => setStatus.mutate({ id: v.id, status: "inativo" })}>
                          Inativar
                        </Button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Add `/veiculos` route to `frontend/src/App.tsx`**

```typescript
import VeiculosPage from "./routes/veiculos/VeiculosPage";
// inside Routes:
<Route path="/veiculos" element={<VeiculosPage />} />
```

- [ ] **Step 7: Verify in browser**

Navigate to `http://localhost:5173/veiculos`:

- Table renders with empty state
- "+ Novo Veículo" opens modal with FIPE/manual toggle
- Selecting carro → marca → modelo → ano → "Consultar FIPE" populates fields (requires backend + internet)
- Manual toggle shows free-text inputs
- FIPE error state shows yellow badge + retry button

- [ ] **Step 8: Run tests**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run test -- --reporter=verbose
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add frontend/src/routes/veiculos/ frontend/src/tests/veiculos.test.tsx frontend/src/App.tsx
git commit -m "feat(ui): add /veiculos page with FIPE cascade picker and status action buttons"
```

---

## Task 18: Simulação form — Client + Vehicle pickers

**Context:** This task modifies the Simulação form built in Task 13. Find `frontend/src/routes/simulacao/SimulacaoForm.tsx` (built by Phase 2 plan). The form currently has free-text `cliente_nome` and `veiculo_descricao` inputs. Replace them with combobox pickers that search existing clients and vehicles.

**Files:**

- Modify: `frontend/src/routes/simulacao/SimulacaoForm.tsx`
- Modify: `frontend/src/routes/simulacao/types.ts` (add client_id, vehicle_id)

- [ ] **Step 1: Add client_id/vehicle_id to the simulação form zod schema**

In `frontend/src/routes/simulacao/types.ts`, update the schema to include:

```typescript
export const simulacaoSchema = z.object({
  // ... existing fields ...
  client_id: z.string().uuid("Selecione um cliente"),
  vehicle_id: z.string().uuid("Selecione um veículo"),
  // remove: cliente_nome, veiculo_descricao
});
```

- [ ] **Step 2: Add client/vehicle pickers to SimulacaoForm.tsx**

Replace the `cliente_nome` and `veiculo_descricao` text inputs with these combobox pickers. Add near the top of the form:

```typescript
// Client picker — search by name/CPF
function ClientPicker({ value, onChange, error }: {
  value: string; onChange: (id: string) => void; error?: string;
}) {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["clients", q],
    queryFn: () => listClients({ q: q || undefined }),
    staleTime: 30_000,
  });
  return (
    <div className="grid gap-2">
      <Label>Cliente</Label>
      <Input
        placeholder="Buscar cliente por nome ou CPF..."
        value={q}
        onChange={e => setQ(e.target.value)}
      />
      {data?.items.length ? (
        <div className="border rounded-md max-h-40 overflow-y-auto">
          {data.items.map(c => (
            <button
              key={c.id}
              type="button"
              onClick={() => { onChange(c.id); setQ(c.nome); }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-muted ${value === c.id ? "bg-muted font-medium" : ""}`}
            >
              {c.nome} <span className="text-muted-foreground text-xs">{c.cpf_cnpj}</span>
            </button>
          ))}
        </div>
      ) : null}
      {value && <p className="text-xs text-green-600">Cliente selecionado: {value}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

// Vehicle picker — search by marca/modelo/placa
function VehiclePicker({ value, onChange, error }: {
  value: string; onChange: (id: string) => void; error?: string;
}) {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["vehicles", { status: "ativo", placa: q || undefined }],
    queryFn: () => listVehicles({ status: "ativo", placa: q || undefined }),
    staleTime: 30_000,
  });
  return (
    <div className="grid gap-2">
      <Label>Veículo</Label>
      <Input
        placeholder="Buscar veículo por placa..."
        value={q}
        onChange={e => setQ(e.target.value)}
      />
      {data?.items.length ? (
        <div className="border rounded-md max-h-40 overflow-y-auto">
          {data.items.map(v => (
            <button
              key={v.id}
              type="button"
              onClick={() => {
                onChange(v.id);
                setQ(`${v.marca} ${v.modelo} ${v.ano_modelo}`);
              }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-muted ${value === v.id ? "bg-muted font-medium" : ""}`}
            >
              {v.marca} {v.modelo} {v.ano_modelo}
              {v.placa && <span className="text-muted-foreground text-xs ml-1">· {v.placa}</span>}
              {v.valor_fipe && (
                <span className="text-muted-foreground text-xs ml-1">
                  · R$ {Number(v.valor_fipe).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
                </span>
              )}
            </button>
          ))}
        </div>
      ) : null}
      {value && <p className="text-xs text-green-600">Veículo selecionado: {value}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}
```

Add to imports at the top of SimulacaoForm.tsx:

```typescript
import { listClients } from "@/lib/clients";
import { listVehicles } from "@/lib/vehicles";
import { useState } from "react";
```

In the form JSX, replace the `cliente_nome` input with:

```typescript
<ClientPicker
  value={watch("client_id")}
  onChange={v => setValue("client_id", v)}
  error={errors.client_id?.message}
/>
```

Replace the `veiculo_descricao` input with:

```typescript
<VehiclePicker
  value={watch("vehicle_id")}
  onChange={v => setValue("vehicle_id", v)}
  error={errors.vehicle_id?.message}
/>
```

- [ ] **Step 3: Verify in browser**

Navigate to `http://localhost:5173/simulacao`:

- Client picker shows search input; typing a name shows matching clients
- Selecting a client highlights it and shows the UUID below
- Same for vehicle picker (filtered to `status=ativo`)
- Submitting form creates a simulation with `client_id` and `vehicle_id`

- [ ] **Step 4: Run all frontend tests**

```bash
cd /home/fj/git/financialsim-saas/frontend
npm run test
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/routes/simulacao/
git commit -m "feat(simulacao): replace free-text inputs with client/vehicle pickers"
```

---

## Self-review

**Spec coverage check:**

| Requirement | Task |
| --- | --- |
| `/clientes` list + create/edit modal | Task 16 |
| PF/PJ toggle swaps fields | Task 16 |
| mod-11 inline validation (CPF + CNPJ) | Task 16 |
| CEP autocomplete fills endereço | Task 16 |
| `/veiculos` list + create modal | Task 17 |
| FIPE cascade picker (tipo → marca → modelo → ano → preço) | Task 17 |
| Cascade clears children on parent change | Task 17 + test |
| Manual fallback when FIPE unavailable | Task 17 |
| Yellow badge + retry on FIPE error | Task 17 |
| Status chips with action buttons | Task 17 |
| Simulação form uses client/vehicle pickers | Task 18 |
| Phase 2 frontend prerequisite | Task 13 |
| shadcn/ui primitives | Task 14 |
| Vitest: PF/PJ toggle; cascade clears children | Tasks 16, 17 |
