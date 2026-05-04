import { createClient } from "@supabase/supabase-js";

/**
 * Cliente Supabase con service role. Bypasea RLS — uso server-only.
 *
 * El KB editor usa este cliente para:
 *   - INSERT bulk en kb_chunks tras un reembed (la dim del vector requiere
 *     que el cast literal '[v1,...]' se acepte; service_role evita
 *     ambiguedad con permisos por sesion).
 *   - DELETE de chunks viejos antes de regenerar.
 *   - UPDATE kb_documents.embeddings_updated_at tras exito.
 *
 * NO se exporta al cliente. Cualquier import desde un componente "use client"
 * fallara en build (las env vars sin prefijo NEXT_PUBLIC_ no estan en el
 * bundle).
 */
export function createAdminClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase admin env vars: NEXT_PUBLIC_SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY",
    );
  }
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
