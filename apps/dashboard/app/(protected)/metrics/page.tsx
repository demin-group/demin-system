import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata = { title: "Metrics — DEMIN" };
export const dynamic = "force-dynamic";

type FunnelTop = {
  companies_total: number;
  companies_descartado: number;
  companies_fit: number;
  companies_no_fit: number;
  companies_pendiente: number;
  companies_dudoso: number;
  companies_research_done: number;
  contacts_total: number;
  contacts_primary: number;
};

type FunnelMessages = {
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

type AngleStats = {
  angle: string;
  sent: number;
  replied: number;
};

type TierStats = {
  tier: string;
  companies: number;
  fit: number;
  contacts: number;
  sent: number;
  replied: number;
};

type MonthCost = {
  llm_cost_usd: number;
  drafts_count: number;
  hunter_calls_estimated: number;
};

type ReplyCategoryStats = {
  category: string;
  count: number;
};

type MailboxStats = {
  email: string;
  status: string;
  sent_7d: number;
  bounces_7d: number;
  current_day_sent: number;
  daily_cap: number;
};

async function loadFunnelTop(): Promise<FunnelTop> {
  const admin = createAdminClient();
  const states = ["fit", "no_fit", "pendiente", "dudoso", "descartado"];
  const promises = states.map(async (state) => {
    if (state === "descartado") {
      const r = await admin
        .from("companies")
        .select("id", { count: "exact", head: true })
        .eq("tier", "descartado");
      return { key: state, n: r.count ?? 0 };
    }
    const r = await admin
      .from("companies")
      .select("id", { count: "exact", head: true })
      .eq("ia_fit", state);
    return { key: state, n: r.count ?? 0 };
  });
  const results = await Promise.all(promises);
  const fit = results.find((r) => r.key === "fit")?.n ?? 0;
  const noFit = results.find((r) => r.key === "no_fit")?.n ?? 0;
  const pendiente = results.find((r) => r.key === "pendiente")?.n ?? 0;
  const dudoso = results.find((r) => r.key === "dudoso")?.n ?? 0;
  const descartado = results.find((r) => r.key === "descartado")?.n ?? 0;

  const total = await admin
    .from("companies")
    .select("id", { count: "exact", head: true });
  const researchDone = await admin
    .from("companies")
    .select("id", { count: "exact", head: true })
    .not("research_done_at", "is", null);
  const contactsTotal = await admin
    .from("contacts")
    .select("id", { count: "exact", head: true });
  const contactsPrimary = await admin
    .from("contacts")
    .select("id", { count: "exact", head: true })
    .eq("is_primary", true);

  return {
    companies_total: total.count ?? 0,
    companies_descartado: descartado,
    companies_fit: fit,
    companies_no_fit: noFit,
    companies_pendiente: pendiente,
    companies_dudoso: dudoso,
    companies_research_done: researchDone.count ?? 0,
    contacts_total: contactsTotal.count ?? 0,
    contacts_primary: contactsPrimary.count ?? 0,
  };
}

async function loadFunnelMessages(): Promise<FunnelMessages> {
  const admin = createAdminClient();
  const statuses: (keyof FunnelMessages)[] = [
    "drafted", "approved", "scheduled", "sent", "bounced", "failed", "cancelled",
  ];
  const out: FunnelMessages = {
    drafted: 0, approved: 0, scheduled: 0, sent: 0,
    bounced: 0, failed: 0, cancelled: 0,
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
    admin.from("events").select("id", { count: "exact", head: true })
      .eq("type", "message_sent").gte("created_at", sevenDaysAgo),
    admin.from("events").select("id", { count: "exact", head: true })
      .eq("type", "bounce").gte("created_at", sevenDaysAgo),
    admin.from("events").select("id", { count: "exact", head: true })
      .eq("type", "message_failed").gte("created_at", sevenDaysAgo),
    admin.from("replies").select("id", { count: "exact", head: true })
      .gte("created_at", sevenDaysAgo),
  ]);
  return {
    sent_7d: sentRes.count ?? 0,
    bounces_7d: bounceRes.count ?? 0,
    failed_7d: failedRes.count ?? 0,
    replies_7d: replyRes.count ?? 0,
  };
}

