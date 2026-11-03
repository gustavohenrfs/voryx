"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { toSaoPaulo } from "@/lib/time";
import type { Account, ChannelDetail } from "@/lib/types";
import { accountName } from "@/lib/types";

const RIGHTS: Record<string, string> = {
  creator: "Dono",
  change_info: "Editar info",
  post_messages: "Postar",
  edit_messages: "Editar posts",
  delete_messages: "Apagar mensagens",
  ban_users: "Banir",
  invite_users: "Convidar e aprovar",
  pin_messages: "Fixar",
  add_admins: "Adicionar admins",
  manage_call: "Lives",
  anonymous: "Anônimo",
  other: "Outros",
};

export function SummaryTab({
  channel,
  accounts,
  onChange,
}: {
  channel: ChannelDetail;
  accounts: Account[];
  onChange: (c: ChannelDetail) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<ChannelDetail>, ok: string) {
    setBusy(true);
    try {
      onChange(await fn());
      toast(ok);
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro inesperado", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-10">
      <dl className="grid grid-cols-2 gap-6 sm:grid-cols-3">
        <div>
          <dt className="text-sm text-muted">Membros</dt>
          <dd className="mt-1 font-display text-4xl tabular-nums">{channel.member_count?.toLocaleString("pt-BR") ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-sm text-muted">Pedidos pendentes</dt>
          <dd className="mt-1 font-display text-4xl tabular-nums">{channel.pending_count}</dd>
        </div>
        <div className="col-span-2 sm:col-span-1">
          <dt className="text-sm text-muted">Atualizado</dt>
          <dd className="mt-2 text-sm">{channel.last_synced_at ? toSaoPaulo(channel.last_synced_at) : "nunca"}</dd>
          <Button
            className="mt-2"
            busy={busy}
            onClick={() => run(() => api(`/channels/${channel.id}/refresh`, { method: "POST" }), "Dados atualizados")}
          >
            Atualizar agora
          </Button>
        </div>
      </dl>

      <label className="flex max-w-sm flex-col gap-1.5 text-sm">
        <span className="text-muted">Conta gestora (aprova pedidos e bane membros)</span>
        <select
          value={channel.manager_account_id ?? ""}
          disabled={busy}
          onChange={(e) =>
            run(
              () => api(`/channels/${channel.id}`, { method: "PATCH", json: { manager_account_id: Number(e.target.value) } }),
              "Conta gestora trocada",
            )
          }
          className="min-h-11 rounded-md border border-line bg-ink px-3 text-text focus:border-gold focus:outline-none"
        >
          {accounts.map((a) => (
            <option key={a.id} value={a.id} disabled={a.status === "dead"}>
              {accountName(a)}
              {a.status === "dead" ? " (caiu)" : ""}
            </option>
          ))}
        </select>
      </label>

      <div>
        <h3 className="mb-3 font-display text-xl">Admins</h3>
        <ul className="divide-y divide-line border-y border-line">
          {channel.admins.map((a) => (
            <li key={a.tg_user_id} className="py-3">
              <p>{a.name}</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Object.entries(a.rights)
                  .filter(([, v]) => v)
                  .map(([k]) => (
                    <span key={k} className="rounded-full border border-line px-2 py-0.5 text-xs text-muted">
                      {RIGHTS[k] ?? k}
                    </span>
                  ))}
              </div>
            </li>
          ))}
          {channel.admins.length === 0 && <li className="py-3 text-sm text-muted">Sem dados de admins ainda.</li>}
        </ul>
      </div>
    </div>
  );
}
