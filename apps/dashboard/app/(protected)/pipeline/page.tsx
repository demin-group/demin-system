import Link from "next/link";

import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";

export const metadata = { title: "Pipeline — DEMIN" };
export const dynamic = "force-dynamic";

const PAGE_SIZE = 50;

const TIERS = ["T1", "T2", "T3", "T4", "descartado"] as const;
const FITS = ["fit", "no_fit", "dudoso", "pendiente"] as const;

type CompanyRow = {
  id: string;
  nif: string;
  nombre: string;
  localidad: string | null;
  tier: string | null;
  ia_fit: string | null;
  ia_fit_reason: string | null;
  web: string | null;
  research_done_at: string | null;
};

type PipelineSearchParams = {
  tier?: string;
  ia_fit?: string;
  q?: string;
  page?: string;
};

async function loadPipeline(params: PipelineSearchParams) {
  const admin = createAdminClient();
  const tier = params.tier && TIERS.includes(params.tier as (typeof TIERS)[number])
    ? params.tier
    : null;
  const fit =
    params.ia_fit && FITS.includes(params.ia_fit as (typeof FITS)[number])
      ? params.ia_fit
      : null;
  const qRaw = (params.q ?? "").trim();
  const page = Math.max(1, Number.parseInt(params.page ?? "1", 10) || 1);

  let query = admin
    .from("companies")
    .select(
      "id, nif, nombre, localidad, tier, ia_fit, ia_fit_reason, web, research_done_at",
      { count: "exact" },
    );
  if (tier) query = query.eq("tier", tier);
  if (fit) query = query.eq("ia_fit", fit);
  if (qRaw) {
    // PostgREST .or con ilike — buscamos en nif y nombre.
    const escaped = qRaw.replace(/[%,]/g, "");
    query = query.or(`nif.ilike.%${escaped}%,nombre.ilike.%${escaped}%`);
  }

  const from = (page - 1) * PAGE_SIZE;
  const to = from + PAGE_SIZE - 1;
  query = query.order("nif", { ascending: true }).range(from, to);

  const res = await query;
  if (res.error) {
    throw new Error(`load pipeline fallo: ${res.error.message}`);
  }
  const rows = (res.data ?? []) as CompanyRow[];
  const ids = rows.map((r) => r.id);

  // Conteos por empresa: contacts y messages.status. Hacemos 2 queries
  // bulk filtradas por los ids de la página actual (no por todo el universo).
  const contactsCounts: Record<string, number> = {};
  const messagesCountsByStatus: Record<string, Record<string, number>> = {};
  if (ids.length > 0) {
    const c = await admin
      .from("contacts")
      .select("company_id")
      .in("company_id", ids);
    if (!c.error) {
      for (const r of c.data ?? []) {
        contactsCounts[r.company_id] = (contactsCounts[r.company_id] ?? 0) + 1;
      }
    }
    const m = await admin
      .from("messages")
      .select("contact_id, status, contacts!inner(company_id)")
      .in("contacts.company_id", ids);
    if (!m.error) {
      for (const r of m.data ?? []) {
        // r.contacts puede ser objeto o array según relación; tomamos defensivo
        const cid = (r.contacts as unknown as { company_id: string } | null)
          ?.company_id;
        if (!cid) continue;
        const bucket = messagesCountsByStatus[cid] ?? {};
        bucket[r.status] = (bucket[r.status] ?? 0) + 1;
        messagesCountsByStatus[cid] = bucket;
      }
    }
  }

  return {
    rows,
    total: res.count ?? 0,
    page,
    pageSize: PAGE_SIZE,
    contactsCounts,
    messagesCountsByStatus,
    filters: { tier, fit, q: qRaw },
  };
}

function formatDate(s: string | null): string {
  if (!s) return "—";
  // YYYY-MM-DD del timestamp; dejamos el resto fuera para tabla compacta
  return s.slice(0, 10);
}

function statusSummary(byStatus: Record<string, number> | undefined): string {
  if (!byStatus) return "—";
  const ordered = ["drafted", "approved", "scheduled", "sent", "bounced", "failed", "cancelled"];
  const parts: string[] = [];
  for (const s of ordered) {
    if (byStatus[s]) parts.push(`${s.slice(0, 3)}=${byStatus[s]}`);
  }
  return parts.length > 0 ? parts.join(" ") : "—";
}

function buildHref(params: PipelineSearchParams, override: Partial<PipelineSearchParams>): string {
  const merged: Record<string, string> = {};
  for (const [k, v] of Object.entries({ ...params, ...override })) {
    if (v !== undefined && v !== "" && v !== null) merged[k] = String(v);
  }
  const qs = new URLSearchParams(merged).toString();
  return qs ? `/pipeline?${qs}` : "/pipeline";
}

