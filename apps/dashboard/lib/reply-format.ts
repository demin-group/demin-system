/**
 * Helpers compartidos de formato para replies / conversaciones.
 *
 * Centraliza el etiquetado y el color de categoria (antes duplicado en
 * inbox/page.tsx) para que el panel de conversacion (ConversationThread) y el
 * inbox usen exactamente el mismo criterio visual. Modulo puro (sin acceso a
 * BD) -> seguro de importar tanto en server como en client components.
 */

export const CATEGORY_LABEL: Record<string, string> = {
  interesado: "Interesado",
  pide_info: "Pide info",
  no_ahora: "No ahora",
  no_interesado: "No interesado",
  rebote: "Rebote",
  fuera_oficina: "Fuera oficina",
  desconocido: "Desconocido",
};

export function categoryBadgeClass(cat: string | null): string {
  if (cat === "interesado") return "bg-emerald-100 text-emerald-900";
  if (cat === "pide_info") return "bg-blue-100 text-blue-900";
  if (cat === "no_ahora") return "bg-amber-100 text-amber-900";
  if (cat === "no_interesado") return "bg-orange-100 text-orange-900";
  if (cat === "rebote") return "bg-red-100 text-red-900";
  if (cat === "fuera_oficina") return "bg-purple-100 text-purple-900";
  return "bg-muted text-muted-foreground";
}

/**
 * Deep-link a Gmail filtrado por el contacto, para que Gonzalo responda a mano
 * DENTRO del hilo. Leccion 45: el bot nunca escribe en el hilo abierto; el
 * dashboard solo le lleva a la conversacion para que conteste el humano.
 */
export function gmailSearchUrl(email: string): string {
  const q = `from:${email} OR to:${email}`;
  return `https://mail.google.com/mail/u/0/#search/${encodeURIComponent(q)}`;
}
