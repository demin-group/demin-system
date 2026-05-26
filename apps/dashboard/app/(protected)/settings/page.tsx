import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import {
  SettingsContent,
  type MailboxRow,
  type AutonomousConditionResult,
} from "./settings-content";

export const metadata = { title: "Settings — DEMIN" };
export const dynamic = "force-dynamic";

// Decision PM L50: pool threshold 50 (no 100).
const POOL_VIRGENES_THRESHOLD = 50;
const APROBACIONES_THRESHOLD = 50;
const REQUIRED_MIGRATIONS = [
  "20260525190000_14_message_revisions.sql",
  "20260526200000_15_messages_reply_tracking.sql",
  "20260526230000_16_auto_switch_autonomous.sql",
];

async function loadMailboxes(): Promise<MailboxRow[]> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("mailboxes")
    .select(
      "id, email, display_name, daily_cap, current_day_sent, warmup_status, status, pause_reason, hitl_mode, auto_switch_enabled, scheduled_autonomous_switch_at",
    )
    .order("email", { ascending: true });
  if (error) {
    throw new Error(`load mailboxes fallo: ${error.message}`);
  }
  return (data ?? []) as MailboxRow[];
}

/**
 * Evalua las 7 condiciones del Bloque 6 server-side. Espejo del worker
 * monitoring/auto_switch_to_autonomous.py para que /settings muestre lo
 * mismo que el worker decide.
 */
