"use server";

import { revalidatePath } from "next/cache";

import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

/**
 * Categorias soportadas en `message_revisions.rejection_category`. Espejo del
 * CHECK CONSTRAINT en migration 14.
 */
export const REJECTION_CATEGORIES = [
  "tono",
  "datos_incorrectos",
  "no_icp",
  "longitud",
  "asunto",
  "duplicado_contacto",
  "otro",
] as const;

export type RejectionCategory = (typeof REJECTION_CATEGORIES)[number];

/**
 * Approve message HITL.
 *
 * UPDATE messages SET status='approved', approved_by=user.email,
 * approved_at=now(). Si `edited` viene, antes del UPDATE INSERTa una fila en
 * `message_revisions` con type='edit' capturando body/subject antes/despues
 * (Bloque 7 sesion 2026-05-25 -- aprendizaje HITL).
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

  // Captura revision (edit) antes de tocar messages.
  if (edited) {
    const before = await admin
      .from("messages")
      .select("subject, body")
      .eq("id", messageId)
      .single();
    if (before.error) {
      return { ok: false, error: before.error.message };
    }
    const revInsert = await admin.from("message_revisions").insert({
      message_id: messageId,
      revision_type: "edit",
      subject_before: before.data.subject,
      subject_after: edited.subject,
      body_before: before.data.body,
      body_after: edited.body,
      revised_by: user.email,
    });
    if (revInsert.error) {
      return { ok: false, error: revInsert.error.message };
    }
  }

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
 * Rechazo HITL con captura de categoria + razon (Bloque 7).
 *
 * Flujo:
 * 1. INSERT message_revisions con type='reject', rejection_category,
 *    rejection_reason_text, body_before/subject_before del DB actual.
 * 2. UPDATE messages SET status='cancelled' + research_snapshot._cancelled_reason.
 * 3. Si alsoOptout=true (Apendice A regla 2 -- explicit opt-out):
 *    UPDATE contacts SET is_optout=true, optout_at=now(),
 *    optout_reason=`hitl_${category}`.
 *
 * `alsoOptout` lo decide el operador en el modal: por defecto OFF (cancelar
 * el draft sin excluir el contact -- vale para "tono malo, regenerar"). El
 * UI marca por defecto ON cuando category in {no_icp, duplicado_contacto}.
 */
export async function rejectMessageAction(args: {
  messageId: string;
  contactId: string;
  category: RejectionCategory;
  reasonText: string | null;
  alsoOptout: boolean;
}): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user?.email) {
    return { ok: false, error: "Sin sesion" };
  }
  if (!REJECTION_CATEGORIES.includes(args.category)) {
    return { ok: false, error: `Categoria invalida: ${args.category}` };
  }

  const admin = createAdminClient();

  // 1. Leer state actual del message (para snapshot en revision + cancel reason).
  const msgRow = await admin
    .from("messages")
    .select("subject, body, status, research_snapshot")
    .eq("id", messageId(args.messageId))
    .single();
  if (msgRow.error) {
    return { ok: false, error: msgRow.error.message };
  }

  // 2. INSERT revision (captura aprendizaje).
  const revInsert = await admin.from("message_revisions").insert({
    message_id: args.messageId,
    revision_type: "reject",
    subject_before: msgRow.data.subject,
    subject_after: null,
    body_before: msgRow.data.body,
    body_after: null,
    rejection_category: args.category,
    rejection_reason_text: args.reasonText,
    revised_by: user.email,
  });
  if (revInsert.error) {
    return { ok: false, error: revInsert.error.message };
  }

  // 3. UPDATE messages -> cancelled, manteniendo el trail del status previo.
  const snapshot = {
    ...(msgRow.data.research_snapshot ?? {}),
    _cancelled_reason: `hitl_${args.category}`,
    _cancelled_from_status: msgRow.data.status ?? "drafted",
    _cancelled_at: new Date().toISOString(),
  };
  const updMsg = await admin
    .from("messages")
    .update({ status: "cancelled", research_snapshot: snapshot })
    .eq("id", args.messageId);
  if (updMsg.error) {
    return { ok: false, error: updMsg.error.message };
  }

  // 4. Opt-out opcional (Apendice A regla 2).
  if (args.alsoOptout) {
    const updContact = await admin
      .from("contacts")
      .update({
        is_optout: true,
        optout_at: new Date().toISOString(),
        optout_reason: `hitl_${args.category}`,
      })
      .eq("id", args.contactId);
    if (updContact.error) {
      return { ok: false, error: updContact.error.message };
    }
  }

  revalidatePath("/approval-queue");
  return { ok: true };
}

/**
 * Helper de identity para mantener el linter contento (eq necesita string y el
 * compilador valida que messageId no es undefined).
 */
function messageId(s: string): string {
  return s;
}
