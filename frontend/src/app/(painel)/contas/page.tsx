"use client";

import { useState } from "react";
import { AccountRing } from "@/components/accounts/AccountRing";
import { ImportSessionDialog } from "@/components/accounts/ImportSessionDialog";
import { LoginWizard } from "@/components/accounts/LoginWizard";
import { Button, Confirm, Dialog, Empty, ErrorLine, PageHeader, StatusBadge } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";
import { api, ApiError } from "@/lib/api";
import { toSaoPaulo } from "@/lib/time";
import type { Account } from "@/lib/types";
import { accountName } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function ContasPage() {
  const { data, error, reload } = useApi<Account[]>("/accounts");
  const toast = useToast();
  const [wizard, setWizard] = useState<{ open: boolean; accountId?: number }>({ open: false });
  const [importFor, setImportFor] = useState<Account | null>(null);
  const [removing, setRemoving] = useState<Account | null>(null);
  const [checking, setChecking] = useState<number | null>(null);

  async function check(a: Account) {
    setChecking(a.id);
    try {
      const r = await api<Account>(`/accounts/${a.id}/check`, { method: "POST" });
      toast(r.status === "online" ? `${accountName(r)} está online` : `${accountName(r)}: ${r.status}`);
      await reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro", "error");
    } finally {
      setChecking(null);
    }
  }

  async function remove() {
    if (!removing) return;
    try {
      await api(`/accounts/${removing.id}`, { method: "DELETE" });
      toast("Conta removida");
      await reload();
    } catch (e) {
      toast(e instanceof ApiError ? e.detail : "erro", "error");
    } finally {
      setRemoving(null);
    }
  }

  return (
    <>
      <PageHeader title="Contas">
        <Button variant="primary" onClick={() => setWizard({ open: true })}>
          Conectar conta
        </Button>
      </PageHeader>
      <ErrorLine error={error} />

      {data && data.length === 0 && (
        <Empty>Nenhuma conta conectada. Conecte a conta de cada modelo para agendar posts e gerenciar os grupos.</Empty>
      )}

      <ul className="divide-y divide-line border-y border-line">
        {data?.map((a) => (
          <li key={a.id} className="flex flex-wrap items-center gap-4 py-4">
            <AccountRing account={a} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate font-medium">{accountName(a)}</p>
              <p className="text-xs text-muted">
                {a.phone}
                {a.last_seen_at && `, visto ${toSaoPaulo(a.last_seen_at)}`}
              </p>
              {a.status === "dead" && a.dead_reason && (
                <p className="mt-1 text-xs text-[#ff9c92]">Motivo: {a.dead_reason}</p>
              )}
            </div>
            <StatusBadge status={a.status} />
            <div className="flex w-full flex-wrap gap-2 sm:w-auto">
              {a.status === "dead" ? (
                <>
                  <Button variant="primary" onClick={() => setWizard({ open: true, accountId: a.id })}>
                    Relogar
                  </Button>
                  <Button onClick={() => setImportFor(a)}>Importar session</Button>
                </>
              ) : (
                <Button busy={checking === a.id} onClick={() => check(a)}>
                  Verificar
                </Button>
              )}
              <Button variant="danger" onClick={() => setRemoving(a)}>
                Remover
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <Dialog
        open={wizard.open}
        onClose={() => setWizard({ open: false })}
        title={wizard.accountId ? "Relogar conta" : "Conectar conta"}
      >
        <LoginWizard
          key={wizard.accountId ?? "new"}
          accountId={wizard.accountId}
          onDone={(a) => {
            setWizard({ open: false });
            toast(`${accountName(a)} conectada`);
            void reload();
          }}
        />
      </Dialog>

      <ImportSessionDialog
        account={importFor}
        onClose={() => setImportFor(null)}
        onDone={(a) => {
          setImportFor(null);
          toast(`${accountName(a)} reconectada`);
          void reload();
        }}
      />

      <Confirm
        open={Boolean(removing)}
        title="Remover conta"
        body={
          <>
            {removing && accountName(removing)} sai do painel e os posts agendados dela são cancelados. A conta continua
            existindo no Telegram.
          </>
        }
        action="Remover conta"
        danger
        onConfirm={remove}
        onClose={() => setRemoving(null)}
      />
    </>
  );
}
