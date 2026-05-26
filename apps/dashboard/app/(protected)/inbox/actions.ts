"use server";

import { revalidatePath } from "next/cache";

import { createAdminClient } from "@/lib/supabase/admin";
import { createClient } from "@/lib/supabase/server";

import { REPLY_CATEGORIES, type ReplyCategory } from "./categories";

/**
 * Marca una reply como respondida (Gonzalo ya contesto a mano en Gmail).
 * Solo cambia human_action -- NO crea draft, NO envia (Leccion 45: cero
 * respuesta automatica dentro de hilo abierto).
 */
export async function markRespondedAction(
  replyId: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) return { ok: false, error: "Sin sesion" };

  const admin = createAdminClient();
  const { error } = await admin
    .from("replies")
    .update({ human_action: "respondido" })
    .eq("id", replyId);
  if (error) return { ok: false, error: error.message };
  revalidatePath("/inbox");
  return { ok: true };
}

/**
 * Archiva una reply sin accion adicional (Gonzalo decide ignorarla o ya
 * la gestiono fuera del sistema).
 */
export async function archiveReplyAction(
  replyId: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) return { ok: false, error: "Sin sesion" };

  const admin = createAdminClient();
  const { error } = await admin
    .from("replies")
    .update({ human_action: "archivado" })
    .eq("id", replyId);
  if (error) return { ok: false, error: error.message };
  revalidatePath("/inbox");
  return { ok: true };
}

/**
 * Reclasifica una reply (IA se equivoco). Sobreescribe replies.category +
 * marca human_action='pendiente' para que handle_actions vuelva a procesar
 * la accion correcta para la nueva categoria.
 *
 * Si la reclasificacion implica que ahora ES opt-out explicito, el operador
 * tambien debe usar el flujo de "archivar" tras la opt-out automatica;
 * este endpoint NO toca is_explicit_optout (decision: mantener la senal
 * original del LLM ahi por trazabilidad, separar de categoria humana).
 */
export async function reclassifyReplyAction(
  replyId: string,
  newCategory: ReplyCategory,
): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createClient();
  const { data: { user } } = await supabase.auth.getUser();
  if (!user?.email) return { ok: false, error: "Sin sesion" };
  if (!REPLY_CATEGORIES.includes(newCategory)) {
    return { ok: false, error: `Categoria invalida: ${newCategory}` };
  }

  const admin = createAdminClient();
  const { error } = await admin
    .from("replies")
    .update({
      category: newCategory,
      human_action: "pendiente",
    })
    .eq("id", replyId);
  if (error) return { ok: false, error: error.message };
  revalidatePath("/inbox");
  return { ok: true };
}