async function loadAngleStats(): Promise<AngleStats[]> {
  const admin = createAdminClient();
  const angles = ["opening", "reframe", "closing", "re_engage_60", "re_engage_90"];
  const out: AngleStats[] = [];
  for (const angle of angles) {
    const sent = await admin
      .from("messages")
      .select("id", { count: "exact", head: true })
      .eq("angle", angle)
      .eq("status", "sent");

    // replies de este angle: join messages para filtrar por angle.
    const sentRows = await admin
      .from("messages")
      .select("id")
      .eq("angle", angle)
      .eq("status", "sent")
      .limit(2000);
    const sentIds = (sentRows.data ?? []).map((r: { id: string }) => r.id);
    let replied = 0;
    if (sentIds.length > 0) {
      const rep = await admin
        .from("replies")
        .select("id", { count: "exact", head: true })
        .in("message_id", sentIds);
      replied = rep.count ?? 0;
    }
    out.push({
      angle,
      sent: sent.count ?? 0,
      replied,
    });
  }
  return out;
}

async function loadTierStats(): Promise<TierStats[]> {
  const admin = createAdminClient();
  const tiers = ["T1", "T2", "T3", "T4"];
  const out: TierStats[] = [];
  for (const t of tiers) {
    const companies = await admin
      .from("companies")
      .select("id", { count: "exact", head: true })
      .eq("tier", t);
    const fit = await admin
      .from("companies")
      .select("id", { count: "exact", head: true })
      .eq("tier", t)
      .eq("ia_fit", "fit");

    // contacts: join contacts -> companies con tier=t.
    const compsRows = await admin
      .from("companies")
      .select("id")
      .eq("tier", t)
      .limit(2000);
    const compIds = (compsRows.data ?? []).map((r: { id: string }) => r.id);
    let contactsCount = 0;
    let sentCount = 0;
    let repliedCount = 0;
    if (compIds.length > 0) {
      const cts = await admin
        .from("contacts")
        .select("id", { count: "exact", head: true })
        .in("company_id", compIds);
      contactsCount = cts.count ?? 0;

      // sent: messages.status=sent JOIN contact -> company in compIds
      const ctRows = await admin
        .from("contacts")
        .select("id")
        .in("company_id", compIds)
        .limit(2000);
      const ctIds = (ctRows.data ?? []).map((r: { id: string }) => r.id);
      if (ctIds.length > 0) {
        const sent = await admin
          .from("messages")
          .select("id", { count: "exact", head: true })
          .in("contact_id", ctIds)
          .eq("status", "sent");
        sentCount = sent.count ?? 0;

        const sentMsgs = await admin
          .from("messages")
          .select("id")
          .in("contact_id", ctIds)
          .eq("status", "sent")
          .limit(2000);
        const sentMsgIds = (sentMsgs.data ?? []).map((r: { id: string }) => r.id);
        if (sentMsgIds.length > 0) {
          const rep = await admin
            .from("replies")
            .select("id", { count: "exact", head: true })
            .in("message_id", sentMsgIds);
          repliedCount = rep.count ?? 0;
        }
      }
    }

    out.push({
      tier: t,
      companies: companies.count ?? 0,
      fit: fit.count ?? 0,
      contacts: contactsCount,
      sent: sentCount,
      replied: repliedCount,
    });
  }
  return out;
}

