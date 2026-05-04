import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { reembedDocument } from "@/lib/kb/reembed";

export const runtime = "nodejs";
// Voyage 1 batch ~1-3s + insert + reembed; con free tier 3 RPM podemos tocar
// hasta ~25s si la ventana esta cerrada. 60s da margen sin desbordar el limite
// de Vercel Hobby Node runtime.
export const maxDuration = 60;

const VALID_CATEGORIES = [
  "servicios",
  "icp",
  "objeciones",
  "casos_exito",
  "tono",
  "diferenciador",
  "correos_gonzalo",
  "otro",
] as const;

type Category = (typeof VALID_CATEGORIES)[number];

async function requireAuth() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) {
    return { user: null, response: NextResponse.json({ error: "no autenticado" }, { status: 401 }) };
  }
  return { user, response: null };
}

/** GET /api/kb — lista de documentos con conteo de chunks por doc. */
export async function GET() {
  const { response } = await requireAuth();
  if (response) return response;

  const admin = createAdminClient();
  // Lista chica (6-50 docs en el KB v1). Dos queries simples: docs + chunks
  // de esos docs. Sin RPC ni vista materializada — overkill al volumen.
  const docs = await admin
    .from("kb_documents")
    .select(
      "id, category, titulo, contenido, is_active, created_by, created_at, updated_at, embeddings_updated_at",
    )
    .order("category", { ascending: true })
    .order("titulo", { ascending: true });
  if (docs.error) {
    return NextResponse.json({ error: docs.error.message }, { status: 500 });
  }

  const ids = (docs.data ?? []).map((d) => d.id);
  const counts: Record<string, number> = {};
  if (ids.length > 0) {
    const ch = await admin
      .from("kb_chunks")
      .select("document_id")
      .in("document_id", ids);
    if (ch.error) {
      return NextResponse.json({ error: ch.error.message }, { status: 500 });
    }
    for (const r of ch.data ?? []) {
      counts[r.document_id] = (counts[r.document_id] ?? 0) + 1;
    }
  }

  const merged = (docs.data ?? []).map((d) => ({
    ...d,
    n_chunks: counts[d.id] ?? 0,
  }));
  return NextResponse.json({ documents: merged });
}

/** POST /api/kb — crea un documento y lo reembeba inline. */
export async function POST(req: Request) {
  const { user, response } = await requireAuth();
  if (response) return response;

  let body: { category?: string; titulo?: string; contenido?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON invalido" }, { status: 400 });
  }

  const { category, titulo, contenido } = body;
  if (!category || !titulo || contenido === undefined) {
    return NextResponse.json(
      { error: "campos requeridos: category, titulo, contenido" },
      { status: 400 },
    );
  }
  if (!VALID_CATEGORIES.includes(category as Category)) {
    return NextResponse.json(
      { error: `category invalida. Validas: ${VALID_CATEGORIES.join(", ")}` },
      { status: 400 },
    );
  }
  if (!titulo.trim()) {
    return NextResponse.json({ error: "titulo no puede ser vacio" }, { status: 400 });
  }

  const admin = createAdminClient();
  const insert = await admin
    .from("kb_documents")
    .insert({
      category,
      titulo: titulo.trim(),
      contenido,
      is_active: true,
      created_by: user!.email ?? "dashboard",
    })
    .select("id")
    .single();
  if (insert.error || !insert.data) {
    return NextResponse.json(
      { error: insert.error?.message ?? "INSERT fallo" },
      { status: 500 },
    );
  }

  try {
    const result = await reembedDocument(insert.data.id, contenido);
    return NextResponse.json({ id: insert.data.id, reembed: result }, { status: 201 });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    // El doc se creo. El reembed fallo. La UI lo veria como "0 chunks" y
    // el usuario puede reintentar pulsando guardar de nuevo.
    return NextResponse.json(
      {
        id: insert.data.id,
        reembed: null,
        error: `documento creado pero reembed fallo: ${msg}`,
      },
      { status: 207 },
    );
  }
}
