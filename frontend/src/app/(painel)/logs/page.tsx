"use client";

import { useState } from "react";
import { Button, Empty, ErrorLine, PageHeader } from "@/components/ui";
import { api } from "@/lib/api";
import { toSaoPaulo } from "@/lib/time";
import type { Account, Channel, LogEntry } from "@/lib/types";
import { accountName } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const ACTION: Record<string, string> = {
  approve: "Aprovou",
  reject: "Recusou",
  approve_all: "Aprovou todos",
  kick: "Removeu",
  ban: "Baniu",
  post: "Postou",
};
const PAGE = 100;

export default function LogsPage() {
  const [channel, setChannel] = useState("");
  const base = `/logs?limit=${PAGE}${channel ? `&channel_id=${channel}` : ""}`;
  const { data, error, setData } = useApi<LogEntry[]>(base);
  const accounts = useApi<Account[]>("/accounts");
  const channels = useApi<Channel[]>("/channels");
  const [more, setMore] = useState(true);

  const accById = new Map(accounts.data?.map((a) => [a.id, a]) ?? []);
  const chById = new Map(channels.data?.map((c) => [c.id, c]) ?? []);

  async function loadMore() {
    const last = data?.at(-1);
    if (!last) return;
    const next = await api<LogEntry[]>(`${base}&before_id=${last.id}`);
    setMore(next.length === PAGE);
    setData([...(data ?? []), ...next]);
  }

  return (
    <>
      <PageHeader title="Histórico" />
      <select
        aria-label="Filtrar por grupo"
        value={channel}
        onChange={(e) => {
          setChannel(e.target.value);
          setMore(true);
        }}
        className="mb-6 min-h-10 rounded-md border border-line bg-ink px-3 text-sm text-text focus:border-gold focus:outline-none"
      >
        <option value="">Todos os grupos</option>
        {channels.data?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.title}
          </option>
        ))}
      </select>
      <ErrorLine error={error} />
      {data?.length === 0 && <Empty>Nada por aqui ainda. Aprovações, banimentos e posts aparecem nesta lista.</Empty>}
      <ul className="divide-y divide-line border-y border-line">
        {data?.map((l) => (
          <li key={l.id} className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-3 text-sm">
            <span className="w-24 shrink-0 text-muted tabular-nums">{toSaoPaulo(l.created_at)}</span>
            <span className="min-w-0 flex-1">
              <span className={l.result === "error" ? "text-[#ff9c92]" : ""}>{ACTION[l.action] ?? l.action}</span>{" "}
              {l.target}
              <span className="text-muted">
                {l.channel_id && chById.get(l.channel_id) ? ` em ${chById.get(l.channel_id)!.title}` : ""}
                {l.account_id && accById.get(l.account_id) ? `, pela conta ${accountName(accById.get(l.account_id)!)}` : ""}
              </span>
              {l.result === "error" && l.detail && <span className="block text-xs text-[#ff9c92]">Falhou: {l.detail}</span>}
            </span>
          </li>
        ))}
      </ul>
      {data && data.length >= PAGE && more && (
        <Button className="mt-4" onClick={loadMore}>
          Carregar mais
        </Button>
      )}
    </>
  );
}
