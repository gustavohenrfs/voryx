"use client";

import { useEffect, useState } from "react";
import { Button, Confirm, Empty, ErrorLine, Field } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import type { ChannelDetail, Member } from "@/lib/types";

const PAGE = 50;

export function MembersTab({ channel }: { channel: ChannelDetail }) {
  const toast = useToast();
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [members, setMembers] = useState<Member[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<{ kind: "kick" | "ban"; member: Member } | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(q.trim());
      setOffset(0);
    }, 400);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let alive = true;
    setMembers(null);
    api<Member[]>(`/channels/${channel.id}/members?q=${encodeURIComponent(query)}&offset=${offset}&limit=${PAGE}`)
      .then((m) => alive && (setMembers(m), setError(null)))
      .catch((e) => alive && setError(e instanceof ApiError ? e.detail : "erro inesperado"));
    return () => {
      alive = false;
    };
  }, [channel.id, query, offset]);

  async function confirm() {
    if (!action) return;
    const { kind, member } = action;
    setAction(null);
    try {
      await api(`/channels/${channel.id}/members/${member.user_id}/${kind}`, { json: { name: member.name } });
      toast(kind === "ban" ? `${member.name} foi banido` : `${member.name} foi removido`);
      setMembers((xs) => xs?.filter((x) => x.user_id !== member.user_id) ?? null);
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro inesperado", "error");
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="max-w-sm">
        <Field label="Buscar membro" placeholder="Nome ou @usuário" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <ErrorLine error={error} />
      {!members && !error && <p className="text-sm text-muted">Carregando membros…</p>}
      {members?.length === 0 && <Empty>Ninguém encontrado.</Empty>}
      <ul className="divide-y divide-line border-y border-line">
        {members?.map((m) => (
          <li key={m.user_id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="truncate">{m.name}</p>
              <p className="text-xs text-muted">{m.username ? `@${m.username}` : `id ${m.user_id}`}</p>
            </div>
            <div className="flex gap-2">
              <Button onClick={() => setAction({ kind: "kick", member: m })}>Remover</Button>
              <Button variant="danger" onClick={() => setAction({ kind: "ban", member: m })}>
                Banir
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <div className="flex gap-2">
        <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
          Anteriores
        </Button>
        <Button disabled={!members || members.length < PAGE} onClick={() => setOffset(offset + PAGE)}>
          Próximos
        </Button>
      </div>

      <Confirm
        open={Boolean(action)}
        title={action?.kind === "ban" ? "Banir membro" : "Remover membro"}
        body={
          action?.kind === "ban"
            ? `${action.member.name} sai de ${channel.title} e não consegue voltar.`
            : `${action?.member.name} sai de ${channel.title}, mas pode pedir para entrar de novo.`
        }
        action={action?.kind === "ban" ? "Banir" : "Remover"}
        danger
        onConfirm={confirm}
        onClose={() => setAction(null)}
      />
    </div>
  );
}
