import { NextResponse } from "next/server";
import { z } from "zod";
import { getServerSupabase } from "@/lib/supabase";
import { sendLeadNotification } from "@/lib/resend";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const phoneRegex = /^[+0-9\s().-]{6,20}$/;

const ContactSchema = z.object({
  nombre: z.string().trim().min(2, "Nombre demasiado corto").max(120),
  empresa: z.string().trim().max(160).optional().default(""),
  telefono: z
    .string()
    .trim()
    .max(40)
    .optional()
    .default("")
    .refine((v) => v === "" || phoneRegex.test(v), { message: "Teléfono no válido" }),
  email: z.string().trim().email("Email no válido").max(160),
  mensaje: z.string().trim().min(10, "Mensaje demasiado corto").max(4000),
  website: z.string().optional().default(""),
});

export async function POST(req: Request) {
  let raw: unknown;
  try {
    raw = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "JSON inválido" }, { status: 400 });
  }

  const parsed = ContactSchema.safeParse(raw);
  if (!parsed.success) {
    const firstIssue = parsed.error.issues[0];
    return NextResponse.json(
      { ok: false, error: firstIssue?.message ?? "Datos no válidos" },
      { status: 400 },
    );
  }

  const data = parsed.data;

  if (data.website.trim() !== "") {
    return NextResponse.json({ ok: true });
  }

  try {
    const supabase = getServerSupabase();
    const { error } = await supabase.from("web_leads").insert({
      nombre: data.nombre,
      empresa: data.empresa || null,
      telefono: data.telefono || null,
      email: data.email,
      mensaje: data.mensaje,
      origen: "web_form",
      status: "nuevo",
    });

    if (error) {
      console.error("[/api/contact] Supabase insert error:", error.message);
      return NextResponse.json(
        { ok: false, error: "No hemos podido guardar el mensaje. Inténtalo más tarde." },
        { status: 500 },
      );
    }
  } catch (err) {
    console.error("[/api/contact] Unexpected error:", err);
    return NextResponse.json(
      { ok: false, error: "Error inesperado. Inténtalo más tarde." },
      { status: 500 },
    );
  }

  try {
    await sendLeadNotification({
      nombre: data.nombre,
      empresa: data.empresa,
      telefono: data.telefono,
      email: data.email,
      mensaje: data.mensaje,
    });
  } catch (err) {
    console.error("[/api/contact] sendLeadNotification failed:", err);
  }

  return NextResponse.json({ ok: true });
}
