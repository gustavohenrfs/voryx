import type { Account } from "@/lib/types";
import { accountName } from "@/lib/types";

const RING: Record<Account["status"], string> = {
  online: "ring-ok",
  offline: "ring-muted/60",
  connecting: "ring-gold",
  dead: "ring-danger",
};

const STATUS_TEXT: Record<Account["status"], string> = {
  online: "online",
  offline: "offline",
  connecting: "conectando",
  dead: "caiu",
};

export function initials(name: string) {
  const parts = name.replace(/[^\p{L}\p{N} ]/gu, "").trim().split(/\s+/);
  return ((parts[0]?.[0] ?? "?") + (parts[1]?.[0] ?? "")).toUpperCase();
}

/** O elemento marcante do painel: cada conta é um anel cuja cor é o status. */
export function AccountRing({ account, size = "lg" }: { account: Account; size?: "lg" | "sm" }) {
  const name = accountName(account);
  const dim = size === "lg" ? "size-16 text-lg ring-[3px]" : "size-9 text-xs ring-2";
  return (
    <span
      title={`${name}: ${STATUS_TEXT[account.status]}`}
      className={`inline-grid shrink-0 place-items-center rounded-full bg-raised font-display text-gold-soft ring-offset-4 ring-offset-ink ${dim} ${RING[account.status]} ${
        account.status === "dead" ? "opacity-70 grayscale" : ""
      }`}
    >
      {initials(name)}
    </span>
  );
}
