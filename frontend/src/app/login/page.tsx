"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button, ErrorLine, Field } from "@/components/ui";
import { api, ApiError } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { json: { email, password } });
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "não foi possível entrar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm">
        <p className="font-display text-5xl tracking-tight text-gold">Voryx</p>
        <p className="mt-2 mb-10 text-sm text-muted">Painel dos grupos de prévias</p>
        <div className="flex flex-col gap-4">
          <Field label="Email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <Field
            label="Senha"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <ErrorLine error={error} />
          <Button variant="primary" type="submit" busy={busy} className="mt-2 w-full">
            Entrar
          </Button>
        </div>
      </form>
    </main>
  );
}
