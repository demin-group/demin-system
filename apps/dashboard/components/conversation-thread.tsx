import { cn } from "@/lib/utils";
import { CATEGORY_LABEL, categoryBadgeClass } from "@/lib/reply-format";
import type { ThreadEntry } from "@/lib/conversation";

function formatTs(ts: string): string {
  return new Date(ts).toLocaleString("es-ES", {
    timeZone: "Europe/Madrid",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * Panel de conversacion reutilizable (inbox + cola de aprobacion). Pinta el hilo
 * completo: salientes (DEMIN) a la derecha en gris, entrantes (prospecto)
 * resaltados a la izquierda con el badge de su clasificacion.
 *
 * Solo presentacion (sin hooks ni handlers) -> server-renderable y valido
 * tambien dentro de un client component sin directiva "use client".
 */
export function ConversationThread({
  thread,
  maxBody = 600,
}: {
  thread: ThreadEntry[];
  maxBody?: number;
}) {
  if (thread.length === 0) return null;
  return (
    <div className="space-y-2">
      {thread.map((e) => {
        const inbound = e.direction === "in";
        return (
          <div
            key={`${e.direction}-${e.id}`}
            className={cn(
              "rounded-md border p-2 text-xs",
              inbound
                ? "ml-6 border-emerald-300 bg-emerald-50/40"
                : "mr-6 bg-muted/30",
            )}
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] font-bold uppercase",
                  inbound
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-500 text-white",
                )}
              >
                {inbound ? "← Prospecto" : "→ DEMIN"}
              </span>
              {!inbound && e.angle ? (
                <span className="text-muted-foreground">
                  step {e.step_index} ({e.angle})
                </span>
              ) : null}
              {!inbound && e.status === "bounced" ? (
                <span className="font-medium text-red-700">rebotó</span>
              ) : null}
              {inbound ? (
                <span
                  className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] uppercase",
                    categoryBadgeClass(e.category),
                  )}
                >
                  {e.category
                    ? (CATEGORY_LABEL[e.category] ?? e.category)
                    : "sin clasificar"}
                </span>
              ) : null}
              {e.is_optout ? (
                <span className="rounded bg-red-100 px-1.5 py-0.5 text-[10px] uppercase text-red-900">
                  opt-out
                </span>
              ) : null}
              <span className="ml-auto text-muted-foreground">
                {formatTs(e.ts)}
              </span>
            </div>
            {e.subject ? (
              <p className="mt-1 font-medium">{e.subject}</p>
            ) : null}
            {e.body ? (
              <pre className="mt-1 whitespace-pre-wrap font-sans text-muted-foreground">
                {e.body.slice(0, maxBody)}
                {e.body.length > maxBody ? "\n[…]" : ""}
              </pre>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
