import Link from "next/link";

import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata = { title: "Inbox — DEMIN" };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type ReplyRow = {
  id: string;
  received_at: string;
  raw_subject: string | null;
  raw_body: string | null;
  category: string | null;
  is_explicit_optout: boolean;
  ai_classification_reason: string | null;
  ai_suggested_response: string | null;
  human_action: string;
  contacts: {
    email: string;
    nombre: string | null;
    cargo: string | null;
    companies: {
      nombre: string;
      tier: string | null;
    } | null;
  } | null;
};

async function loadReplies(
  catFilter: string | null,
  page: number,
): Promise<ReplyRow[]> {
  const admin = createAdminClient();
  let q = admin
    .from("replies")
    .select(
      `
        id, received_at, raw_subject, raw_body, category,
        is_explicit_optout, ai_classification_reason, ai_suggested_response,
        human_action,
        contacts (
          email, nombre, cargo,
          companies (
            nombre, tier
          )
        )
      `,
    )
    .order("received_at", { ascending: false });
  if (catFilter && catFilter !== "all") {
    q = q.eq("category", catFilter);
  }
  const from = page * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;
  const { data, error } = await q.range(from, to);

  if (error) {
    throw new Error(`load replies fallo: ${error.message}`);
  }
  // Normalize 1:1 joins (PostgREST a veces devuelve array).
  const items: ReplyRow[] = [];
  for (const row of (data ?? []) as Array<Record<string, unknown>>) {
    const ct = Array.isArray(row.contacts) ? row.contacts[0] : row.contacts;
    let normalized_ct: ReplyRow["contacts"] = null;
    if (ct) {
      const co = Array.isArray((ct as { companies?: unknown }).companies)
        ? (ct as { companies: unknown[] }).companies[0]
        : (ct as { companies?: unknown }).companies;
      normalized_ct = {
        email: (ct as { email: string }).email,
        nombre: (ct as { nombre: string | null }).nombre ?? null,
        cargo: (ct as { cargo: string | null }).cargo ?? null,
        companies: co
          ? {
              nombre: (co as { nombre: string }).nombre,
              tier: (co as { tier: string | null }).tier ?? null,
            }
          : null,
      };
    }
    items.push({
      id: row.id as string,
      received_at: row.received_at as string,
      raw_subject: (row.raw_subject as string | null) ?? null,
      raw_body: (row.raw_body as string | null) ?? null,
      category: (row.category as string | null) ?? null,
      is_explicit_optout: Boolean(row.is_explicit_optout),
      ai_classification_reason:
        (row.ai_classification_reason as string | null) ?? null,
      ai_suggested_response:
        (row.ai_suggested_response as string | null) ?? null,
      human_action: row.human_action as string,
      contacts: normalized_ct,
    });
  }
  return items;
}

const CATEGORY_LABEL: Record<string, string> = {
  interesado: "Interesado",
  pide_info: "Pide info",
  no_ahora: "No ahora",
  no_interesado: "No interesado",
  rebote: "Rebote",
  fuera_oficina: "Fuera oficina",
  desconocido: "Desconocido",
};

function categoryBadge(cat: string | null): string {
  if (cat === "interesado") return "bg-emerald-100 text-emerald-900";
  if (cat === "pide_info") return "bg-blue-100 text-blue-900";
  if (cat === "no_ahora") return "bg-amber-100 text-amber-900";
  if (cat === "no_interesado") return "bg-orange-100 text-orange-900";
  if (cat === "rebote") return "bg-red-100 text-red-900";
  if (cat === "fuera_oficina") return "bg-purple-100 text-purple-900";
  return "bg-muted text-muted-foreground";
}

function humanActionBadge(act: string): string {
  if (act === "pendiente") return "bg-yellow-100 text-yellow-900";
  if (act === "escalado") return "bg-red-100 text-red-900";
  if (act === "respondido") return "bg-emerald-100 text-emerald-900";
  if (act === "archivado") return "bg-muted text-muted-foreground";
  if (act === "reprogramado") return "bg-blue-100 text-blue-900";
  return "bg-muted text-muted-foreground";
}

async function loadCategoryCounts(): Promise<Record<string, number>> {
  const admin = createAdminClient();
  const cats = [
    "interesado",
    "pide_info",
    "no_ahora",
    "no_interesado",
    "rebote",
    "fuera_oficina",
    "desconocido",
  ];
  const counts: Record<string, number> = { all: 0 };
  const total = await admin
    .from("replies")
    .select("id", { count: "exact", head: true });
  counts.all = total.count ?? 0;
  for (const c of cats) {
    const r = await admin
      .from("replies")
      .select("id", { count: "exact", head: true })
      .eq("category", c);
    counts[c] = r.count ?? 0;
  }
  return counts;
}

