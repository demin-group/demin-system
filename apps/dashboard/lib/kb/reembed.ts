import { createAdminClient } from "@/lib/supabase/admin";
import { chunkText } from "./chunker";
import { embedTexts } from "./voyage";

/**
 * Re-embed inline de un kb_document.
 *
 * Pipeline atomico desde la perspectiva de la UI:
 *   1) DELETE chunks viejos del doc.
 *   2) chunkText(contenido).
 *   3) Voyage embed batch (input_type="document").
 *   4) INSERT bulk de chunks nuevos con embedding.
 *   5) UPDATE kb_documents.embeddings_updated_at = now().
 *
 * Si algo falla entre 1 y 5, el doc queda con embeddings_updated_at sin
 * actualizar y kb_chunks puede quedar parcial. El siguiente save (o un
 * boton "reembedar de nuevo") regenera todo. NO se hace transaccion porque
 * Supabase JS no expone BEGIN/COMMIT manual; el coste de inconsistencia
 * temporal es bajo (solo afecta retrieval del proximo prompt) y la
 * recuperacion es 1 click.
 *
 * Replica funcional del Python `apps/workers/kb/embed_documents.py` para
 * el caso single-doc, sin la cola de jobs (no hay worker daemon en el
 * stack del dashboard — ver decision Sprint 1 paso 4).
 */

export type ReembedResult = {
  documentId: string;
  nChunks: number;
  elapsedMs: number;
  embeddingsUpdatedAt: string;
};

function vectorLiteral(vec: number[]): string {
  return `[${vec.join(",")}]`;
}

export async function reembedDocument(
  documentId: string,
  contenido: string,
): Promise<ReembedResult> {
  const started = Date.now();
  const admin = createAdminClient();

  // 1. Borrar chunks viejos.
  const del = await admin
    .from("kb_chunks")
    .delete()
    .eq("document_id", documentId);
  if (del.error) {
    throw new Error(`DELETE kb_chunks fallo: ${del.error.message}`);
  }

  // 2. Chunkear.
  const chunks = chunkText(contenido);

  // 3+4+5. Si el doc esta vacio, marcamos timestamp pero no insertamos.
  if (chunks.length === 0) {
    const upd = await admin
      .from("kb_documents")
      .update({ embeddings_updated_at: new Date().toISOString() })
      .eq("id", documentId)
      .select("embeddings_updated_at")
      .single();
    if (upd.error || !upd.data) {
      throw new Error(`UPDATE kb_documents fallo: ${upd.error?.message ?? "no row"}`);
    }
    return {
      documentId,
      nChunks: 0,
      elapsedMs: Date.now() - started,
      embeddingsUpdatedAt: upd.data.embeddings_updated_at as string,
    };
  }

  // 3. Embeds (un unico batch — Voyage admite hasta 128 textos por llamada).
  const vectors = await embedTexts(chunks, "document");

  // 4. INSERT bulk. embedding va como literal text '[v1,v2,...]' — pgvector
  //    castea automaticamente al tipo vector(1024) de la columna.
  const rows = chunks.map((contenidoChunk, idx) => ({
    document_id: documentId,
    chunk_index: idx,
    contenido: contenidoChunk,
    embedding: vectorLiteral(vectors[idx]),
  }));
  const ins = await admin.from("kb_chunks").insert(rows);
  if (ins.error) {
    throw new Error(`INSERT kb_chunks fallo: ${ins.error.message}`);
  }

  // 5. Marcar timestamp.
  const upd = await admin
    .from("kb_documents")
    .update({ embeddings_updated_at: new Date().toISOString() })
    .eq("id", documentId)
    .select("embeddings_updated_at")
    .single();
  if (upd.error || !upd.data) {
    throw new Error(`UPDATE kb_documents fallo: ${upd.error?.message ?? "no row"}`);
  }

  return {
    documentId,
    nChunks: chunks.length,
    elapsedMs: Date.now() - started,
    embeddingsUpdatedAt: upd.data.embeddings_updated_at as string,
  };
}
