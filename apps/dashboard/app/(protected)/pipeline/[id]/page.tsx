import Link from "next/link";
import { notFound } from "next/navigation";

import { createAdminClient } from "@/lib/supabase/admin";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

export const metadata = { title: "Detalle empresa — DEMIN" };
export const dynamic = "force-dynamic";

type CompanyFull = {
  id: string;
  nif: string;
  nombre: string;
  localidad: string | null;
  descripcion: string | null;
  web: string | null;
  rev_y0_keur: number | null;
  rev_y1_keur: number | null;
  rev_growth_pct: number | null;
  tier: string | null;
  ia_fit: string | null;
  ia_fit_reason: string | null;
  research_done_at: string | null;
  research_data: Record<string, unknown> | null;
};

type ContactRow = {
  id: string;
  email: string;
  email_verified: boolean | null;
  email_source: string | null;
  email_type: string | null;
  email_priority: number | null;
  nombre: string | null;
  cargo: string | null;
  is_primary: boolean | null;
  is_optout: boolean | null;
  optout_reason: string | null;
};

type MessageRow = {
  id: string;
  contact_id: string;
  step_index: number;
  angle: string;
  status: string;
  subject: string | null;
  body: string | null;
  approved_at: string | null;
  sent_at: string | null;
  edited: boolean | null;
  generation_cost_usd: number | null;
  created_at: string;
};

async function loadCompanyDetail(id: string) {
  const admin = createAdminClient();
  const c = await admin
    .from("companies")
    .select(
      "id, nif, nombre, localidad, descripcion, web, rev_y0_keur, rev_y1_keur, rev_growth_pct, tier, ia_fit, ia_fit_reason, research_done_at, research_data",
    )
    .eq("id", id)
    .maybeSingle();
  if (c.error) {
    throw new Error(`load company fallo: ${c.error.message}`);
  }
  if (!c.data) return null;

  const ct = await admin
    .from("contacts")
    .select(
      "id, email, email_verified, email_source, email_type, email_priority, nombre, cargo, is_primary, is_optout, optout_reason",
    )
    .eq("company_id", id)
    .order("email_priority", { ascending: true });
  if (ct.error) {
    throw new Error(`load contacts fallo: ${ct.error.message}`);
  }
  const contacts = (ct.data ?? []) as ContactRow[];
  const contactIds = contacts.map((x) => x.id);

  let messages: MessageRow[] = [];
  if (contactIds.length > 0) {
    const m = await admin
      .from("messages")
      .select(
        "id, contact_id, step_index, angle, status, subject, body, approved_at, sent_at, edited, generation_cost_usd, created_at",
      )
      .in("contact_id", contactIds)
      .order("created_at", { ascending: false });
    if (m.error) {
      throw new Error(`load messages fallo: ${m.error.message}`);
    }
    messages = (m.data ?? []) as MessageRow[];
  }
  return { company: c.data as CompanyFull, contacts, messages };
}

function fmtDate(s: string | null): string {
  if (!s) return "—";
  return s.replace("T", " ").slice(0, 16);
}

