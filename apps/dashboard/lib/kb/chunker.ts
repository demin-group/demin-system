/**
 * Chunker para el KB. Replica EXACTAMENTE el algoritmo Python en
 * `apps/workers/kb/embed_documents.py::chunk_text`. Si el algoritmo cambia
 * en una codebase, debe cambiar en la otra simultaneamente — los chunks
 * indexados desde Python (Sprint 1 paso 2) y los indexados desde Node
 * (Sprint 1 paso 4) tienen que ser equivalentes para que retrieval no
 * dependa de la fuente.
 *
 * Decisiones:
 * - ~2000 chars con overlap 200 (~500 tokens ES, encaja con plan §7.2).
 * - Si el corte cae dentro de un parrafo y existe `\n\n` en los 300 chars
 *   anteriores, corta ahi para no partir parrafos.
 * - Texto vacio → lista vacia. Texto mas corto que CHUNK_CHARS → 1 chunk.
 */

export const CHUNK_CHARS = 2000;
export const CHUNK_OVERLAP = 200;
export const PARAGRAPH_LOOKBACK = 300;

export function chunkText(input: string): string[] {
  const s = input.trim();
  if (!s) return [];
  if (s.length <= CHUNK_CHARS) return [s];

  const chunks: string[] = [];
  let i = 0;
  const n = s.length;

  while (i < n) {
    let end = Math.min(i + CHUNK_CHARS, n);
    if (end < n) {
      const windowStart = Math.max(end - PARAGRAPH_LOOKBACK, i);
      const window = s.slice(windowStart, end);
      const idx = window.lastIndexOf("\n\n");
      if (idx >= 0) {
        end = windowStart + idx;
      }
    }
    const chunk = s.slice(i, end).trim();
    if (chunk) chunks.push(chunk);
    if (end >= n) break;
    const nextI = end - CHUNK_OVERLAP;
    i = nextI > i ? nextI : end; // garantiza progreso
  }
  return chunks;
}
