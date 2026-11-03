"use client";

import { forwardRef, useEffect, useRef } from "react";
import type { AccountStatus, ChannelStatus, PostStatus } from "@/lib/types";

type BtnProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  busy?: boolean;
};

export function Button({ variant = "ghost", busy, className = "", children, disabled, ...rest }: BtnProps) {
  const styles = {
    primary: "bg-gold text-ink hover:bg-gold-soft font-semibold",
    ghost: "border border-line text-text hover:border-gold/60 hover:text-gold-soft",
    danger: "border border-danger/50 text-[#ffb4ab] hover:bg-danger/10",
  }[variant];
  return (
    <button
      {...rest}
      disabled={disabled || busy}
      className={`inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-4 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${styles} ${className}`}
    >
      {busy ? "Aguarde…" : children}
    </button>
  );
}

type FieldProps = React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: string };

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field({ label, hint, id, ...rest }, ref) {
  const fid = id ?? `f-${label.replace(/\W+/g, "-").toLowerCase()}`;
  return (
    <label htmlFor={fid} className="flex flex-col gap-1.5 text-sm">
      <span className="text-muted">{label}</span>
      <input
        ref={ref}
        id={fid}
        {...rest}
        className="min-h-11 rounded-md border border-line bg-ink px-3 text-text placeholder:text-muted/60 focus:border-gold focus:outline-none"
      />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
});

const STATUS: Record<string, { label: string; dot: string; text: string }> = {
  online: { label: "Online", dot: "bg-ok", text: "text-ok" },
  offline: { label: "Offline", dot: "bg-muted", text: "text-muted" },
  connecting: { label: "Conectando", dot: "bg-gold", text: "text-gold-soft" },
  dead: { label: "Caiu", dot: "bg-danger", text: "text-[#ff9c92]" },
  ok: { label: "Ativo", dot: "bg-ok", text: "text-ok" },
  sem_acesso: { label: "Sem acesso", dot: "bg-danger", text: "text-[#ff9c92]" },
  conta_caida: { label: "Conta gestora caiu", dot: "bg-danger", text: "text-[#ff9c92]" },
  scheduled: { label: "Agendado", dot: "bg-gold", text: "text-gold-soft" },
  sending: { label: "Enviando", dot: "bg-gold", text: "text-gold-soft" },
  sent: { label: "Enviado", dot: "bg-ok", text: "text-ok" },
  failed: { label: "Falhou", dot: "bg-danger", text: "text-[#ff9c92]" },
  canceled: { label: "Cancelado", dot: "bg-muted", text: "text-muted" },
};

export function StatusBadge({ status }: { status: AccountStatus | ChannelStatus | PostStatus }) {
  const s = STATUS[status] ?? STATUS.offline;
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium ${s.text}`}>
      <span aria-hidden className={`size-2 rounded-full ${s.dot}`} />
      {s.label}
    </span>
  );
}

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal?.();
    if (!open && d.open) d.close?.();
  }, [open]);
  if (!open) return null;
  return (
    <dialog
      ref={ref}
      open
      onClose={onClose}
      onCancel={onClose}
      aria-label={title}
      className="m-auto w-[min(32rem,calc(100vw-2rem))] rounded-xl border border-line bg-surface p-0 text-text"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <h2 className="font-display text-lg">{title}</h2>
        <button onClick={onClose} aria-label="Fechar" className="text-muted hover:text-text">
          ✕
        </button>
      </div>
      <div className="p-5">{children}</div>
    </dialog>
  );
}

export function Confirm({
  open,
  title,
  body,
  action,
  danger,
  onConfirm,
  onClose,
}: {
  open: boolean;
  title: string;
  body: React.ReactNode;
  action: string;
  danger?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="text-sm text-muted">{body}</div>
      <div className="mt-6 flex justify-end gap-2">
        <Button onClick={onClose}>Voltar</Button>
        <Button variant={danger ? "danger" : "primary"} onClick={onConfirm}>
          {action}
        </Button>
      </div>
    </Dialog>
  );
}

export function PageHeader({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <h1 className="font-display text-3xl tracking-tight md:text-4xl">{title}</h1>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-dashed border-line px-5 py-8 text-center text-sm text-muted">{children}</div>;
}

export function ErrorLine({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="text-sm text-[#ff9c92]">
      {error}
    </p>
  );
}