async function loadMailboxStats(): Promise<MailboxStats[]> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("mailboxes")
    .select("id, email, status, current_day_sent, daily_cap")
    .order("email", { ascending: true });
  if (error) throw new Error(`mailboxes fallo: ${error.message}`);

  const sevenDaysAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const out: MailboxStats[] = [];
  for (const mb of (data ?? []) as Array<{
    id: string; email: string; status: string;
    current_day_sent: number; daily_cap: number;
  }>) {
    const msgRows = await admin
      .from("messages")
      .select("id")
      .eq("mailbox_id", mb.id)
      .limit(2000);
    const msgIds = (msgRows.data ?? []).map((r: { id: string }) => r.id);
    let sent7d = 0;
    let bounces7d = 0;
    if (msgIds.length > 0) {
      const sentEv = await admin
        .from("events")
        .select("id", { count: "exact", head: true })
        .in("message_id", msgIds)
        .eq("type", "message_sent")
        .gte("created_at", sevenDaysAgo);
      sent7d = sentEv.count ?? 0;
      const bounceEv = await admin
        .from("events")
        .select("id", { count: "exact", head: true })
        .in("message_id", msgIds)
        .eq("type", "bounce")
        .gte("created_at", sevenDaysAgo);
      bounces7d = bounceEv.count ?? 0;
    }
    out.push({
      email: mb.email,
      status: mb.status,
      sent_7d: sent7d,
      bounces_7d: bounces7d,
      current_day_sent: mb.current_day_sent,
      daily_cap: mb.daily_cap,
    });
  }
  return out;
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

  // Estimacion Hunter: contacts insertados este mes desde email_source=hunter.
  const hunterCalls = await admin
    .from("contacts")
    .select("id", { count: "exact", head: true })
    .eq("email_source", "hunter")
    .gte("created_at", monthStart);

  return {
    llm_cost_usd: cost,
    drafts_count: drafts,
    hunter_calls_estimated: hunterCalls.count ?? 0,
  };
}

async function loadReplyCategoryStats(): Promise<ReplyCategoryStats[]> {
  const admin = createAdminClient();
  const cats = [
    "interesado", "pide_info", "no_ahora", "no_interesado",
    "rebote", "fuera_oficina", "desconocido",
  ];
  const out: ReplyCategoryStats[] = [];
  for (const c of cats) {
    const r = await admin
      .from("replies")
      .select("id", { count: "exact", head: true })
      .eq("category", c);
    out.push({ category: c, count: r.count ?? 0 });
  }
  return out;
}

function pct(n: number, d: number): string {
  if (d === 0) return "—";
  return `${((n / d) * 100).toFixed(2)}%`;
}

