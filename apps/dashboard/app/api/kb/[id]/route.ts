import { NextResponse } from "next/server";

import { createClient } from "@/lib/supabase/server";
import { createAdminClient } from "@/lib/supabase/admin";
import { reembedDocument } from "@/lib/kb/reembed";

export const runtime = "nodejs";
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

/** GET /api/kb/:id — devuelve un documento. */
export async function GET(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { response } = await requireAuth();
  if (response) return response;

  const { id } = await ctx.params;
  const admin = createAdminClient();
  const { data, error } = await admin
    .from("kb_documents")
    .select("*")
    .eq("id", id)
    .maybeSingle();
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  if (!data) {
    return NextResponse.json({ error: "no existe" }, { status: 404 });
  }
  return NextResponse.json(data);
}

/** PATCH /api/kb/:id — actualiza el doc y reembeba inline. */
export async function PATCH(
  req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { response } = await requireAuth();
  if (response) return response;

  const { id } = await ctx.params;

  let body: { category?: string; titulo?: string; contenido?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON invalido" }, { status: 400 });
  }

  const update: Record<string, unknown> = {};
  if (body.category !== undefined) {
    if (!VALID_CATEGORIES.includes(body.category as Category)) {
      return NextResponse.json(
        { error: `category invalida. Validas: ${VALID_CATEGORIES.join(", ")}` },
        { status: 400 },
      );
    }
    update.category = body.category;
  }
  if (body.titulo !== undefined) {
    if (!body.titulo.trim()) {
      return NextResponse.json({ error: "titulo no puede ser vacio" }, { status: 400 });
    }
    update.titulo = body.titulo.trim();
  }
  if (body.contenido !== undefined) {
    update.contenido = body.contenido;
  }

  if (Object.keys(update).length === 0) {
    return NextResponse.json({ error: "nada que actualizar" }, { status: 400 });
  }

  const admin = createAdminClient();
  const upd = await admin
    .from("kb_documents")
    .update(update)
    .eq("id", id)
    .select("id, contenido")
    .single();
  if (upd.error || !upd.data) {
    return NextResponse.json(
      { error: upd.error?.message ?? "UPDATE fallo" },
      { status: 500 },
    );
  }

  // Reembed solo si cambio el contenido. Si solo cambio el titulo o
  // categoria, los chunks siguen siendo validos (no afectan retrieval).
  if (body.contenido === undefined) {
    return NextResponse.json({ id: upd.data.id, reembed: null });
  }

  try {
    const result = await reembedDocument(upd.data.id, upd.data.contenido as string);
    return NextResponse.json({ id: upd.data.id, reembed: result });
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    return NextResponse.json(
      {
        id: upd.data.id,
        reembed: null,
        error: `actualizado pero reembed fallo: ${msg}`,
      },
      { status: 207 },
    );
  }
}

/** DELETE /api/kb/:id — elimina el doc; los chunks caen via CASCADE. */
export async function DELETE(
  _req: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const { response } = await requireAuth();
  if (response) return response;

  const { id } = await ctx.params;
  const admin = createAdminClient();
  const { error } = await admin.from("kb_documents").delete().eq("id", id);
  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
  return NextResponse.json({ ok: true });
}
