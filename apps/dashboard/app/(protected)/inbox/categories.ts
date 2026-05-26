/**
 * Constantes + tipos para las acciones humanas sobre replies.
 *
 * Espejo de los valores de `replies.category` emitidos por
 * `classify_replies.py` (apps/workers/replies/classify_replies.py).
 *
 * Vive en un fichero separado de `actions.ts` porque Next.js Turbopack
 * rechaza ficheros `"use server"` que exporten cualquier cosa que no sea
 * funcion async (error "A 'use server' file can only export async
 * functions, found object"). Constantes y tipos van aqui.
 */

export const REPLY_CATEGORIES = [
  "interesado",
  "pide_info",
  "no_ahora",
  "no_interesado",
  "rebote",
  "fuera_oficina",
  "desconocido",
] as const;

export type ReplyCategory = (typeof REPLY_CATEGORIES)[number];
