/**
 * Smoke E2E del KB editor — valida el pipeline de reembed inline contra
 * demin-dev SIN pasar por HTTP ni por el flow de magic link.
 *
 * Uso:
 *   cd apps/dashboard
 *   npx tsx scripts/smoke_kb_e2e.ts
 *
 * Lee `.env.local` (con VOYAGE_API_KEY + Supabase service role) y ejecuta
 * los 6 pasos del E2E pedido en el prompt Sprint 1 paso 4:
 *   1) crear doc tipo "otro"
 *   2) reembedar (corto -> N chunks pequenos)
 *   3) editar contenido (largo -> M chunks, M > N)
 *   4) reembedar (deberia regenerar y dar M chunks)
 *   5) borrar doc
 *   6) verificar que kb_chunks asociados desaparecen via CASCADE
 *
 * Imprime counts en cada paso. ENV se hardcodea via .env.local del
 * dashboard (apunta a demin-dev por configuracion).
 */
import { config as loadEnv } from "dotenv";
import { resolve } from "node:path";
import { createClient } from "@supabase/supabase-js";

// Cargar .env.local del dashboard (donde estan las creds de dev).
loadEnv({ path: resolve(__dirname, "..", ".env.local") });

import { reembedDocument } from "../lib/kb/reembed";

// SupabaseClient generic drifted entre @supabase/supabase-js versiones (Sprint 1
// vs hoy). Acepto cualquier shape via `any` aqui — el smoke E2E solo lo usa
// para SELECT con count head sobre tablas conocidas; sin type-safety perdida
// operativa para un script de prueba.
// deno-lint-ignore no-explicit-any
async function countChunks(
  admin: any,  // eslint-disable-line @typescript-eslint/no-explicit-any
  docId: string,
): Promise<number> {
  const r = await admin
    .from("kb_chunks")
    .select("id", { count: "exact", head: true })
    .eq("document_id", docId);
  if (r.error) throw new Error(`count chunks fallo: ${r.error.message}`);
  return r.count ?? 0;
}

async function main(): Promise<number> {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    console.error("Falta NEXT_PUBLIC_SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY en .env.local");
    return 1;
  }
  const admin = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  console.log("=".repeat(64));
  console.log("smoke_kb_e2e — pipeline reembed contra demin-dev");
  console.log("=".repeat(64));

  // Paso 1: crear doc
  const cortoText = "# SMOKE E2E\n\nTexto inicial corto del doc de prueba para Sprint 1 paso 4. Solo deberia generar 1 chunk.";
  const ins = await admin
    .from("kb_documents")
    .insert({
      category: "otro",
      titulo: "SMOKE E2E — sprint 1 paso 4",
      contenido: cortoText,
      is_active: true,
      created_by: "dashboard-smoke-e2e",
    })
    .select("id")
    .single();
  if (ins.error || !ins.data) throw new Error(`INSERT fallo: ${ins.error?.message}`);
  const docId = ins.data.id as string;
  console.log(`[1] doc creado id=${docId}`);

  // Paso 2: reembedar
  const r1 = await reembedDocument(docId, cortoText);
  const c1 = await countChunks(admin, docId);
  console.log(`[2] reembed inicial: nChunks=${r1.nChunks}, count en BD=${c1}, elapsed=${r1.elapsedMs}ms`);
  if (c1 !== r1.nChunks) throw new Error(`mismatch: BD ${c1} vs reembed ${r1.nChunks}`);

  // Paso 3: editar a contenido largo
  const largoText = "# SMOKE E2E - largo\n\n" + Array.from({ length: 30 }, (_, i) =>
    `## Seccion ${i + 1}\n\nContenido sustancial repetido para generar mas chunks. ` +
    "Lorem ipsum, Madrid, Chamberi, vaciado integral, demolicion, presupuesto, plazos, ".repeat(5)
  ).join("\n\n");
  const upd = await admin
    .from("kb_documents")
    .update({ contenido: largoText })
    .eq("id", docId);
  if (upd.error) throw new Error(`UPDATE fallo: ${upd.error.message}`);
  console.log(`[3] doc editado, ${largoText.length} chars`);

  // Paso 4: reembedar el contenido nuevo
  const r2 = await reembedDocument(docId, largoText);
  const c2 = await countChunks(admin, docId);
  console.log(`[4] reembed largo:  nChunks=${r2.nChunks}, count en BD=${c2}, elapsed=${r2.elapsedMs}ms`);
  if (c2 !== r2.nChunks) throw new Error(`mismatch: BD ${c2} vs reembed ${r2.nChunks}`);
  if (r2.nChunks <= r1.nChunks) {
    throw new Error(`esperaba mas chunks tras editar a largo (antes ${r1.nChunks}, ahora ${r2.nChunks})`);
  }

  // Paso 5: borrar doc
  const del = await admin.from("kb_documents").delete().eq("id", docId);
  if (del.error) throw new Error(`DELETE fallo: ${del.error.message}`);
  console.log(`[5] doc eliminado`);

  // Paso 6: verificar CASCADE
  const c3 = await countChunks(admin, docId);
  console.log(`[6] chunks tras borrar: ${c3} (esperado 0 via CASCADE)`);
  if (c3 !== 0) throw new Error(`CASCADE fallo: ${c3} chunks huerfanos`);

  console.log("=".repeat(64));
  console.log("smoke_kb_e2e OK");
  return 0;
}

main()
  .then((code) => process.exit(code))
  .catch((err) => {
    console.error("FALLO:", err);
    process.exit(1);
  });
