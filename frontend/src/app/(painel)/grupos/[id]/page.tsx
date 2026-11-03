"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { MembersTab } from "@/components/channels/MembersTab";
import { RequestsTab } from "@/components/channels/RequestsTab";
import { SummaryTab } from "@/components/channels/SummaryTab";
import { Button, Confirm, ErrorLine, StatusBadge } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import type { Account, ChannelDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const TABS = [
  ["resumo", "Resumo"],
  ["solicitacoes", "Solicitações"],
  ["membros", "Membros"],
] as const;

export default function GrupoPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data: channel, error, setData } = useApi<ChannelDetail>(`/channels/${id}`);
  const accounts = useApi<Account[]>("/accounts");
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("resumo");
  const [removing, setRemoving] = useState(false);

  async function remove() {
    try {
      await api(`/channels/${id}`, { method: "DELETE" });
      toast("Grupo removido do painel");
      router.replace("/grupos");
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro inesperado", "error");
    }
  }

  if (error) return <ErrorLine error={error} />;
  if (!channel) return <p className="text-sm text-muted">Carregando…</p>;

  return (
    <>
      <Link href="/grupos" className="text-sm text-muted hover:text-gold-soft">
        Grupos
      </Link>
      <div className="mt-2 mb-6 flex flex-wrap items-end gap-3">
        <h1 className="mr-auto font-display text-3xl tracking-tight md:text-4xl">{channel.title}</h1>
        <StatusBadge status={channel.status} />
      </div>

      {channel.status !== "ok" && (
        <p role="alert" className="mb-6 rounded-lg border border-danger/50 bg-[#2a1614] px-4 py-3 text-sm text-[#ffd9d4]">
          {channel.status === "conta_caida"
            ? "A conta gestora deste grupo caiu. Troque a conta gestora no Resumo ou reconecte a conta."
            : "A conta gestora perdeu acesso de admin a este grupo."}
        </p>
      )}

      <div role="tablist" aria-label="Seções do grupo" className="mb-8 flex gap-6 border-b border-line">
        {TABS.map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`-mb-px border-b-2 pb-3 text-sm ${
              tab === key ? "border-gold text-gold-soft" : "border-transparent text-muted hover:text-text"
            }`}
          >
            {label}
            {key === "solicitacoes" && channel.pending_count > 0 && ` (${channel.pending_count})`}
          </button>
        ))}
      </div>

      {tab === "resumo" && <SummaryTab channel={channel} accounts={accounts.data ?? []} onChange={setData} />}
      {tab === "solicitacoes" && <RequestsTab channel={channel} onChannelChange={setData} />}
      {tab === "membros" && <MembersTab channel={channel} />}

      {tab === "resumo" && (
        <div className="mt-16 border-t border-line pt-6">
          <Button variant="danger" onClick={() => setRemoving(true)}>
            Remover grupo do painel
          </Button>
        </div>
      )}

      <Confirm
        open={removing}
        title="Remover grupo do painel"
        body="O grupo continua existindo no Telegram. Os posts agendados para ele são cancelados."
        action="Remover"
        danger
        onConfirm={remove}
        onClose={() => setRemoving(false)}
      />
    </>
  );
}
