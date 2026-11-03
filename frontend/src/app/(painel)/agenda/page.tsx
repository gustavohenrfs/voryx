"use client";

import { useMemo, useState } from "react";
import { PostForm } from "@/components/posts/PostForm";
import { Button, Confirm, Dialog, Empty, ErrorLine, PageHeader, StatusBadge } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { dayKey, dayLabel, timeOf } from "@/lib/time";
import type { Account, Channel, Post } from "@/lib/types";
import { accountName } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const DAYS_AHEAD = 14;

export default function AgendaPage() {
  const toast = useToast();
  const [accountFilter, setAccountFilter] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const range = useMemo(() => {
    const from = new Date(Date.now() - 24 * 3600 * 1000).toISOString();
    const to = new Date(Date.now() + DAYS_AHEAD * 24 * 3600 * 1000).toISOString();
    return `from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
  }, []);
  const qs = `${range}${accountFilter ? `&account_id=${accountFilter}` : ""}${channelFilter ? `&channel_id=${channelFilter}` : ""}`;
  const posts = useApi<Post[]>(`/posts?${qs}`);
  const accounts = useApi<Account[]>("/accounts");
  const channels = useApi<Channel[]>("/channels");
  const [editing, setEditing] = useState<Post | "new" | null>(null);
  const [canceling, setCanceling] = useState<Post | null>(null);

  const accById = new Map(accounts.data?.map((a) => [a.id, a]) ?? []);
  const chById = new Map(channels.data?.map((c) => [c.id, c]) ?? []);
  const today = dayKey(new Date().toISOString());

  const groups = useMemo(() => {
    const m = new Map<string, Post[]>();
    for (const p of posts.data ?? []) {
      const k = dayKey(p.run_at);
      m.set(k, [...(m.get(k) ?? []), p]);
    }
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [posts.data]);

  async function cancel() {
    if (!canceling) return;
    try {
      await api(`/posts/${canceling.id}`, { method: "DELETE" });
      toast("Post cancelado");
      void posts.reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro inesperado", "error");
    } finally {
      setCanceling(null);
    }
  }

  const select = "min-h-10 rounded-md border border-line bg-ink px-3 text-sm text-text focus:border-gold focus:outline-none";
  const ready = accounts.data && channels.data;

  return (
    <>
      <PageHeader title="Agenda">
        <Button variant="primary" disabled={!ready || !channels.data?.length} onClick={() => setEditing("new")}>
          Novo post
        </Button>
      </PageHeader>

      <div className="mb-8 flex flex-wrap gap-2">
        <select aria-label="Filtrar por conta" className={select} value={accountFilter} onChange={(e) => setAccountFilter(e.target.value)}>
          <option value="">Todas as contas</option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {accountName(a)}
            </option>
          ))}
        </select>
        <select aria-label="Filtrar por grupo" className={select} value={channelFilter} onChange={(e) => setChannelFilter(e.target.value)}>
          <option value="">Todos os grupos</option>
          {channels.data?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </div>

      <ErrorLine error={posts.error} />
      {posts.data?.length === 0 && (
        <Empty>Nada na agenda para os próximos {DAYS_AHEAD} dias. Crie um post para uma das modelos.</Empty>
      )}

      <div className="flex flex-col gap-10">
        {groups.map(([day, list]) => (
          <section key={day} aria-label={dayLabel(day, today)}>
            <h2 className="mb-3 font-display text-xl capitalize">{dayLabel(day, today)}</h2>
            <ul className="divide-y divide-line border-y border-line">
              {list.map((p) => {
                const acc = p.account_id ? accById.get(p.account_id) : undefined;
                return (
                  <li key={p.id} className="flex flex-wrap items-start gap-x-4 gap-y-2 py-4">
                    <span className="w-14 shrink-0 font-display text-lg text-gold-soft tabular-nums">{timeOf(p.run_at)}</span>
                    <div className="min-w-0 flex-1 basis-56">
                      <p className="text-sm">
                        {acc ? accountName(acc) : "Conta removida"}
                        <span className="text-muted"> em {p.channel_id ? chById.get(p.channel_id)?.title : "grupo removido"}</span>
                      </p>
                      <p className="mt-1 line-clamp-2 text-sm text-muted">
                        {p.media.length > 0 && `${p.media.length} mídia${p.media.length > 1 ? "s" : ""}. `}
                        {p.text}
                      </p>
                      {p.error && p.status !== "sent" && <p className="mt-1 text-xs text-[#ff9c92]">{p.error}</p>}
                    </div>
                    <StatusBadge status={p.status} />
                    {p.status === "scheduled" && (
                      <div className="flex gap-2">
                        <Button onClick={() => setEditing(p)}>Editar</Button>
                        <Button variant="danger" onClick={() => setCanceling(p)}>
                          Cancelar
                        </Button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        ))}
      </div>

      <Dialog open={editing !== null} onClose={() => setEditing(null)} title={editing === "new" ? "Novo post" : "Editar post"}>
        {editing && ready && (
          <PostForm
            accounts={accounts.data!}
            channels={channels.data!}
            post={editing === "new" ? undefined : editing}
            onSaved={() => {
              setEditing(null);
              void posts.reload();
            }}
          />
        )}
      </Dialog>

      <Confirm
        open={Boolean(canceling)}
        title="Cancelar post"
        body="O post não vai ser publicado. Dá para criar outro depois."
        action="Cancelar post"
        danger
        onConfirm={cancel}
        onClose={() => setCanceling(null)}
      />
    </>
  );
}
