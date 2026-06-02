# Phase 7F — UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the must-have UX items for the staff app: per-route tab titles, favicon + social meta, confirm dialogs on destructive actions, and form-level error summaries.

**Architecture:** Tab titles use `useEffect(() => { document.title = ... }, [])` in each route component. Favicon uses `frontend/public/favicon.svg`. Social meta added to `frontend/index.html`. Confirm dialogs use the existing `dialog.tsx` shadcn component. Form error summaries rendered above the submit button when `Object.keys(errors).length > 0`.

**Scope note:** Portal routes (`/portal/*`) are not yet implemented (depends on Phase 6D). This plan covers existing staff app routes only. Portal UX polish follows when Phase 6D lands.

**Tech Stack:** React 18, React Hook Form, shadcn/ui `dialog.tsx`, Tailwind CSS

**Depends on:** Nothing — pure frontend, no backend changes

---

## File Map

| Action | File |
|--------|------|
| Create | `frontend/public/favicon.svg` |
| Modify | `frontend/index.html` — favicon link, social meta, app title |
| Modify | `frontend/src/routes/Login.tsx` — tab title |
| Modify | `frontend/src/routes/ForgotPassword.tsx` — tab title |
| Modify | `frontend/src/routes/ResetPassword.tsx` — tab title |
| Modify | `frontend/src/routes/Simulacao.tsx` — tab title |
| Modify | `frontend/src/routes/SimulacaoEdit.tsx` — tab title |
| Modify | `frontend/src/routes/clientes/ClientesPage.tsx` — tab title, confirm delete, form errors |
| Modify | `frontend/src/routes/veiculos/VeiculosPage.tsx` — tab title, confirm status change, form errors |
| Modify | `frontend/src/routes/propostas/PropostasPage.tsx` — tab title, confirm cancel |
| Modify | `frontend/src/routes/admin/Users.tsx` — tab title |

---

### Task 1: Favicon and social meta

**Files:**
- Create: `frontend/public/favicon.svg`
- Modify: `frontend/index.html`

- [ ] **Step 1: Create favicon.svg**

`frontend/public/favicon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="6" fill="#2563eb"/>
  <text x="16" y="22" font-family="sans-serif" font-size="18" font-weight="bold"
        text-anchor="middle" fill="white">F</text>
</svg>
```

- [ ] **Step 2: Update index.html**

Replace the entire `<head>` section in `frontend/index.html`:

```html
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>FinacialSim</title>
    <meta name="description" content="Sistema de simulação e gestão de financiamento de veículos" />
    <meta property="og:title" content="FinacialSim" />
    <meta property="og:description" content="Sistema de simulação e gestão de financiamento de veículos" />
    <meta property="og:type" content="website" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="FinacialSim" />
  </head>
```

- [ ] **Step 3: Verify favicon renders**

Start the dev server (`cd frontend && npm run dev`) and open `http://localhost:5173`. Confirm the blue "F" favicon appears in the browser tab.

---

### Task 2: Add tab titles to all routes

For each route below, add a `useEffect` hook that sets `document.title`. If the component already has a `useEffect`, add the title line inside it or add a new one.

- [ ] **Step 1: Login.tsx**

Add inside `Login` component:
```tsx
import { useEffect } from "react";

// inside component:
useEffect(() => { document.title = "Login — FinacialSim"; }, []);
```

- [ ] **Step 2: ForgotPassword.tsx**

```tsx
useEffect(() => { document.title = "Esqueci minha senha — FinacialSim"; }, []);
```

- [ ] **Step 3: ResetPassword.tsx**

```tsx
useEffect(() => { document.title = "Redefinir senha — FinacialSim"; }, []);
```

- [ ] **Step 4: Simulacao.tsx**

```tsx
useEffect(() => { document.title = "Simulações — FinacialSim"; }, []);
```

- [ ] **Step 5: SimulacaoEdit.tsx**

```tsx
useEffect(() => { document.title = "Editar Simulação — FinacialSim"; }, []);
```

- [ ] **Step 6: ClientesPage.tsx**

```tsx
useEffect(() => { document.title = "Clientes — FinacialSim"; }, []);
```

- [ ] **Step 7: VeiculosPage.tsx**

```tsx
useEffect(() => { document.title = "Veículos — FinacialSim"; }, []);
```

- [ ] **Step 8: PropostasPage.tsx**

```tsx
useEffect(() => { document.title = "Propostas — FinacialSim"; }, []);
```

- [ ] **Step 9: Admin/Users.tsx**

```tsx
useEffect(() => { document.title = "Usuários — FinacialSim"; }, []);
```

- [ ] **Step 10: Verify all tab titles in browser**

Navigate to each route and confirm the browser tab shows the correct title.

---

### Task 3: Confirm dialogs for destructive actions

The existing `dialog.tsx` component is already available. Use it to wrap destructive actions.