export default async function PipelinePage(props: {
  searchParams: Promise<PipelineSearchParams>;
}) {
  const params = await props.searchParams;
  const data = await loadPipeline(params);
  const { rows, total, page, pageSize, contactsCounts, messagesCountsByStatus, filters } =
    data;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">Pipeline</h1>
        <p className="text-sm text-muted-foreground">
          Vista del funnel de outreach: empresas filtradas, contactos enriquecidos,
          drafts en cola. {total} empresas con los filtros actuales.
        </p>
      </div>

      <Card>
        <CardContent className="pt-6">
          <form
            method="get"
            action="/pipeline"
            className="flex flex-wrap items-end gap-3"
          >
            <div className="flex flex-col gap-1">
              <label htmlFor="tier" className="text-xs font-medium text-muted-foreground">
                Tier
              </label>
              <select
                id="tier"
                name="tier"
                defaultValue={filters.tier ?? ""}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">todos</option>
                {TIERS.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <label htmlFor="ia_fit" className="text-xs font-medium text-muted-foreground">
                IA fit
              </label>
              <select
                id="ia_fit"
                name="ia_fit"
                defaultValue={filters.fit ?? ""}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                <option value="">todos</option>
                {FITS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1 grow min-w-[200px]">
              <label htmlFor="q" className="text-xs font-medium text-muted-foreground">
                Búsqueda (NIF o nombre)
              </label>
              <Input id="q" name="q" defaultValue={filters.q} placeholder="A12345678 o ACME" />
            </div>
            <Button type="submit">Filtrar</Button>
            <Link
              href="/pipeline"
              className="text-sm text-muted-foreground underline-offset-4 hover:underline"
            >
              limpiar
            </Link>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs uppercase text-muted-foreground">
              <tr>
                <th className="px-2 py-2 font-medium">NIF</th>
                <th className="px-2 py-2 font-medium">Empresa</th>
                <th className="px-2 py-2 font-medium">Tier</th>
                <th className="px-2 py-2 font-medium">IA fit</th>
                <th className="px-2 py-2 font-medium">Localidad</th>
                <th className="px-2 py-2 font-medium">Web</th>
                <th className="px-2 py-2 font-medium text-right">Cont.</th>
                <th className="px-2 py-2 font-medium">Messages</th>
                <th className="px-2 py-2 font-medium">Research</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-2 py-6 text-center text-muted-foreground">
                    Sin empresas que coincidan con los filtros.
                  </td>
                </tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-2 py-2 font-mono text-xs">{r.nif}</td>
                  <td className="px-2 py-2">
                    <Link
                      href={`/pipeline/${r.id}`}
                      className="font-medium underline-offset-4 hover:underline"
                    >
                      {r.nombre}
                    </Link>
                    {r.ia_fit_reason && (
                      <p className="text-xs text-muted-foreground line-clamp-1">
                        {r.ia_fit_reason}
                      </p>
                    )}
                  </td>
                  <td className="px-2 py-2">{r.tier ?? "—"}</td>
                  <td className="px-2 py-2">{r.ia_fit ?? "—"}</td>
                  <td className="px-2 py-2 text-xs">{r.localidad ?? "—"}</td>
                  <td className="px-2 py-2 text-xs">
                    {r.web ? (
                      <a
                        href={r.web.startsWith("http") ? r.web : `https://${r.web}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline-offset-4 hover:underline"
                      >
                        {r.web.replace(/^https?:\/\//, "").slice(0, 30)}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-2 py-2 text-right tabular-nums">
                    {contactsCounts[r.id] ?? 0}
                  </td>
                  <td className="px-2 py-2 text-xs font-mono">
                    {statusSummary(messagesCountsByStatus[r.id])}
                  </td>
                  <td className="px-2 py-2 text-xs">{formatDate(r.research_done_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
        <p>
          Página {page} de {totalPages} · {total} empresas total
        </p>
        <div className="flex items-center gap-2">
          {page > 1 && (
            <Link
              href={buildHref(params, { page: String(page - 1) })}
              className="underline-offset-4 hover:underline"
            >
              ← anterior
            </Link>
          )}
          {page < totalPages && (
            <Link
              href={buildHref(params, { page: String(page + 1) })}
              className="underline-offset-4 hover:underline"
            >
              siguiente →
            </Link>
          )}
        </div>
      </div>
      <Separator />
      <p className="text-xs text-muted-foreground">
        Read-only en Sprint 4 paso 6. Click en una empresa para ver el dossier
        completo, contacts y messages.
      </p>
    </div>
  );
}
