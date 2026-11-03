"use client";

import { useState } from "react";
import { Button, Confirm, Empty, ErrorLine } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { toSaoPaulo } from "@/lib/time";
import type { ChannelDetail, JoinRequest } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export function RequestsTab({
  channel,
  onChannelChange,
}: {
  channel: ChannelDetail;
  onChannelChange: (c: ChannelDetail) => void;
}) {
  const path = `/channels/${channel.id}/requests?status=pending`;
  const { data, error, reload, setData } = useApi<JoinRequest[]>(path);
  const toast = useToast();
  const [mode, setMode] = useState(channel.join_mode);
  const [confirmAll, setConfirmAll] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const fail = (e: unknown) => toast(e instanceof ApiError ? e.detail : "erro inesperado", "error");

  async function changeMode(next: "auto" | "manual") {
    if (next === mode) return;
    const prev = mode;
    setMode(next);
    try {
      const c = await api<ChannelDetail>(`/channels/${channel.id}`, { method: "PATCH", json: { join_mode: next } });
      onChannelChange(c);
      toast(next === "auto" ? "Aprovação automática ligada" : "Aprovação manual ligada");
      void reload();
    } catch (e) {
      setMode(prev);
      fail(e);
    }
  }

  async function decide(r: JoinRequest, approve: boolean) {
    setBusy(`${r.id}`);
    try {
      await api(`/channels/${channel.id}/requests/${r.id}/${approve ? "approve" : "reject"}`, { method: "POST" });
      setData((xs) => xs?.map((x) => (x.id === r.id ? { ...x, queued: true } : x)) ?? null);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }

  async function approveAll() {
    setConfirmAll(false);
    try {
      await api(`/channels/${channel.id}/requests/approve-all`, { method: "POST" });
      toast("Aprovação de todos enviada. Em alguns segundos a lista se atualiza.");
      setData((xs) => xs?.map((x) => ({ ...x, queued: true })) ?? null);
    } catch (e) {
      fail(e);
    }
  }

  async function refresh() {
    setBusy("refresh");
    try {
      setData(await api<JoinRequest[]>(`/channels/${channel.id}/requests/refresh`, { method: "POST" }));
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }

  const waiting = data?.filter((r) => !r.queued) ?? [];

  return (
    <div className="flex flex-col gap-8">
      <fieldset>
        <legend className="mb-3 text-sm text-muted">Como aprovar quem pede para entrar</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {(
            [
              ["auto", "Automático", "Aprova todo mundo, um a cada poucos segundos para não estourar o limite do Telegram."],
              ["manual", "Manual", "Os pedidos ficam aqui e você decide quem entra."],
            ] as const
          ).map(([value, title, desc]) => (
            <label
              key={value}
              className={`flex cursor-pointer gap-3 rounded-lg border p-4 ${
                mode === value ? "border-gold bg-gold/5" : "border-line hover:border-gold/40"
              }`}
            >
              <input
                type="radio"
                name="join_mode"
                value={value}
                checked={mode === value}
                onChange={() => changeMode(value)}
                className="mt-1 accent-[#c9a54c]"
                aria-label={title}
              />
              <span>
                <span className="block font-medium">{title}</span>
                <span className="mt-1 block text-sm text-muted">{desc}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="mr-auto font-display text-xl">Pedidos pendentes</h3>
          <Button busy={busy === "refresh"} onClick={refresh}>
            Buscar novos
          </Button>
          {waiting.length > 0 && (
            <Button variant="primary" onClick={() => setConfirmAll(true)}>
              Aprovar todos ({waiting.length})
            </Button>
          )}
        </div>
        <ErrorLine error={error} />
        {data?.length === 0 && <Empty>Nenhum pedido pendente.</Empty>}
        <ul className="divide-y divide-line border-y border-line">
          {data?.map((r) => (
            <li key={r.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate">{r.name}</p>
                <p className="text-xs text-muted">
                  {r.username ? `@${r.username}, ` : ""}pediu em {toSaoPaulo(r.requested_at)}
                </p>
              </div>
              {r.queued ? (
                <span className="text-xs text-gold-soft">Na fila</span>
              ) : (
                <div className="flex gap-2">
                  <Button variant="primary" busy={busy === `${r.id}`} onClick={() => decide(r, true)} aria-label={`Aprovar ${r.name}`}>
                    Aprovar
                  </Button>
                  <Button onClick={() => decide(r, false)} aria-label={`Recusar ${r.name}`}>
                    Recusar
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      </div>

      <Confirm
        open={confirmAll}
        title="Aprovar todos"
        body={`Todos os ${waiting.length} pedidos pendentes de ${channel.title} vão ser aprovados de uma vez.`}
        action={`Aprovar ${waiting.length} pedidos`}
        onConfirm={approveAll}
        onClose={() => setConfirmAll(false)}
      />
    </div>
  );
}
