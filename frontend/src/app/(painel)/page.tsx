"use client";

import Link from "next/link";
import { useMemo } from "react";
import { AccountRing } from "@/components/accounts/AccountRing";
import { Empty, ErrorLine, StatusBadge } from "@/components/ui";
import { toSaoPaulo } from "@/lib/time";
import type { Account, Channel, Post } from "@/lib/types";
import { accountName } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Overview() {
  const accounts = useApi<Account[]>("/accounts");
  const channels = useApi<Channel[]>("/channels");
  const from = useMemo(() => new Date().toISOString(), []);
  const posts = useApi<Post[]>(`/posts?status=scheduled&from=${encodeURIComponent(from)}`);

  const byId = new Map(accounts.data?.map((a) => [a.id, a]) ?? []);
  const chById = new Map(channels.data?.map((c) => [c.id, c]) ?? []);
  const dead = accounts.data?.filter((a) => a.status === "dead") ?? [];
  const next = posts.data?.slice(0, 5) ?? [];

  return (
    <div className="flex flex-col gap-12">
      {dead.map((a) => (
        <div key={a.id} role="alert" className="flex flex-wrap items-center gap-3 rounded-lg border border-danger/50 bg-[#2a1614] px-4 py-3 text-sm">
          <span className="font-medium text-[#ffd9d4]">{accountName(a)} caiu.</span>
          <span className="text-[#ffb4ab]">Posts e aprovações dela estão parados.</span>
          <Link href="/contas" className="ml-auto text-gold-soft underline underline-offset-4">
            Reconectar
          </Link>
        </div>
      ))}

      <section aria-labelledby="modelos">
        <h1 id="modelos" className="font-display text-4xl tracking-tight">
          Suas modelos
        </h1>
        <ErrorLine error={accounts.error} />
        {accounts.data?.length === 0 ? (
          <div className="mt-6">
            <Empty>
              Nenhuma conta ainda. <Link href="/contas" className="text-gold-soft underline">Conecte a primeira</Link>.
            </Empty>
          </div>
        ) : (
          <ul className="mt-8 flex flex-wrap gap-x-8 gap-y-6">
            {accounts.data?.map((a) => (
              <li key={a.id} className="flex w-20 flex-col items-center gap-3 text-center">
                <AccountRing account={a} />
                <span className="w-full truncate text-xs text-muted">{accountName(a)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="grupos" className="grid gap-12 lg:grid-cols-2">
        <div>
          <div className="flex items-baseline justify-between">
            <h2 id="grupos" className="font-display text-2xl">
              Grupos
            </h2>
            <Link href="/grupos" className="text-sm text-muted hover:text-gold-soft">
              Ver todos
            </Link>
          </div>
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {channels.data?.map((c) => (
              <li key={c.id}>
                <Link href={`/grupos/${c.id}`} className="flex items-center gap-3 py-3 hover:text-gold-soft">
                  <span className="min-w-0 flex-1 truncate">{c.title}</span>
                  {c.pending_count > 0 && (
                    <span className="rounded-full bg-gold/15 px-2 py-0.5 text-xs text-gold-soft">
                      {c.pending_count} {c.pending_count === 1 ? "pedido" : "pedidos"}
                    </span>
                  )}
                  <span className="w-24 text-right text-sm text-muted tabular-nums">
                    {c.member_count?.toLocaleString("pt-BR") ?? "—"} membros
                  </span>
                </Link>
              </li>
            ))}
            {channels.data?.length === 0 && <li className="py-3 text-sm text-muted">Nenhum grupo importado.</li>}
          </ul>
        </div>

        <div>
          <div className="flex items-baseline justify-between">
            <h2 className="font-display text-2xl">Próximos posts</h2>
            <Link href="/agenda" className="text-sm text-muted hover:text-gold-soft">
              Abrir agenda
            </Link>
          </div>
          <ul className="mt-4 divide-y divide-line border-y border-line">
            {next.map((p) => {
              const acc = p.account_id ? byId.get(p.account_id) : undefined;
              return (
                <li key={p.id} className="flex items-center gap-3 py-3">
                  <span className="w-24 shrink-0 text-sm text-gold-soft tabular-nums">{toSaoPaulo(p.run_at)}</span>
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {acc ? accountName(acc) : "—"}
                    <span className="text-muted"> em {p.channel_id ? chById.get(p.channel_id)?.title : "—"}</span>
                  </span>
                  <StatusBadge status={p.status} />
                </li>
              );
            })}
            {posts.data && next.length === 0 && <li className="py-3 text-sm text-muted">Nada agendado.</li>}
          </ul>
        </div>
      </section>
    </div>
  );
}