#### 3a — ClientesPage: deactivate client

- [ ] **Step 1: Add confirm dialog state to ClientesPage**

In `frontend/src/routes/clientes/ClientesPage.tsx`, add state for pending deactivation:

```tsx
const [deactivatePending, setDeactivatePending] = useState<string | null>(null);
```

- [ ] **Step 2: Replace the deactivate button's onClick**

Find the button that calls the deactivate/delete client API and change its `onClick` to:

```tsx
onClick={() => setDeactivatePending(client.id)}
```

- [ ] **Step 3: Add the confirm Dialog**

Add this JSX before the closing `</>` of the component's return:

```tsx
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

// Inside return JSX:
<Dialog open={!!deactivatePending} onOpenChange={() => setDeactivatePending(null)}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Desativar cliente?</DialogTitle>
    </DialogHeader>
    <p className="text-sm text-muted-foreground">
      Esta ação desativará o cliente. O histórico será mantido.
    </p>
    <DialogFooter>
      <Button variant="outline" onClick={() => setDeactivatePending(null)}>
        Cancelar
      </Button>
      <Button
        variant="destructive"
        onClick={() => {
          if (deactivatePending) {
            handleDeactivate(deactivatePending); // your existing deactivate function
            setDeactivatePending(null);
          }
        }}
      >
        Desativar
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>
```

Replace `handleDeactivate` with the actual function name used in your codebase to perform the API call.

#### 3b — PropostasPage: cancel proposal

- [ ] **Step 4: Add confirm dialog for proposal cancellation in PropostasPage.tsx**

Apply the same pattern as ClientesPage. State variable: `cancelPending`. The dialog title is `"Cancelar proposta?"` with text `"Esta ação cancela a proposta e libera o veículo reservado."`.

#### 3c — VeiculosPage: status change to inativo

- [ ] **Step 5: Add confirm dialog for vehicle deactivation in VeiculosPage.tsx**

Apply the same pattern. Only prompt when the new status is `"inativo"`. State variable: `deactivateVehiclePending` (holds vehicle id + new status). Dialog title: `"Desativar veículo?"`.

---

### Task 4: Form-level error summaries

React Hook Form's `formState.errors` object has one key per failing field. Show a summary at the top of the form when there are errors, and focus the first errored field.

#### 4a — Pattern (apply to all forms with React Hook Form)

- [ ] **Step 1: Add error summary component**

Create `frontend/src/components/FormErrorSummary.tsx`:

```tsx
interface Props {
  errors: Record<string, { message?: string } | undefined>;
}

export function FormErrorSummary({ errors }: Props) {
  const messages = Object.values(errors)
    .filter(Boolean)
    .map((e) => e?.message)
    .filter(Boolean) as string[];

  if (messages.length === 0) return null;

  return (
    <div
      role="alert"
      className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <p className="font-medium mb-1">Corrija os erros abaixo:</p>
      <ul className="list-disc list-inside space-y-0.5">
        {messages.map((msg, i) => (
          <li key={i}>{msg}</li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Add FormErrorSummary to ClientesPage form**

In `ClientesPage.tsx`, import and place `<FormErrorSummary errors={formState.errors} />` directly above the form's submit button.

- [ ] **Step 3: Add FormErrorSummary to VeiculosPage form**

Same as above for `VeiculosPage.tsx`.

- [ ] **Step 4: Add FormErrorSummary to Login.tsx**

Add `<FormErrorSummary errors={formState.errors} />` above the login button in `Login.tsx`.

- [ ] **Step 5: Focus first errored field on submit failure**

In each form with React Hook Form, add `criteriaMode: "all"` to `useForm()` and use `setFocus` from RHF to focus the first error field after a failed submission:

```tsx
const { ..., setFocus, formState: { errors } } = useForm({ criteriaMode: "all" });

// In the onSubmit error handler or after form validation:
const firstError = Object.keys(errors)[0];
if (firstError) setFocus(firstError as any);
```

---

### Task 5: Verify and commit

- [ ] **Step 1: Run frontend type check**

```bash
cd frontend && npm run build
```

Expected: No TypeScript errors.

- [ ] **Step 2: Manual verification checklist**

Open `http://localhost:5173` and verify:
- [ ] Browser tab shows "FinacialSim" on index
- [ ] Each route shows correct tab title on navigation
- [ ] Favicon (blue "F") visible in tab
- [ ] Deactivating a client shows a confirm dialog before calling the API
- [ ] Cancelling a proposal shows a confirm dialog
- [ ] Form validation in ClientesPage shows error summary above submit button

- [ ] **Step 3: Commit**

```bash
git add frontend/public/favicon.svg \
        frontend/index.html \
        frontend/src/components/FormErrorSummary.tsx \
        frontend/src/routes/ \
        frontend/src/components/
git commit -m "feat(phase7f): tab titles, favicon, social meta, confirm dialogs, form error summaries"
```
