"use client";

import { useState } from "react";
import { Button, Dialog, ErrorLine } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Account } from "@/lib/types";

export function ImportSessionDialog({
  account,
  onClose,
  onDone,
}: {
  account: Account | null;
  onClose: () => void;
  onDone: (a: Account) => void;
}) {
  const [session, setSession] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!account) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await api<Account>(`/accounts/${account.id}/session`, { json: { session: session.trim() } }));
      setSession("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "erro inesperado");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={Boolean(account)} onClose={onClose} title="Importar session">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <p className="text-sm text-muted">
          Cole uma StringSession do Telethon gerada para esta conta (por exemplo, pelo TData). Ela substitui a session
          atual e reconecta a conta.
        </p>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">StringSession</span>
          <textarea
            required
            rows={4}
            value={session}
            onChange={(e) => setSession(e.target.value)}
            className="rounded-md border border-line bg-ink p-3 font-mono text-xs break-all text-text focus:border-gold focus:outline-none"
          />
        </label>
        <ErrorLine error={error} />
        <Button variant="primary" type="submit" busy={busy}>
          Importar e reconectar
        </Button>
      </form>
    </Dialog>
  );
}
