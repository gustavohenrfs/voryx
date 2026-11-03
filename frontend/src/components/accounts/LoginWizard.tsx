"use client";

import { useState } from "react";
import { Button, ErrorLine, Field } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Account } from "@/lib/types";

type Step = "start" | "code" | "password";
type CodeResult = { status: "ok"; account: Account } | { status: "needs_password" };

export function LoginWizard({ accountId, onDone }: { accountId?: number; onDone: (a: Account) => void }) {
  const [step, setStep] = useState<Step>("start");
  const [phone, setPhone] = useState("");
  const [apiId, setApiId] = useState("");
  const [apiHash, setApiHash] = useState("");
  const [label, setLabel] = useState("");
  const [loginId, setLoginId] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : "erro inesperado";
      setError(msg);
      if (e instanceof ApiError && e.status === 404) setStep("start"); // login expirou
    } finally {
      setBusy(false);
    }
  }

  const start = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const r = await api<{ login_id: string }>("/accounts/login/start", {
        json: {
          phone,
          api_id: Number(apiId),
          api_hash: apiHash.trim(),
          label: label.trim() || null,
          ...(accountId ? { account_id: accountId } : {}),
        },
      });
      setLoginId(r.login_id);
      setStep("code");
    });
  };

  const sendCode = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const r = await api<CodeResult>("/accounts/login/code", { json: { login_id: loginId, code: code.trim() } });
      if (r.status === "needs_password") setStep("password");
      else onDone(r.account);
    });
  };

  const sendPassword = (e: React.FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const r = await api<CodeResult>("/accounts/login/password", { json: { login_id: loginId, password } });
      if (r.status === "ok") onDone(r.account);
    });
  };

  if (step === "code")
    return (
      <form onSubmit={sendCode} className="flex flex-col gap-4">
        <p className="text-sm text-muted">O Telegram mandou um código para {phone} (no app, não por SMS).</p>
        <Field
          label="Código recebido no Telegram"
          inputMode="numeric"
          autoComplete="one-time-code"
          autoFocus
          required
          value={code}
          onChange={(e) => setCode(e.target.value)}
        />
        <ErrorLine error={error} />
        <Button variant="primary" type="submit" busy={busy}>
          Confirmar código
        </Button>
      </form>
    );

  if (step === "password")
    return (
      <form onSubmit={sendPassword} className="flex flex-col gap-4">
        <p className="text-sm text-muted">Essa conta tem verificação em duas etapas. A senha não fica salva.</p>
        <Field
          label="Senha de verificação em duas etapas"
          type="password"
          autoFocus
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <ErrorLine error={error} />
        <Button variant="primary" type="submit" busy={busy}>
          Entrar na conta
        </Button>
      </form>
    );

  return (
    <form onSubmit={start} className="flex flex-col gap-4">
      <Field label="Número com DDI" placeholder="+55 11 99999-0000" required value={phone} onChange={(e) => setPhone(e.target.value)} />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="api_id" inputMode="numeric" required value={apiId} onChange={(e) => setApiId(e.target.value)} />
        <Field label="api_hash" required value={apiHash} onChange={(e) => setApiHash(e.target.value)} />
      </div>
      <p className="text-xs text-muted">
        Pegue o api_id e o api_hash em my.telegram.org, em “API development tools”, logado com o número da conta.
      </p>
      {!accountId && (
        <Field label="Apelido (opcional)" placeholder="Ex.: Ana" value={label} onChange={(e) => setLabel(e.target.value)} />
      )}
      <ErrorLine error={error} />
      <Button variant="primary" type="submit" busy={busy}>
        Enviar código
      </Button>
    </form>
  );
}
