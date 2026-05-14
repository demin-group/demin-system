import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import { SettingsContent, type MailboxRow } from "./settings-content";

export const metadata = { title: "Settings — DEMIN" };
export const dynamic = "force-dynamic";

async function loadMailboxes(): Promise<MailboxRow[]> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("mailboxes")
    .select(
      "id, email, display_name, daily_cap, current_day_sent, warmup_status, status, pause_reason, hitl_mode",
    )
    .order("email", { ascending: true });
  if (error) {
    throw new Error(`load mailboxes fallo: ${error.message}`);
  }
  return (data ?? []) as MailboxRow[];
}

export default async function SettingsPage() {
  const mailboxes = await loadMailboxes();
  const anyActive = mailboxes.some((m) => m.status === "active");
  const anyPaused = mailboxes.some((m) => m.status === "paused");

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Configuracion minima paso 7. Pausa de emergencia + estado de buzones.
          Toggle HITL/autonomo, caps editables, horario y palabras gatillo
          quedan diferidos a Fase 3.
        </p>
      </div>

      <SettingsContent
        initialMailboxes={mailboxes}
        anyActive={anyActive}
        anyPaused={anyPaused}
      />

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Buzones</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          {mailboxes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No hay mailboxes. Aplica migration 11.
            </p>
          ) : (
            <div className="space-y-3">
              {mailboxes.map((mb) => (
                <MailboxCard key={mb.id} mb={mb} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Apendice A regla 6</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4 text-sm text-muted-foreground">
          La auto-pausa (umbrales bounce 2% / spam 0.1% en 7d) NO se puede
          desactivar desde esta pantalla. Pausa de emergencia y reanudar son
          las dos palancas humanas; auto_pause.py vigila bounce/spam y pausa
          automaticamente si dispara threshold.
        </CardContent>
      </Card>
    </div>
  );
}

function MailboxCard({ mb }: { mb: MailboxRow }) {
  const statusBadge =
    mb.status === "active"
      ? "bg-emerald-100 text-emerald-900"
      : mb.status === "paused"
        ? "bg-amber-100 text-amber-900"
        : "bg-muted text-muted-foreground";
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{mb.email}</strong>
        <span
          className={`rounded-md px-2 py-0.5 text-xs uppercase ${statusBadge}`}
        >
          {mb.status}
        </span>
        <span className="rounded-md border px-2 py-0.5 text-xs uppercase">
          warmup: {mb.warmup_status}
        </span>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Display name: <strong>{mb.display_name ?? "—"}</strong> · cap diario:{" "}
        <strong>{mb.daily_cap}</strong> · enviados rolling 24h cache:{" "}
        <strong>{mb.current_day_sent}</strong>
        {mb.pause_reason ? (
          <>
            <span> · pause_reason: </span>
            <code className="text-xs">{mb.pause_reason}</code>
          </>
        ) : null}
      </p>
    </div>
  );
}
