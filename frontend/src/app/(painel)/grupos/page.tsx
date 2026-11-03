"use client";

import Link from "next/link";
import { useState } from "react";
import { ImportChannelDialog } from "@/components/channels/ImportChannelDialog";
import { Button, Empty, ErrorLine, PageHeader, StatusBadge } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import type { Account, Channel } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function GruposPage() {
  const { data, error, reload } = useApi<Channel[]>("/channels");
  const accounts = useApi<Account[]>("/accounts");
  const [importing, setImporting] = useState(false);
  const toast = useToast();

  return (
    <>
      <PageHeader title="Grupos">
        <Button variant="primary" onClick={() => setImporting(true)}>
          Importar grupo
        </Button>
      </PageHeader>
      <ErrorLine error={error} />
      {data?.length === 0 && (
        <Empty>Nenhum grupo ainda. Importe um grupo de prévias em que uma das contas seja admin.</Empty>
      )}
      <ul className="divide-y divide-line border-y border-line">
        {data?.map((c) => (
          <li key={c.id}>
            <Link href={`/grupos/${c.id}`} className="flex flex-wrap items-center gap-x-4 gap-y-1 py-4 hover:text-gold-soft">
              <span className="min-w-0 flex-1 basis-48 truncate font-medium">{c.title}</span>
              <StatusBadge status={c.status} />
              <span className="text-sm text-muted">{c.join_mode === "auto" ? "Aprovação automática" : "Aprovação manual"}</span>
              <span className="text-sm text-muted tabular-nums">
                {c.pending_count} pendentes, {c.member_count?.toLocaleString("pt-BR") ?? "—"} membros
              </span>
            </Link>
          </li>
        ))}
      </ul>
      <ImportChannelDialog
        open={importing}
        accounts={accounts.data ?? []}
        onClose={() => setImporting(false)}
        onDone={(c) => {
          setImporting(false);
          toast(`${c.title} importado`);
          void reload();
        }}
      />
    </>
  );
}
