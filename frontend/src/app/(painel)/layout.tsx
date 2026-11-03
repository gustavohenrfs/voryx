"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { MeCtx } from "@/lib/me";
import type { User } from "@/lib/types";

const NAV = [
  { href: "/", label: "Visão geral", icon: "◎" },
  { href: "/agenda", label: "Agenda", icon: "◷" },
  { href: "/grupos", label: "Grupos", icon: "◫" },
  { href: "/contas", label: "Contas", icon: "◉" },
  { href: "/logs", label: "Histórico", icon: "≡" },
];

export default function PainelLayout({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<User | null>(null);
  const router = useRouter();
  const path = usePathname();

  useEffect(() => {
    api<User>("/auth/me")
      .then(setMe)
      .catch(() => router.replace("/login"));
  }, [router]);

  if (!me) return <div className="grid min-h-dvh place-items-center text-sm text-muted">Carregando…</div>;

  const items = me.role === "admin" ? [...NAV, { href: "/admin", label: "Usuários", icon: "⚙" }] : NAV;
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href));

  async function logout() {
    await api("/auth/logout", { method: "POST" }).catch(() => null);
    router.replace("/login");
  }

  return (
    <MeCtx.Provider value={me}>
      <div className="md:flex">
        <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-line px-4 py-6 md:flex">
          <Link href="/" className="px-3 font-display text-3xl text-gold">
            Voryx
          </Link>
          <nav className="mt-10 flex flex-col gap-1" aria-label="Principal">
            {items.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                aria-current={active(n.href) ? "page" : undefined}
                className={`rounded-md px-3 py-2 text-sm transition-colors ${
                  active(n.href) ? "bg-raised text-gold-soft" : "text-muted hover:text-text"
                }`}
              >
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="mt-auto border-t border-line px-3 pt-4 text-sm">
            <p className="truncate text-text">{me.name}</p>
            <button onClick={logout} className="mt-1 text-xs text-muted hover:text-gold-soft">
              Sair
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-4 pt-6 pb-28 md:px-10 md:pt-10 md:pb-12">
          <div className="mb-6 flex items-center justify-between md:hidden">
            <span className="font-display text-2xl text-gold">Voryx</span>
            <button onClick={logout} className="text-xs text-muted">
              Sair
            </button>
          </div>
          <div className="mx-auto max-w-5xl">{children}</div>
        </main>

        <nav
          aria-label="Principal"
          className="fixed inset-x-0 bottom-0 z-40 grid border-t border-line bg-surface/95 backdrop-blur md:hidden"
          style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}
        >
          {items.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              aria-current={active(n.href) ? "page" : undefined}
              className={`flex flex-col items-center gap-0.5 py-2.5 text-[11px] ${
                active(n.href) ? "text-gold" : "text-muted"
              }`}
            >
              <span aria-hidden className="text-base leading-none">
                {n.icon}
              </span>
              {n.label.split(" ")[0]}
            </Link>
          ))}
        </nav>
      </div>
    </MeCtx.Provider>
  );
}