function ResearchBlock({ data }: { data: Record<string, unknown> | null }) {
  if (!data) {
    return <p className="text-sm text-muted-foreground">Sin research todavía.</p>;
  }
  const failed = data["_failed"];
  if (failed) {
    return (
      <div className="space-y-2">
        <p className="text-sm">
          <span className="font-medium text-destructive">Research falló: </span>
          <span className="font-mono text-xs">{String(failed)}</span>
        </p>
        {Boolean(data["reason"]) && (
          <p className="text-xs text-muted-foreground">{String(data["reason"])}</p>
        )}
      </div>
    );
  }
  const get = (k: string) => data[k];
  const personas = (get("personas_extraidas") as Array<Record<string, string>>) ?? [];
  const tipo_obra = (get("tipo_obra_que_hacen") as string[]) ?? [];
  const proyectos = (get("proyectos_recientes") as string[]) ?? [];
  const valores = (get("valores_que_destacan") as string[]) ?? [];
  const hooks = (get("hooks_de_personalizacion") as string[]) ?? [];

  return (
    <div className="space-y-3 text-sm">
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">Tipo de actividad</p>
        <p>{(get("tipo_actividad_concreta") as string) || "—"}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs font-medium uppercase text-muted-foreground">Tamaño</p>
          <p>{(get("tamano_aparente") as string) || "—"}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase text-muted-foreground">Lenguaje</p>
          <p>{(get("lenguaje_que_usan") as string) || "—"}</p>
        </div>
      </div>
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">Tipo de obra</p>
        <p>{tipo_obra.length > 0 ? tipo_obra.join(", ") : "—"}</p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">Proyectos recientes</p>
        {proyectos.length > 0 ? (
          <ul className="list-disc pl-5">
            {proyectos.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        ) : (
          <p>—</p>
        )}
      </div>
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">Valores destacados</p>
        <p>{valores.length > 0 ? valores.join(" · ") : "—"}</p>
      </div>
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">Hooks de personalización</p>
        {hooks.length > 0 ? (
          <ul className="list-disc pl-5">
            {hooks.map((h, i) => (
              <li key={i}>{h}</li>
            ))}
          </ul>
        ) : (
          <p>—</p>
        )}
      </div>
      <div>
        <p className="text-xs font-medium uppercase text-muted-foreground">
          Personas extraídas (cruce con find_contacts T2)
        </p>
        {personas.length > 0 ? (
          <ul className="list-disc pl-5">
            {personas.map((p, i) => (
              <li key={i}>
                <span className="font-medium">{p["nombre"]}</span>
                {p["cargo_si_aparece"] && (
                  <span className="text-muted-foreground"> — {p["cargo_si_aparece"]}</span>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p>—</p>
        )}
      </div>
      {Boolean(get("_warning")) && (
        <p className="text-xs text-amber-700">⚠ {String(get("_warning"))}</p>
      )}
    </div>
  );
}

export default async function CompanyDetailPage(props: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await props.params;
  const data = await loadCompanyDetail(id);
  if (!data) notFound();
  const { company, contacts, messages } = data;

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <Link
          href="/pipeline"
          className="text-xs text-muted-foreground underline-offset-4 hover:underline"
        >
          ← Pipeline
        </Link>
        <h1 className="text-3xl font-semibold tracking-tight">{company.nombre}</h1>
        <p className="text-sm text-muted-foreground">
          NIF {company.nif} · tier {company.tier ?? "—"} · ia_fit {company.ia_fit ?? "—"} ·{" "}
          {company.localidad ?? "—"}
        </p>
        {company.web && (
          <p className="text-sm">
            <a
              href={company.web.startsWith("http") ? company.web : `https://${company.web}`}
              target="_blank"
              rel="noopener noreferrer"
              className="underline-offset-4 hover:underline"
            >
              {company.web}
            </a>
          </p>
        )}
        {company.ia_fit_reason && (
          <p className="text-sm text-muted-foreground">
            <span className="font-medium">Razón ia_fit: </span>
            {company.ia_fit_reason}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Facturación (k€)</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>Y0: {company.rev_y0_keur ?? "—"}</p>
            <p>Y1: {company.rev_y1_keur ?? "—"}</p>
            <p>
              Crecim:{" "}
              {company.rev_growth_pct !== null && company.rev_growth_pct !== undefined
                ? `${company.rev_growth_pct.toFixed(1)}%`
                : "—"}
            </p>
          </CardContent>
        </Card>
        <Card className="md:col-span-2">
          <CardHeader>
            <CardTitle className="text-sm">Descripción SABI</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm whitespace-pre-line">{company.descripcion ?? "—"}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Research (paso 4b)</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-xs text-muted-foreground">
            Última ejecución: {fmtDate(company.research_done_at)}
          </p>
          <Separator className="mb-3" />
          <ResearchBlock data={company.research_data} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Contacts ({contacts.length})</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {contacts.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin contacts todavía.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-2 py-2 font-medium">Email</th>
                  <th className="px-2 py-2 font-medium">Tipo</th>
                  <th className="px-2 py-2 font-medium">Prio</th>
                  <th className="px-2 py-2 font-medium">Nombre</th>
                  <th className="px-2 py-2 font-medium">Cargo</th>
                  <th className="px-2 py-2 font-medium">Verif.</th>
                  <th className="px-2 py-2 font-medium">Source</th>
                  <th className="px-2 py-2 font-medium">Primary</th>
                  <th className="px-2 py-2 font-medium">Opt-out</th>
                </tr>
              </thead>
              <tbody>
                {contacts.map((c) => (
                  <tr key={c.id} className="border-t">
                    <td className="px-2 py-2 font-mono text-xs">{c.email}</td>
                    <td className="px-2 py-2 text-xs">{c.email_type ?? "—"}</td>
                    <td className="px-2 py-2 text-right">{c.email_priority ?? "—"}</td>
                    <td className="px-2 py-2 text-xs">{c.nombre ?? "—"}</td>
                    <td className="px-2 py-2 text-xs">{c.cargo ?? "—"}</td>
                    <td className="px-2 py-2 text-xs">{c.email_verified ? "✓" : "—"}</td>
                    <td className="px-2 py-2 text-xs">{c.email_source ?? "—"}</td>
                    <td className="px-2 py-2 text-xs">{c.is_primary ? "✓" : "—"}</td>
                    <td className="px-2 py-2 text-xs">
                      {c.is_optout ? `✗ ${c.optout_reason ?? ""}` : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Messages ({messages.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">Sin messages todavía.</p>
          ) : (
            <div className="space-y-3">
              {messages.map((m) => (
                <div key={m.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-baseline gap-2 text-xs text-muted-foreground">
                    <span className="font-mono">{m.id.slice(0, 8)}</span>
                    <span>·</span>
                    <span>step {m.step_index} ({m.angle})</span>
                    <span>·</span>
                    <span className="font-medium">{m.status}</span>
                    {m.edited && (
                      <>
                        <span>·</span>
                        <span>edited</span>
                      </>
                    )}
                    {m.approved_at && (
                      <>
                        <span>·</span>
                        <span>approved {fmtDate(m.approved_at)}</span>
                      </>
                    )}
                    {m.sent_at && (
                      <>
                        <span>·</span>
                        <span>sent {fmtDate(m.sent_at)}</span>
                      </>
                    )}
                    {m.generation_cost_usd !== null && m.generation_cost_usd !== undefined && (
                      <>
                        <span>·</span>
                        <span>${m.generation_cost_usd.toFixed(4)}</span>
                      </>
                    )}
                  </div>
                  {m.subject && (
                    <p className="mt-2 text-sm">
                      <span className="font-medium">Asunto: </span>
                      {m.subject}
                    </p>
                  )}
                  {m.body && (
                    <p className="mt-1 text-sm whitespace-pre-line text-muted-foreground">
                      {m.body}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