export default async function MetricsPage() {
  const [
    funnelTop, funnelMessages, rates, angleStats,
    tierStats, mailboxStats, monthCost, replyCats,
  ] = await Promise.all([
    loadFunnelTop(),
    loadFunnelMessages(),
    loadRates7d(),
    loadAngleStats(),
    loadTierStats(),
    loadMailboxStats(),
    loadMonthCost(),
    loadReplyCategoryStats(),
  ]);

  const totalMessages =
    funnelMessages.drafted + funnelMessages.approved + funnelMessages.scheduled +
    funnelMessages.sent + funnelMessages.bounced + funnelMessages.failed +
    funnelMessages.cancelled;

  const bounceRate = pct(rates.bounces_7d, rates.sent_7d);
  const failRate = pct(rates.failed_7d, rates.sent_7d);
  const replyRate = pct(rates.replies_7d, rates.sent_7d);
  const interesados = replyCats.find((c) => c.category === "interesado")?.count ?? 0;
  const totalReplies = replyCats.reduce((sum, c) => sum + c.count, 0);

  // Coste mensual desglosado estimado.
  const COST_PER_HUNTER_CALL = 0.030;   // Starter 30€/500 ≈ $0.0006 per call... but cobra cuando encuentra.
  const VOYAGE_EST_MONTH = 0.05;        // ~5c/mes uso real bajo.
  const HETZNER_MONTH_EUR = 9.67;
  const VERCEL_MONTH_USD = 0;           // Hobby tier gratuito hasta limits.

  const hunterCostEst = monthCost.hunter_calls_estimated * COST_PER_HUNTER_CALL;
  const totalMonthUSD =
    monthCost.llm_cost_usd + hunterCostEst + VOYAGE_EST_MONTH +
    HETZNER_MONTH_EUR + VERCEL_MONTH_USD;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">Metrics</h1>
        <p className="text-sm text-muted-foreground">
          Estado del pipeline outreach. Datos en tiempo real desde la BD.
          Embudo completo + rates 7d + reply rate por angulo + conversion por
          tier + coste mensual desglosado. Sprint 6 (2026-05-14).
        </p>
      </div>

      {/* Embudo top-of-funnel: companies + research + contacts */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Embudo top: ingest → fit → research → contacts</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-6">
            <MetricCell label="Companies" value={funnelTop.companies_total} hint="SABI ingest" />
            <MetricCell
              label="ia_fit=fit"
              value={funnelTop.companies_fit}
              hint={`${pct(funnelTop.companies_fit, funnelTop.companies_total)} de total`}
            />
            <MetricCell label="no_fit" value={funnelTop.companies_no_fit} hint="classify_descr" />
            <MetricCell label="pendientes" value={funnelTop.companies_pendiente} hint="sin classify" />
            <MetricCell label="dudosos" value={funnelTop.companies_dudoso} hint="auditar" />
            <MetricCell label="descartado" value={funnelTop.companies_descartado} hint="fuera tier" />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
            <MetricCell
              label="research_done"
              value={funnelTop.companies_research_done}
              hint={`${pct(funnelTop.companies_research_done, funnelTop.companies_fit)} de fit`}
            />
            <MetricCell label="contacts" value={funnelTop.contacts_total} hint="Hunter inserts" />
            <MetricCell
              label="contacts primary"
              value={funnelTop.contacts_primary}
              hint={`${pct(funnelTop.contacts_primary, funnelTop.contacts_total)} de contacts`}
            />
            <MetricCell
              label="cobertura efectiva"
              value={pct(funnelTop.contacts_primary, funnelTop.companies_research_done)}
              hint="primary / research_done"
            />
          </div>
        </CardContent>
      </Card>

      {/* Embudo messages */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Embudo messages (historico)</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-7">
            <MetricCell label="Drafted" value={funnelMessages.drafted} hint="HITL queue" />
            <MetricCell label="Approved" value={funnelMessages.approved} hint="listos enviar" />
            <MetricCell label="Scheduled" value={funnelMessages.scheduled} hint="con jitter" />
            <MetricCell label="Sent" value={funnelMessages.sent} hint="enviados Gmail" />
            <MetricCell label="Bounced" value={funnelMessages.bounced} hint="sync bounce" />
            <MetricCell label="Failed" value={funnelMessages.failed} hint="error envio" />
            <MetricCell label="Cancelled" value={funnelMessages.cancelled} hint="hitl/auto" />
          </div>
          <p className="mt-4 text-xs text-muted-foreground">
            Total messages historico: <strong>{totalMessages}</strong> ·
            Interesados (replies): <strong>{interesados}</strong> /{" "}
            <strong>{totalReplies}</strong> replies clasificadas.
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
          <MetricCell label="Sent 7d" value={rates.sent_7d} hint="base denominador" />
          <MetricCell
            label="Bounce rate"
            value={bounceRate}
            hint={`${rates.bounces_7d} bounces / ${rates.sent_7d} sent · auto-pause >2%`}
            tone={rates.sent_7d >= 50 && rates.bounces_7d / Math.max(rates.sent_7d, 1) > 0.02 ? "danger" : "neutral"}
          />
          <MetricCell label="Fail rate" value={failRate} hint={`${rates.failed_7d} failed / ${rates.sent_7d} sent`} />
          <MetricCell label="Reply rate" value={replyRate} hint={`${rates.replies_7d} replies / ${rates.sent_7d} sent`} />
        </CardContent>
      </Card>

      {/* Reply rate por angulo */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Reply rate por angulo</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Angle</th>
                <th className="pb-2 text-right">Sent</th>
                <th className="pb-2 text-right">Replies</th>
                <th className="pb-2 text-right">Reply rate</th>
              </tr>
            </thead>
            <tbody>
              {angleStats.map((s) => (
                <tr key={s.angle} className="border-t">
                  <td className="py-2">{s.angle}</td>
                  <td className="py-2 text-right">{s.sent}</td>
                  <td className="py-2 text-right">{s.replied}</td>
                  <td className="py-2 text-right font-medium">{pct(s.replied, s.sent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Conversion por tier */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Conversion por tier</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Tier</th>
                <th className="pb-2 text-right">Companies</th>
                <th className="pb-2 text-right">fit</th>
                <th className="pb-2 text-right">Contacts</th>
                <th className="pb-2 text-right">Sent</th>
                <th className="pb-2 text-right">Replies</th>
                <th className="pb-2 text-right">Reply rate</th>
              </tr>
            </thead>
            <tbody>
              {tierStats.map((s) => (
                <tr key={s.tier} className="border-t">
                  <td className="py-2">{s.tier}</td>
                  <td className="py-2 text-right">{s.companies}</td>
                  <td className="py-2 text-right">{s.fit}</td>
                  <td className="py-2 text-right">{s.contacts}</td>
                  <td className="py-2 text-right">{s.sent}</td>
                  <td className="py-2 text-right">{s.replied}</td>
                  <td className="py-2 text-right font-medium">{pct(s.replied, s.sent)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Deliverability por buzon */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Deliverability por buzon (7d)</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Mailbox</th>
                <th className="pb-2 text-right">Status</th>
                <th className="pb-2 text-right">Sent 7d</th>
                <th className="pb-2 text-right">Bounces 7d</th>
                <th className="pb-2 text-right">Bounce rate</th>
                <th className="pb-2 text-right">Today / cap</th>
              </tr>
            </thead>
            <tbody>
              {mailboxStats.map((s) => (
                <tr key={s.email} className="border-t">
                  <td className="py-2">{s.email}</td>
                  <td className="py-2 text-right">{s.status}</td>
                  <td className="py-2 text-right">{s.sent_7d}</td>
                  <td className="py-2 text-right">{s.bounces_7d}</td>
                  <td className="py-2 text-right font-medium">{pct(s.bounces_7d, s.sent_7d)}</td>
                  <td className="py-2 text-right">{s.current_day_sent} / {s.daily_cap}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {/* Coste mensual desglosado */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Coste mes en curso (desglosado, USD)</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="pb-2">Concepto</th>
                <th className="pb-2 text-right">USD</th>
                <th className="pb-2 text-right">Notas</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t">
                <td className="py-2">LLM (Anthropic) drafts</td>
                <td className="py-2 text-right">${monthCost.llm_cost_usd.toFixed(4)}</td>
                <td className="py-2 text-right text-xs">{monthCost.drafts_count} drafts</td>
              </tr>
              <tr className="border-t">
                <td className="py-2">Hunter (estimado)</td>
                <td className="py-2 text-right">${hunterCostEst.toFixed(4)}</td>
                <td className="py-2 text-right text-xs">{monthCost.hunter_calls_estimated} contacts inserted</td>
              </tr>
              <tr className="border-t">
                <td className="py-2">Voyage embeds (estimado)</td>
                <td className="py-2 text-right">${VOYAGE_EST_MONTH.toFixed(4)}</td>
                <td className="py-2 text-right text-xs">KB reembeds + queries</td>
              </tr>
              <tr className="border-t">
                <td className="py-2">Hetzner CPX22 VPS</td>
                <td className="py-2 text-right">€{HETZNER_MONTH_EUR.toFixed(2)}</td>
                <td className="py-2 text-right text-xs">flat, ya pagado</td>
              </tr>
              <tr className="border-t">
                <td className="py-2">Vercel</td>
                <td className="py-2 text-right">${VERCEL_MONTH_USD.toFixed(2)}</td>
                <td className="py-2 text-right text-xs">Hobby tier gratuito</td>
              </tr>
              <tr className="border-t font-medium">
                <td className="py-2">Total estimado</td>
                <td className="py-2 text-right">${totalMonthUSD.toFixed(2)}</td>
                <td className="py-2 text-right text-xs">D15 techo: 150€/mes ≈ $160</td>
              </tr>
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted-foreground">
            LLM real (Anthropic) viene de <code>messages.generation_cost_usd</code> agregado del mes en curso.
            Hunter es estimado por contacts insertados (Starter plan 30€/500 búsquedas).
            Voyage/Hetzner/Vercel son flat o muy bajos. Total bajo D15 techo.
          </p>
        </CardContent>
      </Card>

      {/* Reply categories breakdown */}
      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">Replies por categoría</h2>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {replyCats.map((c) => (
              <MetricCell
                key={c.category}
                label={c.category}
                value={c.count}
                hint=""
              />
            ))}
          </div>
        </CardContent>
      </Card>
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
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
