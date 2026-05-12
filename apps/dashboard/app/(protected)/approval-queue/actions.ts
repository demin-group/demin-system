"use server";

import { revalidatePath } from "next/cache";

import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Approve message HITL.
 *
 * UPDATE messages SET status='approved', approved_by=user.email,
 * approved_at=now(). Si `edited` viene, tambien UPDATE subject/body + edited=true.
 *
 * Llamadora: client component approval-queue-content.tsx.
 */
export async function approveMessageAction(
  messageId: string,
  edited?: { subject: string; body: string },
): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user?.email) {
    return { ok: false, error: "Sin sesion" };
  }

  const admin = createAdminClient();
  const update: Record<string, unknown> = {
    status: "approved",
    approved_by: user.email,
    approved_at: new Date().toISOString(),
  };
  if (edited) {
    update.subject = edited.subject;
    update.body = edited.body;
    update.edited = true;
  }
  const { error } = await admin
    .from("messages")
    .update(update)
    .eq("id", messageId)
    .eq("status", "drafted"); // guard: solo aprobar lo que sigue siendo draft
  if (error) {
    return { ok: false, error: error.message };
  }
  revalidatePath("/approval-queue");
  return { ok: true };
}

/**
 * Reject + opt-out permanente del contact (Apendice A regla 2).
 *
 * UPDATE messages SET status='cancelled' + _cancelled_reason='hitl_rejected'.
 * UPDATE contacts SET is_optout=true, optout_at=now(), optout_reason='hitl_rejected'.
 *
 * Esto detiene cualquier follow-up futuro para el contact (filtros en
 * generate_draft.fetch_pending_contacts y follow_ups.fetch_followup_candidates).
 */
export async function rejectAndOptoutAction(
  messageId: string,
  contactId: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user?.email) {
    return { ok: false, error: "Sin sesion" };
  }

  const admin = createAdminClient();

  // Cancela el message con razon en research_snapshot
  const msgRow = await admin
    .from("messages")
    .select("research_snapshot, status")
    .eq("id", messageId)
    .single();
  if (msgRow.error) {
    return { ok: false, error: msgRow.error.message };
  }
  const snapshot = {
    ...(msgRow.data?.research_snapshot ?? {}),
    _cancelled_reason: "hitl_rejected",
    _cancelled_from_status: msgRow.data?.status ?? "drafted",
  };
  const updMsg = await admin
    .from("messages")
    .update({ status: "cancelled", research_snapshot: snapshot })
    .eq("id", messageId);
  if (updMsg.error) {
    return { ok: false, error: updMsg.error.message };
  }

  // Opt-out del contact (permanente, Apendice A regla 2)
  const updContact = await admin
    .from("contacts")
    .update({
      is_optout: true,
      optout_at: new Date().toISOString(),
      optout_reason: "hitl_rejected",
    })
    .eq("id", contactId);
  if (updContact.error) {
    return { ok: false, error: updContact.error.message };
  }

  revalidatePath("/approval-queue");
  return { ok: true };
}
