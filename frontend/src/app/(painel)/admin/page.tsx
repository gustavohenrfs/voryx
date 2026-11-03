"use client";

import { useState } from "react";
import { Button, Dialog, ErrorLine, Field, PageHeader } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { useMe } from "@/lib/me";
import type { User } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AdminPage() {
  const me = useMe();
  const { data, error, reload } = useApi<User[]>(me?.role === "admin" ? "/admin/users" : null);
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [pwFor, setPwFor] = useState<User | null>(null);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [formError, setFormError] = useState<string | null>(null);

  if (me?.role !== "admin") return <p className="text-sm text-muted">Só o admin acessa esta página.</p>;

  async function call(fn: () => Promise<unknown>, ok: string) {
    setFormError(null);
    try {
      await fn();
      toast(ok);
      setCreating(false);
      setPwFor(null);
      setForm({ name: "", email: "", password: "" });
      await reload();
    } catch (e) {
      setFormError(e instanceof ApiError ? e.detail : "erro inesperado");
    }
  }

  return (
    <>
      <PageHeader title="Usuários">
        <Button variant="primary" onClick={() => setCreating(true)}>
          Criar parceiro
        </Button>
      </PageHeader>
      <ErrorLine error={error} />
      <ul className="divide-y divide-line border-y border-line">
        {data?.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center gap-3 py-4">
            <div className="min-w-0 flex-1">
              <p className={u.disabled ? "text-muted line-through" : ""}>{u.name}</p>
              <p className="text-xs text-muted">
                {u.email}, {u.role === "admin" ? "admin" : "parceiro"}
              </p>
            </div>
            {u.id !== me.id && (
              <div className="flex gap-2">
                <Button onClick={() => setPwFor(u)}>Trocar senha</Button>
                <Button
                  variant={u.disabled ? "ghost" : "danger"}
                  onClick={() =>
                    call(
                      () => api(`/admin/users/${u.id}`, { method: "PATCH", json: { disabled: !u.disabled } }),
                      u.disabled ? `${u.name} reativado` : `${u.name} desativado`,
                    )
                  }
                >
                  {u.disabled ? "Reativar" : "Desativar"}
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      <Dialog open={creating} onClose={() => setCreating(false)} title="Criar parceiro">
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void call(() => api("/admin/users", { json: form }), `${form.name} criado`);
          }}
        >
          <Field label="Nome" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <Field label="Email" type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          <Field
            label="Senha inicial"
            type="password"
            minLength={8}
            required
            hint="Mínimo de 8 caracteres. Mande para o parceiro por um canal seguro."
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <ErrorLine error={formError} />
          <Button variant="primary" type="submit">
            Criar parceiro
          </Button>
        </form>
      </Dialog>

      <Dialog open={Boolean(pwFor)} onClose={() => setPwFor(null)} title={`Nova senha para ${pwFor?.name ?? ""}`}>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (pwFor)
              void call(
                () => api(`/admin/users/${pwFor.id}`, { method: "PATCH", json: { password: form.password } }),
                "Senha trocada. A pessoa precisa entrar de novo.",
              );
          }}
        >
          <Field
            label="Nova senha"
            type="password"
            minLength={8}
            required
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <ErrorLine error={formError} />
          <Button variant="primary" type="submit">
            Trocar senha
          </Button>
        </form>
      </Dialog>
    </>
  );
}
