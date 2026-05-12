import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata = { title: "Metrics — DEMIN" };
export const dynamic = "force-dynamic";

type FunnelCounts = {
  drafted: number;
  approved: number;
  scheduled: number;
  sent: number;
  bounced: number;
  failed: number;
  cancelled: number;
};

type Rates7d = {
  sent_7d: number;
  bounces_7d: number;
  failed_7d: number;
  replies_7d: number;
};

type MonthCost = {
  cost_usd: number;
  drafts_count: number;
};

async function loadFunnel(): Promise<FunnelCounts> {
  const admin = createAdminClient();
  const statuses: (keyof FunnelCounts)[] = [
    "drafted",
    "approved",
    "scheduled",
    "sent",
    "bounced",
    "failed",
    "cancelled",
  ];
  const out: FunnelCounts = {
    drafted: 0,
    approved: 0,
    scheduled: 0,
    sent: 0,
    bounced: 0,
    failed: 0,
    cancelled: 0,
  };
  for (const st of statuses) {
    const { count, error } = await admin
      .from("messages")
      .select("id", { count: "exact", head: true })
      .eq("status", st);
    if (error) throw new Error(`funnel ${st} fallo: ${error.message}`);
    out[st] = count ?? 0;
  }
  return out;
}

async function loadRates7d(): Promise<Rates7d> {
  const admin = createAdminClient();
  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();

  const [sentRes, bounceRes, failedRes, replyRes] = await Promise.all([
    admin
      .from("events")
      .select("id", { count: "exact", head: true })
      .eq("type", "message_sent")
      .gte("created_at", sevenDaysAgo),
    admin
      .from("events")
      .select("id", { count: "exact", head: true })
      .eq("type", "bounce")
      .gte("created_at", sevenDaysAgo),
    admin
      .from("events")
      .select("id", { count: "exact", head: true })
      .eq("type", "message_failed")
      .gte("created_at", sevenDaysAgo),
    admin
      .from("replies")
      .select("id", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
  ]);

  return {
    sent_7d: sentRes.count ?? 0,
    bounces_7d: bounceRes.count ?? 0,
    failed_7d: failedRes.count ?? 0,
    replies_7d: replyRes.count ?? 0,
  };
}

async function loadMonthCost(): Promise<MonthCost> {
  const admin = createAdminClient();
  const monthStart = new Date(
    new Date().getFullYear(),
    new Date().getMonth(),
    1,
  ).toISOString();
  const { data, error } = await admin
    .from("messages")
    .select("generation_cost_usd")
    .gte("created_at", monthStart);
  if (error) throw new Error(`month cost fallo: ${error.message}`);
  let cost = 0;
  let drafts = 0;
  for (const r of data ?? []) {
    if (r.generation_cost_usd != null) {
      cost += Number(r.generation_cost_usd);
      drafts += 1;
    }
  }
  return { cost_usd: cost, drafts_count: drafts };
}

function pct(n: number, d: number): string {
  if (d === 0) return "—";
  return `${((n / d) * 100).toFixed(2)}%`;
}

export default async function MetricsPage() {
  const [funnel, rates, monthCost] = await Promise.all([
    loadFunnel(),
    loadRates7d(),
    loadMonthCost(),
  ]);

  const totalMessages =
    funnel.drafted +
    funnel.approved +
    funnel.scheduled +
    funnel.sent +
    funnel.bounced +
    funnel.failed +
    funnel.cancelled;

  const bounceRate = pct(rates.bounces_7d, rates.sent_7d);
  const failRate = pct(rates.failed_7d, rates.sent_7d);
  const replyRate = pct(rates.replies_7d, rates.sent_7d);

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">Metrics</h1>
        <p className="text-sm text-muted-foreground">
          Estado del pipeline outreach. Datos en tiempo real desde la BD.
          Vista minima para paso 7 — refinamiento con datos reales en Fase 3.
        </p>
      </div>

      {/* Embudo */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Embudo (todo el historial)</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-7">
            <MetricCell label="Drafted" value={funnel.drafted} hint="HITL queue" />
            <MetricCell label="Approved" value={funnel.approved} hint="listos enviar" />
            <MetricCell label="Scheduled" value={funnel.scheduled} hint="con jitter" />
            <MetricCell label="Sent" value={funnel.sent} hint="enviados Gmail" />
            <MetricCell label="Bounced" value={funnel.bounced} hint="sync bounce" />
            <MetricCell label="Failed" value={funnel.failed} hint="error envio" />
            <MetricCell label="Cancelled" value={funnel.cancelled} hint="hitl/auto" />
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Total messages historico: <strong>{totalMessages}</strong>.
          </p>
        </CardContent>
      </Card>

      {/* Rates 7d */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Rates 7 dias rolling</h2>
        </CardHeader>
        <Separator />
        <CardContent className="grid grid-cols-2 gap-4 pt-4 sm:grid-cols-4">
          <MetricCell
            label="Sent 7d"
            value={rates.sent_7d}
            hint="base denominador"
          />
          <MetricCell
            label="Bounce rate"
            value={bounceRate}
            hint={`${rates.bounces_7d} bounces / ${rates.sent_7d} sent · auto-pause >2%`}
            tone={rates.sent_7d >= 50 && rates.bounces_7d / Math.max(rates.sent_7d, 1) > 0.02 ? "danger" : "neutral"}
          />
          <MetricCell
            label="Fail rate"
            value={failRate}
            hint={`${rates.failed_7d} failed / ${rates.sent_7d} sent`}
          />
          <MetricCell
            label="Reply rate"
            value={replyRate}
            hint={`${rates.replies_7d} replies / ${rates.sent_7d} sent`}
          />
        </CardContent>
      </Card>

      {/* Coste mes */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Coste mes en curso</h2>
        </CardHeader>
        <Separator />
        <CardContent className="grid grid-cols-2 gap-4 pt-4 sm:grid-cols-3">
          <MetricCell
            label="LLM coste mes"
            value={`$${monthCost.cost_usd.toFixed(4)}`}
            hint={`${monthCost.drafts_count} drafts con cost`}
          />
          <MetricCell
            label="Drafts mes"
            value={monthCost.drafts_count}
            hint="generation_cost_usd no nulo"
          />
          <MetricCell
            label="Avg coste/draft"
            value={
              monthCost.drafts_count > 0
                ? `$${(monthCost.cost_usd / monthCost.drafts_count).toFixed(4)}`
                : "—"
            }
            hint="LLM solo (no incluye Hunter/Voyage)"
          />
        </CardContent>
      </Card>

      <p className="text-xs text-muted-foreground">
        Pendientes Fase 3: gráficas, breakdown por ángulo (opening/reframe/closing),
        deliverability por buzón (Postmaster Tools), conversión por tier.
      </p>
    </div>
  );
}

type CellTone = "neutral" | "danger";

function MetricCell({
  label,
  value,
  hint,
  tone = "neutral",
}: {
  label: string;
  value: number | string;
  hint: string;
  tone?: CellTone;
}) {
  return (
    <div className="space-y-1">
      <p className="text-xs uppercase text-muted-foreground">{label}</p>
      <p
        className={
          tone === "danger"
            ? "text-2xl font-semibold text-destructive"
            : "text-2xl font-semibold"
        }
      >
        {value}
      </p>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
