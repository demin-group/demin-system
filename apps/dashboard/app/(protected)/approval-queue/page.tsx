import { createAdminClient } from "@/lib/supabase/admin";
import { hasRealReply, loadThreadsByContact } from "@/lib/conversation";

import { ApprovalQueueContent, type DraftItem } from "./approval-queue-content";

export const metadata = { title: "Approval Queue — DEMIN" };
export const dynamic = "force-dynamic";

async function loadDrafts(): Promise<DraftItem[]> {
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("messages")
    .select(
      `
        id, subject, body, step_index, angle, research_snapshot,
        created_at, generation_cost_usd,
        contacts (
          id, email, email_type, email_priority, nombre, cargo,
          companies (
            id, nif, nombre, tier, web, ia_fit, ia_fit_reason
          )
        )
      `,
    )
    .eq("status", "drafted")
    .order("created_at", { ascending: true });

  if (error) {
    throw new Error(`load drafts fallo: ${error.message}`);
  }

  const items: DraftItem[] = [];
  for (const row of data ?? []) {
    // El cliente PostgREST a veces devuelve la relacion como array, a veces
    // como objeto unico. Normalizamos a single object para joins 1:1.
    const ct = Array.isArray(row.contacts) ? row.contacts[0] : row.contacts;
    if (!ct) continue;
    const co = Array.isArray(ct.companies) ? ct.companies[0] : ct.companies;
    if (!co) continue;

    items.push({
      id: row.id,
      subject: row.subject ?? "",
      body: row.body ?? "",
      step_index: row.step_index,
      angle: row.angle,
      created_at: row.created_at,
      generation_cost_usd: row.generation_cost_usd,
      failed_validations:
        (row.research_snapshot as Record<string, unknown> | null)?.[
          "_failed_validations"
        ] as string[] | undefined,
      contact: {
        id: ct.id,
        email: ct.email,
        email_type: ct.email_type,
        email_priority: ct.email_priority,
        nombre: ct.nombre,
        cargo: ct.cargo,
      },
      company: {
        id: co.id,
        nif: co.nif,
        nombre: co.nombre,
        tier: co.tier,
        web: co.web,
        ia_fit: co.ia_fit,
        ia_fit_reason: co.ia_fit_reason,
      },
      // Se rellenan abajo con el hilo del contacto (Caso A/B).
      thread: [],
      hasReplied: false,
    });
  }

  // Caso A vs B: cargamos el hilo (correos enviados + respuestas) de cada
  // contacto. Si ya contestó -> aviso + conversación completa. Si NO contestó
  // pero hay correos previos (es un follow-up) -> mostramos lo ya enviado como
  // contexto. Aperturas (contacto virgen) -> hilo vacío -> nada que mostrar.
  const threadMap = await loadThreadsByContact(items.map((i) => i.contact.id));
  for (const it of items) {
    it.thread = threadMap.get(it.contact.id) ?? [];
    it.hasReplied = hasRealReply(it.thread);
  }
  return items;
}

export default async function ApprovalQueuePage() {
  const drafts = await loadDrafts();
  return <ApprovalQueueContent initialDrafts={drafts} />;
}
