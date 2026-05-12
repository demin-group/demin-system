"use server";

import { revalidatePath } from "next/cache";

import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Pausa de emergencia: UPDATE mailboxes status='paused' para todos los active.
 * INSERT event 'mailbox_paused' con reason='manual_emergency' para auditoria.
 *
 * Apendice A regla 6: la auto-pausa no se desactiva sin OK humano. Esta accion
 * es la palanca humana inversa -- pausa manual cuando el operador detecta
 * algo malo antes de que auto_pause.py lo capture.
 */
export async function emergencyPauseAction(): Promise<
  { ok: true; paused: number } | { ok: false; error: string }
> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user?.email) {
    return { ok: false, error: "Sin sesion" };
  }

  const admin = createAdminClient();
  const { data: active, error: selErr } = await admin
    .from("mailboxes")
    .select("id, email")
    .eq("status", "active");
  if (selErr) {
    return { ok: false, error: selErr.message };
  }
  if (!active || active.length === 0) {
    return { ok: true, paused: 0 };
  }

  // Pause all active
  const { error: updErr } = await admin
    .from("mailboxes")
    .update({ status: "paused", pause_reason: "manual_emergency" })
    .eq("status", "active");
  if (updErr) {
    return { ok: false, error: updErr.message };
  }

  // Insert event per mailbox pausado
  const events = active.map((mb) => ({
    type: "mailbox_paused",
    payload: {
      mailbox_id: mb.id,
      mailbox_email: mb.email,
      reason: "manual_emergency",
      paused_by: user.email,
    },
  }));
  const { error: evErr } = await admin.from("events").insert(events);
  if (evErr) {
    // Log pero no abortamos -- la pausa ya esta aplicada
    console.error("emergency_pause: event insert fallo", evErr);
  }

  revalidatePath("/settings");
  return { ok: true, paused: active.length };
}

/**
 * Reanudar todos los mailbox paused. Apendice A regla 6: requiere accion
 * humana explicita (este boton).
 */
export async function resumeAllAction(): Promise<
  { ok: true; resumed: number } | { ok: false; error: string }
> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user?.email) {
    return { ok: false, error: "Sin sesion" };
  }

  const admin = createAdminClient();
  const { data: paused, error: selErr } = await admin
    .from("mailboxes")
    .select("id, email")
    .eq("status", "paused");
  if (selErr) {
    return { ok: false, error: selErr.message };
  }
  if (!paused || paused.length === 0) {
    return { ok: true, resumed: 0 };
  }

  const { error: updErr } = await admin
    .from("mailboxes")
    .update({ status: "active", pause_reason: null })
    .eq("status", "paused");
  if (updErr) {
    return { ok: false, error: updErr.message };
  }

  const events = paused.map((mb) => ({
    type: "mailbox_resumed",
    payload: {
      mailbox_id: mb.id,
      mailbox_email: mb.email,
      resumed_by: user.email,
    },
  }));
  const { error: evErr } = await admin.from("events").insert(events);
  if (evErr) {
    console.error("resume_all: event insert fallo", evErr);
  }

  revalidatePath("/settings");
  return { ok: true, resumed: paused.length };
}
