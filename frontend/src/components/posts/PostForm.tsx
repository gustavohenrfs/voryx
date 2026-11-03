"use client";

import { useState } from "react";
import { Button, ErrorLine, Field } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError, upload } from "@/lib/api";
import { fromSaoPauloInput, toInputs } from "@/lib/time";
import type { Account, Channel, Post } from "@/lib/types";
import { accountName } from "@/lib/types";

const MAX_TEXT = 4096;
const MAX_CAPTION = 1024;
const MAX_MEDIA = 10;

type Item = { key: string; name: string; id?: number; mime: string; progress: number; preview?: string; error?: string };

function defaultWhen() {
  const d = new Date(Date.now() + 60 * 60 * 1000);
  d.setMinutes(0, 0, 0);
  return toInputs(d.toISOString());
}

export function PostForm({
  accounts,
  channels,
  post,
  onSaved,
}: {
  accounts: Account[];
  channels: Channel[];
  post?: Post;
  onSaved: (p: Post) => void;
}) {
  const toast = useToast();
  const live = accounts.filter((a) => a.status !== "dead");
  const [accountId, setAccountId] = useState<number>(post?.account_id ?? live[0]?.id ?? 0);
  const [channelId, setChannelId] = useState<number>(post?.channel_id ?? channels[0]?.id ?? 0);
  const [text, setText] = useState(post?.text ?? "");
  const [items, setItems] = useState<Item[]>(
    post?.media.map((m, i) => ({ key: `m${m.id}`, name: `Mídia ${i + 1}`, id: m.id, mime: m.mime, progress: 100 })) ?? [],
  );
  const initial = post ? toInputs(post.run_at) : defaultWhen();
  const [date, setDate] = useState(initial.date);
  const [time, setTime] = useState(initial.time);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"schedule" | "now" | null>(null);

  const limit = items.length ? MAX_CAPTION : MAX_TEXT;
  const tooLong = text.length > limit;
  const uploading = items.some((i) => !i.id && !i.error);
  const empty = !text.trim() && items.length === 0;
  const blocked = tooLong || uploading || empty || !accountId || !channelId || items.some((i) => i.error);

  function addFiles(files: FileList | null) {
    if (!files) return;
    const room = MAX_MEDIA - items.length;
    const list = Array.from(files).slice(0, room);
    if (files.length > room) toast(`No máximo ${MAX_MEDIA} mídias por post`, "error");
    for (const f of list) {
      const key = `${f.name}-${f.size}-${Math.random()}`;
      const preview = f.type.startsWith("image/") && typeof URL.createObjectURL === "function" ? URL.createObjectURL(f) : undefined;
      setItems((xs) => [...xs, { key, name: f.name, mime: f.type, progress: 0, preview }]);
      upload(f, (p) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, progress: p } : x))))
        .then((m) => setItems((xs) => xs.map((x) => (x.key === key ? { ...x, id: m.id, progress: 100 } : x))))
        .catch((e) =>
          setItems((xs) => xs.map((x) => (x.key === key ? { ...x, error: e instanceof ApiError ? e.detail : "falhou" } : x))),
        );
    }
  }

  function move(i: number, d: -1 | 1) {
    setItems((xs) => {
      const ys = [...xs];
      const j = i + d;
      if (j < 0 || j >= ys.length) return xs;
      [ys[i], ys[j]] = [ys[j], ys[i]];
      return ys;
    });
  }

  async function submit(now: boolean) {
    setBusy(now ? "now" : "schedule");
    setError(null);
    const media_ids = items.map((i) => i.id!).filter(Boolean);
    const run_at = now ? null : fromSaoPauloInput(date, time);
    try {
      const saved = post
        ? await api<Post>(`/posts/${post.id}`, { method: "PATCH", json: { text, media_ids, run_at, post_now: now } })
        : await api<Post>("/posts", {
            json: { account_id: accountId, channel_id: channelId, text, media_ids, run_at, post_now: now },
          });
      toast(now ? "Post enviado para a fila agora" : post ? "Post atualizado" : "Post agendado");
      onSaved(saved);
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "erro inesperado");
    } finally {
      setBusy(null);
    }
  }

  const select = "min-h-11 rounded-md border border-line bg-ink px-3 text-text focus:border-gold focus:outline-none";

  return (
    <form
      className="flex flex-col gap-5"
      onSubmit={(e) => {
        e.preventDefault();
        void submit(false);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">Conta que posta</span>
          <select className={select} value={accountId} disabled={Boolean(post)} onChange={(e) => setAccountId(Number(e.target.value))}>
            {live.map((a) => (
              <option key={a.id} value={a.id}>
                {accountName(a)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">Grupo</span>
          <select className={select} value={channelId} disabled={Boolean(post)} onChange={(e) => setChannelId(Number(e.target.value))}>
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.title}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="flex justify-between text-muted">
          <span>Texto</span>
          <span className={tooLong ? "text-[#ff9c92]" : "tabular-nums"}>
            {text.length} / {limit}
          </span>
        </span>
        <textarea
          aria-label="Texto"
          rows={5}
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="rounded-md border border-line bg-ink p-3 text-text focus:border-gold focus:outline-none"
        />
        {items.length > 0 && <span className="text-xs text-muted">Com mídia, o Telegram aceita até 1024 caracteres de legenda.</span>}
      </label>

      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1.5">
          <span className="text-muted">Fotos e vídeos</span>
          <input
            type="file"
            accept="image/*,video/*"
            multiple
            disabled={items.length >= MAX_MEDIA}
            onChange={(e) => {
              addFiles(e.target.files);
              e.target.value = "";
            }}
            className="text-sm text-muted file:mr-3 file:rounded-md file:border file:border-line file:bg-raised file:px-3 file:py-2 file:text-text"
          />
        </label>
        {items.length > 0 && (
          <ol className="divide-y divide-line rounded-md border border-line">
            {items.map((it, i) => (
              <li key={it.key} className="flex items-center gap-3 p-2">
                {it.preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={it.preview} alt="" className="size-10 rounded object-cover" />
                ) : (
                  <span className="grid size-10 place-items-center rounded bg-raised text-xs text-muted">
                    {it.mime.startsWith("video") ? "vídeo" : "foto"}
                  </span>
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate">{it.name}</span>
                  <span className={`block text-xs ${it.error ? "text-[#ff9c92]" : "text-muted"}`}>
                    {it.error ?? (it.id ? "Pronto" : `Enviando ${it.progress}%`)}
                  </span>
                </span>
                <button type="button" aria-label={`Subir ${it.name}`} onClick={() => move(i, -1)} className="px-1 text-muted hover:text-text">
                  ↑
                </button>
                <button type="button" aria-label={`Descer ${it.name}`} onClick={() => move(i, 1)} className="px-1 text-muted hover:text-text">
                  ↓
                </button>
                <button
                  type="button"
                  aria-label={`Tirar ${it.name}`}
                  onClick={() => setItems((xs) => xs.filter((x) => x.key !== it.key))}
                  className="px-1 text-muted hover:text-[#ff9c92]"
                >
                  ✕
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 sm:max-w-sm">
        <Field label="Dia" type="date" value={date} onChange={(e) => setDate(e.target.value)} required />
        <Field label="Hora" type="time" value={time} onChange={(e) => setTime(e.target.value)} required />
      </div>
      <p className="-mt-3 text-xs text-muted">Horário de Brasília.</p>

      <ErrorLine error={error} />
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" type="submit" disabled={blocked} busy={busy === "schedule"}>
          {post ? "Salvar" : "Agendar"}
        </Button>
        <Button type="button" disabled={blocked} busy={busy === "now"} onClick={() => submit(true)}>
          Postar agora
        </Button>
      </div>
    </form>
  );
}
