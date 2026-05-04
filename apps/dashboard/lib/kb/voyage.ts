/**
 * Cliente Voyage para el KB editor. Llamada HTTP directa a la API REST,
 * sin SDK — el endpoint es trivial y mantenemos el dashboard sin deps
 * adicionales. Fetch global de Node 18+.
 *
 * El input_type asimetrico se respeta (Leccion derivada del Sprint 1
 * paso 2): "document" para chunks que se indexan, "query" para queries
 * que recuperan. Mezclar roles degrada retrieval.
 *
 * Errores 4xx (auth, bad request) NO se reintentan — son problemas de
 * configuracion. Errores 429/5xx (rate limit, server) se propagan; la
 * UI muestra el error y el operador puede reintentar.
 */

const VOYAGE_URL = "https://api.voyageai.com/v1/embeddings";
const DEFAULT_MODEL = "voyage-multilingual-2";
const EXPECTED_DIM = 1024;

export type VoyageInputType = "document" | "query";

export async function embedTexts(
  texts: string[],
  inputType: VoyageInputType = "document",
): Promise<number[][]> {
  if (texts.length === 0) return [];

  const apiKey = process.env.VOYAGE_API_KEY;
  if (!apiKey) {
    throw new Error("VOYAGE_API_KEY no configurada en el entorno del dashboard");
  }

  const model = process.env.VOYAGE_MODEL ?? DEFAULT_MODEL;

  const res = await fetch(VOYAGE_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      input: texts,
      input_type: inputType,
    }),
  });

  if (!res.ok) {
    const errText = await res.text();
    throw new Error(`Voyage API ${res.status}: ${errText.slice(0, 500)}`);
  }

  const data: { data: Array<{ embedding: number[] }> } = await res.json();
  const vectors = data.data.map((d) => d.embedding);

  if (vectors.length !== texts.length) {
    throw new Error(
      `Voyage devolvio ${vectors.length} vectores para ${texts.length} textos`,
    );
  }
  if (vectors[0].length !== EXPECTED_DIM) {
    throw new Error(
      `Dim de embedding inesperada: esperado ${EXPECTED_DIM}, recibido ${vectors[0].length} (modelo ${model})`,
    );
  }

  return vectors;
}
