import { createAdminClient } from "@/lib/supabase/admin";

/**
 * Una entrada del hilo de conversacion con un prospecto.
 *
 * El "hilo" no existe como tabla: se reconstruye combinando messages SALIENTES
 * (status sent/bounced) y replies ENTRANTES de un mismo contact_id, ordenados
 * cronologicamente. No hay thread_id; se agrupa por contacto (1 contacto = 1
 * hilo, valido para este negocio).
 *
 * Tipo plano y serializable: puede viajar de un Server Component al cliente como
 * prop sin arrastrar nada de BD (los consumidores client usan `import type`).
 */
export type ThreadEntry = {
  id: string;
  direction: "out" | "in";
  ts: string;
  subject: string | null;
  body: string | null;
  // Solo salientes (direction === "out"):
  angle: string | null;
  step_index: number | null;
  status: string | null;
  // Solo entrantes (direction === "in"):
  category: string | null;
  is_optout: boolean;
};

// Categorias entrantes que NO cuentan como "el prospecto contesto de verdad":
// un rebote (DSN) o un autorespondedor de fuera de oficina no son engagement.
const SOFT_REPLY_CATEGORIES: ReadonlySet<string> = new Set([
  "rebote",
  "fuera_oficina",
]);

/**
 * Carga el hilo completo (salientes + entrantes ordenados) para un conjunto de
 * contactos. Dos consultas `.in()` (una a messages, otra a replies) -> coste
 * constante en round-trips independientemente del numero de contactos.
 */
export async function loadThreadsByContact(
  contactIds: string[],
): Promise<Map<string, ThreadEntry[]>> {
  const map = new Map<string, ThreadEntry[]>();
  const uniq = Array.from(new Set(contactIds.filter(Boolean)));
  if (uniq.length === 0) return map;
  for (const cid of uniq) map.set(cid, []);

  const admin = createAdminClient();

  const { data: outRows, error: outErr } = await admin
    .from("messages")
    .select(
      "id, contact_id, subject, body, angle, step_index, status, sent_at, created_at",
    )
    .in("contact_id", uniq)
    .in("status", ["sent", "bounced"]);
  if (outErr) throw new Error(`load hilo (salientes) fallo: ${outErr.message}`);

  const { data: inRows, error: inErr } = await admin
    .from("replies")
    .select(
      "id, contact_id, raw_subject, raw_body, category, is_explicit_optout, received_at",
    )
    .in("contact_id", uniq);
  if (inErr) throw new Error(`load hilo (entrantes) fallo: ${inErr.message}`);

  for (const m of (outRows ?? []) as Array<Record<string, unknown>>) {
    const arr = map.get(m.contact_id as string);
    if (!arr) continue;
    arr.push({
      id: m.id as string,
      direction: "out",
      ts: (m.sent_at as string | null) ?? (m.created_at as string),
      subject: (m.subject as string | null) ?? null,
      body: (m.body as string | null) ?? null,
      angle: (m.angle as string | null) ?? null,
      step_index: (m.step_index as number | null) ?? null,
      status: (m.status as string | null) ?? null,
      category: null,
      is_optout: false,
    });
  }
  for (const r of (inRows ?? []) as Array<Record<string, unknown>>) {
    const arr = map.get(r.contact_id as string);
    if (!arr) continue;
    arr.push({
      id: r.id as string,
      direction: "in",
      ts: r.received_at as string,
      subject: (r.raw_subject as string | null) ?? null,
      body: (r.raw_body as string | null) ?? null,
      angle: null,
      step_index: null,
      status: null,
      category: (r.category as string | null) ?? null,
      is_optout: Boolean(r.is_explicit_optout),
    });
  }
  for (const arr of map.values()) {
    arr.sort((a, b) => new Date(a.ts).getTime() - new Date(b.ts).getTime());
  }
  return map;
}

/**
 * True si el contacto contesto de verdad: hay alguna entrada entrante que no sea
 * rebote ni fuera de oficina. Una respuesta sin clasificar (category null) SI
 * cuenta -> es un inbound real aunque aun no este etiquetado.
 */
export function hasRealReply(thread: ThreadEntry[]): boolean {
  return thread.some(
    (e) => e.direction === "in" && !SOFT_REPLY_CATEGORIES.has(e.category ?? ""),
  );
}