export default async function InboxPage({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string; page?: string }>;
}) {
  const sp = await searchParams;
  const catFilter = sp.cat ?? "all";
  const page = Math.max(0, parseInt(sp.page ?? "0", 10) || 0);
  const [replies, catCounts] = await Promise.all([
    loadReplies(catFilter === "all" ? null : catFilter, page),
    loadCategoryCounts(),
  ]);

  // Agrupar por estado pendiente vs auto-handled.
  const pendientes = replies.filter((r) => r.human_action === "pendiente");
  const handled = replies.filter((r) => r.human_action !== "pendiente");

  const filterLinks = [
    { key: "all", label: "Todas" },
    { key: "interesado", label: "Interesado" },
    { key: "pide_info", label: "Pide info" },
    { key: "no_ahora", label: "No ahora" },
    { key: "no_interesado", label: "No interesado" },
    { key: "rebote", label: "Rebote" },
    { key: "fuera_oficina", label: "Fuera oficina" },
    { key: "desconocido", label: "Desconocido" },
  ];

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">Inbox</h1>
        <p className="text-sm text-muted-foreground">
          Respuestas recibidas. {pendientes.length} pendientes en esta página
          (interesado / pide_info / desconocido escalados). {handled.length}{" "}
          auto-procesadas. Pagina {page + 1} ({PAGE_SIZE} por pagina).
        </p>
      </div>

      {/* Filtros por categoria con counts */}
      <div className="flex flex-wrap gap-2">
        {filterLinks.map((f) => {
          const active = catFilter === f.key;
          const count = catCounts[f.key] ?? 0;
          return (
            <Link
              key={f.key}
              href={f.key === "all" ? "/inbox" : `/inbox?cat=${f.key}`}
              className={`rounded-md border px-3 py-1 text-xs ${active ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
            >
              {f.label} <span className="ml-1 opacity-70">({count})</span>
            </Link>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">
            Pendientes ({pendientes.length})
          </h2>
          <p className="text-xs text-muted-foreground">
            Estas respuestas requieren tu atención. Acción Apéndice A regla 2:
            opt-out enforced automáticamente; cualquier otra acción humana se
            hace fuera del dashboard por ahora (responder desde Gmail Gonzalo).
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          {pendientes.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No hay respuestas pendientes.
            </p>
          ) : (
            <div className="space-y-3">
              {pendientes.map((r) => (
                <ReplyCard key={r.id} reply={r} />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="text-lg font-semibold">
            Auto-procesadas ({handled.length})
          </h2>
          <p className="text-xs text-muted-foreground">
            Histórico. handle_actions ya ejecutó la acción correspondiente.
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="pt-4">
          {handled.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Aún no hay respuestas auto-procesadas.
            </p>
          ) : (
            <div className="space-y-3">
              {handled.map((r) => (
                <ReplyCard key={r.id} reply={r} compact />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Paginacion */}
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div>
          Pagina {page + 1} · {replies.length} resultados.
        </div>
        <div className="flex gap-2">
          {page > 0 && (
            <Link
              href={`/inbox?${catFilter !== "all" ? `cat=${catFilter}&` : ""}page=${page - 1}`}
              className="rounded-md border px-3 py-1 hover:bg-muted"
            >
              ← Anterior
            </Link>
          )}
          {replies.length === PAGE_SIZE && (
            <Link
              href={`/inbox?${catFilter !== "all" ? `cat=${catFilter}&` : ""}page=${page + 1}`}
              className="rounded-md border px-3 py-1 hover:bg-muted"
            >
              Siguiente →
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function ReplyCard({
  reply,
  compact = false,
}: {
  reply: ReplyRow;
  compact?: boolean;
}) {
  const company = reply.contacts?.companies?.nombre ?? "—";
  const contact_email = reply.contacts?.email ?? "—";
  const tier = reply.contacts?.companies?.tier ?? "—";
  const dt = new Date(reply.received_at);
  const dt_str = dt.toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
  return (
    <div className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <strong>{company}</strong>
        <span className="text-xs text-muted-foreground">
          ({contact_email})
        </span>
        <span className="rounded-md border px-2 py-0.5 text-xs uppercase">
          {tier}
        </span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs uppercase ${categoryBadge(reply.category)}`}
        >
          {reply.category ? (CATEGORY_LABEL[reply.category] ?? reply.category) : "sin clasificar"}
        </span>
        <span
          className={`rounded-md px-2 py-0.5 text-xs uppercase ${humanActionBadge(reply.human_action)}`}
        >
          {reply.human_action}
        </span>
        {reply.is_explicit_optout && (
          <span className="rounded-md bg-red-100 px-2 py-0.5 text-xs uppercase text-red-900">
            OPT-OUT
          </span>
        )}
        <span className="ml-auto text-xs text-muted-foreground">{dt_str}</span>
      </div>
      <p className="mt-2 text-sm font-medium">
        {reply.raw_subject ?? "(sin asunto)"}
      </p>
      {!compact && reply.raw_body && (
        <pre className="mt-2 whitespace-pre-wrap rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
          {reply.raw_body.slice(0, 800)}
          {reply.raw_body.length > 800 ? "\n\n[truncado]" : ""}
        </pre>
      )}
      {reply.ai_classification_reason && (
        <p className="mt-2 text-xs text-muted-foreground italic">
          IA: {reply.ai_classification_reason}
        </p>
      )}
      {reply.ai_suggested_response && (
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer font-medium text-emerald-900">
            Respuesta sugerida IA
          </summary>
          <pre className="mt-1 whitespace-pre-wrap rounded-md bg-emerald-50 p-2">
            {reply.ai_suggested_response}
          </pre>
        </details>
      )}
    </div>
  );
}
