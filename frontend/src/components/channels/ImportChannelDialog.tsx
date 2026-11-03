"use client";

import { useEffect, useState } from "react";
import { Button, Dialog, Empty, ErrorLine } from "@/components/ui";
import { api, ApiError } from "@/lib/api";
import type { Account, Channel, Dialog as TgDialog } from "@/lib/types";
import { accountName } from "@/lib/types";

const KIND: Record<string, string> = { channel: "Canal", supergroup: "Grupo", group: "Grupo básico" };

export function ImportChannelDialog({
  open,
  accounts,
  onClose,
  onDone,
}: {
  open: boolean;
  accounts: Account[];
  onClose: () => void;
  onDone: (c: Channel) => void;
}) {
  const usable = accounts.filter((a) => a.status === "online");
  const [accountId, setAccountId] = useState<number | null>(null);
  const [dialogs, setDialogs] = useState<TgDialog[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  useEffect(() => {
    if (!open || !accountId) return;
    setDialogs(null);
    setError(null);
    api<TgDialog[]>(`/accounts/${accountId}/dialogs`)
      .then(setDialogs)
      .catch((e) => setError(e instanceof ApiError ? e.detail : "erro inesperado"));
  }, [open, accountId]);

  async function importOne(d: TgDialog) {
    if (!accountId) return;
    setBusy(d.chat_id);
    try {
      onDone(await api<Channel>("/channels", { json: { account_id: accountId, chat_id: d.chat_id } }));
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "erro inesperado");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Importar grupo">
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">Conta que é admin do grupo</span>
          <select
            value={accountId ?? ""}
            onChange={(e) => setAccountId(Number(e.target.value) || null)}
            className="min-h-11 rounded-md border border-line bg-ink px-3 text-text focus:border-gold focus:outline-none"
          >
            <option value="">Escolha a conta</option>
            {usable.map((a) => (
              <option key={a.id} value={a.id}>
                {accountName(a)}
              </option>
            ))}
          </select>
        </label>
        {usable.length === 0 && <p className="text-sm text-muted">Nenhuma conta online. Conecte uma conta primeiro.</p>}
        <ErrorLine error={error} />
        {accountId && !dialogs && !error && <p className="text-sm text-muted">Buscando grupos onde a conta é admin…</p>}
        {dialogs?.length === 0 && <Empty>Essa conta não é admin de nenhum grupo que ainda não foi importado.</Empty>}
        <ul className="max-h-80 divide-y divide-line overflow-y-auto">
          {dialogs?.map((d) => (
            <li key={d.chat_id} className="flex items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate">{d.title}</p>
                <p className="text-xs text-muted">
                  {KIND[d.kind] ?? d.kind}
                  {d.member_count != null && `, ${d.member_count.toLocaleString("pt-BR")} membros`}
                </p>
              </div>
              <Button variant="primary" busy={busy === d.chat_id} onClick={() => importOne(d)}>
                Importar
              </Button>
            </li>
          ))}
        </ul>
      </div>
    </Dialog>
  );
}
