/**
 * Constantes + tipos para el modal de rechazo HITL.
 *
 * Espejo del CHECK CONSTRAINT en migration 14 (`message_revisions.rejection_category`).
 *
 * Vive en un fichero separado de `actions.ts` porque Next.js Turbopack
 * rechaza ficheros `"use server"` que exporten cualquier cosa que no sea
 * funcion async (error "A 'use server' file can only export async
 * functions, found object"). Constantes y tipos van aqui.
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
