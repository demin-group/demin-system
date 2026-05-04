import { createAdminClient } from "@/lib/supabase/admin";
import { KbContent, type KbDoc } from "./kb-content";

export const metadata = { title: "KB — DEMIN" };
export const dynamic = "force-dynamic";

async function loadDocs(): Promise<KbDoc[]> {
  const admin = createAdminClient();
  const docs = await admin
    .from("kb_documents")
    .select(
      "id, category, titulo, contenido, is_active, created_by, created_at, updated_at, embeddings_updated_at",
    )
    .order("category", { ascending: true })
    .order("titulo", { ascending: true });
  if (docs.error) {
    throw new Error(`load kb_documents fallo: ${docs.error.message}`);
  }
  const ids = (docs.data ?? []).map((d) => d.id);
  const counts: Record<string, number> = {};
  if (ids.length > 0) {
    const ch = await admin
      .from("kb_chunks")
      .select("document_id")
      .in("document_id", ids);
    if (!ch.error) {
      for (const r of ch.data ?? []) {
        counts[r.document_id] = (counts[r.document_id] ?? 0) + 1;
      }
    }
  }
  return (docs.data ?? []).map((d) => ({
    ...d,
    n_chunks: counts[d.id] ?? 0,
  })) as KbDoc[];
}

export default async function KbPage() {
  const docs = await loadDocs();
  return <KbContent initialDocs={docs} />;
}