async function evaluateAutonomousConditions(): Promise<AutonomousConditionResult[]> {
  const admin = createAdminClient();
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const fourteenDaysAgo = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000).toISOString();

  // Cond 1: migrations.
  const migrationsRes = await admin.from("_migrations").select("filename");
  const applied = new Set((migrationsRes.data ?? []).map((r) => r.filename as string));
  const missing = REQUIRED_MIGRATIONS.filter((m) => !applied.has(m));
  const cond1: AutonomousConditionResult = {
    name: "1_migrations",
    label: "Migrations 14+15+16 aplicadas",
    ok: missing.length === 0,
    detail: `applied=${REQUIRED_MIGRATIONS.length - missing.length}/${REQUIRED_MIGRATIONS.length}`,
  };

  // Cond 2: aprobaciones acumuladas.
  const aprobRes = await admin
    .from("messages")
    .select("id", { count: "exact", head: true })
    .in("status", ["approved", "sent"]);
  const aprob = aprobRes.count ?? 0;
  const cond2: AutonomousConditionResult = {
    name: "2_aprobaciones",
    label: `Aprobaciones acumuladas ≥${APROBACIONES_THRESHOLD}`,
    ok: aprob >= APROBACIONES_THRESHOLD,
    detail: `acumuladas=${aprob}/${APROBACIONES_THRESHOLD}`,
  };

  // Cond 3: B7 operativo + replies.
  const mbRes = await admin
    .from("mailboxes")
    .select("id", { count: "exact", head: true })
    .eq("status", "active")
    .not("oauth_refresh_token_encrypted", "is", null);
  const tokenOk = (mbRes.count ?? 0) > 0;
  const repRes = await admin
    .from("replies")
    .select("id", { count: "exact", head: true });
  const replies = repRes.count ?? 0;
  const cond3: AutonomousConditionResult = {
    name: "3_b7_y_replies",
    label: "B7 operativo + ≥1 reply real",
    ok: tokenOk && replies >= 1,
    detail: `mailbox_token=${tokenOk}, replies=${replies}`,
  };

  // Cond 4: sin bounces ni spam 7d.
  const bounceRes = await admin
    .from("events")
    .select("id", { count: "exact", head: true })
    .in("type", ["bounce", "spam_complaint"])
    .gte("created_at", sevenDaysAgo);
  const bounces = bounceRes.count ?? 0;
  const cond4: AutonomousConditionResult = {
    name: "4_sin_bounces",
    label: "Cero bounces/spam 7d",
    ok: bounces === 0,
    detail: `events_bounce_spam_7d=${bounces}`,
  };

  // Cond 5: pool virgenes. Hacemos en 2 pasos con JS.
  // Companies fit researched -> contacts primary+!optout -> not in messages.
  // Simplificacion: contamos directamente contacts elegibles via embedding chain.
  const compsRes = await admin
    .from("companies")
    .select("id")
    .eq("ia_fit", "fit")
    .not("research_done_at", "is", null)
    .limit(2000);
  const compIds = (compsRes.data ?? []).map((r: { id: string }) => r.id);
  let virgenes = 0;
  if (compIds.length > 0) {
    const ctsRes = await admin
      .from("contacts")
      .select("id, company_id")
      .in("company_id", compIds)
      .eq("is_primary", true)
      .eq("is_optout", false)
      .limit(5000);
    const cts = ctsRes.data ?? [];
    if (cts.length > 0) {
      // For each contact, check if it has any message in active states.
      // Hacemos batch query a messages para los contact_ids.
      const ctIds = cts.map((c: { id: string }) => c.id);
      const msgRes = await admin
        .from("messages")
        .select("contact_id")
        .in("contact_id", ctIds)
        .in("status", ["sent", "scheduled", "drafted", "approved"]);
      const tocados = new Set(
        (msgRes.data ?? []).map((m: { contact_id: string }) => m.contact_id),
      );
      // Virgenes: companies con al menos 1 contact primary+activo NO tocado.
      const companiesVirgenes = new Set<string>();
      for (const c of cts as { id: string; company_id: string }[]) {
        if (!tocados.has(c.id)) {
          companiesVirgenes.add(c.company_id);
        }
      }
      virgenes = companiesVirgenes.size;
    }
  }
  const cond5: AutonomousConditionResult = {
    name: "5_pool_virgenes",
    label: `Pool vírgenes elegibles ≥${POOL_VIRGENES_THRESHOLD}`,
    ok: virgenes >= POOL_VIRGENES_THRESHOLD,
    detail: `virgenes=${virgenes}/${POOL_VIRGENES_THRESHOLD}`,
  };

  // Cond 6: replenish no reescribe (0 contacts con >=3 msgs en 14d).
  // Aproximacion: contamos messages 14d agrupados (sin SQL agregado puro
  // en PostgREST, vamos a leer + agrupar en JS).
  const recentMsgRes = await admin
    .from("messages")
    .select("contact_id")
    .gte("created_at", fourteenDaysAgo)
    .limit(5000);
  const counts: Record<string, number> = {};
  for (const m of (recentMsgRes.data ?? []) as { contact_id: string | null }[]) {
    if (m.contact_id) counts[m.contact_id] = (counts[m.contact_id] ?? 0) + 1;
  }
  const reescritos = Object.values(counts).filter((n) => n >= 3).length;
  const cond6: AutonomousConditionResult = {
    name: "6_replenish_no_reescribe",
    label: "Replenish no reescribe (0 contacts con ≥3 msgs en 14d)",
    ok: reescritos === 0,
    detail: `contacts_con_3+msgs_14d=${reescritos}`,
  };

  // Cond 7: Lemwarm pausado (no verificable desde Code).
  const cond7: AutonomousConditionResult = {
    name: "7_lemwarm_pausado",
    label: "Lemwarm pausado (L38)",
    ok: true,
    detail: "no verificable desde Code — PM confirma manualmente",
  };

  return [cond1, cond2, cond3, cond4, cond5, cond6, cond7];
}

export default async function SettingsPage() {
  const [mailboxes, conditions] = await Promise.all([
    loadMailboxes(),
    evaluateAutonomousConditions(),
  ]);
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
        autonomousConditions={conditions}
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
        <strong>{mb.daily_cap}</strong> · enviados cumulativo cache:{" "}
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
