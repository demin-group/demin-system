"use client";

import * as React from "react";
import {
  CheckCircle2,
  Loader2,
  Pencil,
  SkipForward,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { approveMessageAction, rejectMessageAction } from "./actions";
import { REJECTION_CATEGORIES, type RejectionCategory } from "./categories";

export type DraftItem = {
  id: string;
  subject: string;
  body: string;
  step_index: number;
  angle: string;
  created_at: string;
  generation_cost_usd: number | null;
  failed_validations: string[] | undefined;
  contact: {
    id: string;
    email: string;
    email_type: string;
    email_priority: number;
    nombre: string | null;
    cargo: string | null;
  };
  company: {
    id: string;
    nif: string;
    nombre: string;
    tier: string | null;
    web: string | null;
    ia_fit: string | null;
    ia_fit_reason: string | null;
  };
};

type Props = { initialDrafts: DraftItem[] };

type EditState =
  | { mode: "view" }
  | { mode: "editing"; subject: string; body: string };

const CATEGORY_LABELS: Record<RejectionCategory, string> = {
  tono: "Tono no encaja",
  datos_incorrectos: "Datos incorrectos (hooks alucinados, research mal)",
  no_icp: "No es ICP (falso positivo classify_descr)",
  longitud: "Longitud (muy largo o muy corto)",
  asunto: "Asunto malo",
  duplicado_contacto: "Duplicado de contact del mismo dominio",
  otro: "Otro (describe abajo)",
};

// Categorias que por defecto activan opt-out: el contact NO debe recibir mas
// porque no es valido. Para tono/longitud/asunto el draft se regenera con
// nuevos prompts en cadencia futura y el contact sigue activo.
const DEFAULT_OPTOUT_FOR: ReadonlySet<RejectionCategory> = new Set<RejectionCategory>(
  ["no_icp", "duplicado_contacto"],
);

export function ApprovalQueueContent({ initialDrafts }: Props) {
  const [drafts, setDrafts] = React.useState<DraftItem[]>(initialDrafts);
  const [index, setIndex] = React.useState(0);
  const [editor, setEditor] = React.useState<EditState>({ mode: "view" });
  const [busy, setBusy] = React.useState(false);
  const [rejectModal, setRejectModal] = React.useState<null | {
    category: RejectionCategory;
    reasonText: string;
    alsoOptout: boolean;
  }>(null);

  const current = drafts[index];

  const removeAndAdvance = React.useCallback(
    (id: string) => {
      setDrafts((prev) => prev.filter((d) => d.id !== id));
      // Si el index se queda sin elemento (ej. era el ultimo), retrocedemos
      setIndex((prev) => Math.min(prev, drafts.length - 2));
      setEditor({ mode: "view" });
    },
    [drafts.length],
  );

  const skip = React.useCallback(() => {
    setIndex((prev) => Math.min(prev + 1, drafts.length - 1));
    setEditor({ mode: "view" });
  }, [drafts.length]);

  const back = React.useCallback(() => {
    setIndex((prev) => Math.max(prev - 1, 0));
    setEditor({ mode: "view" });
  }, []);

  const startEditing = React.useCallback(() => {
    if (!current) return;
    setEditor({ mode: "editing", subject: current.subject, body: current.body });
  }, [current]);

  const doApprove = React.useCallback(
    async (edited?: { subject: string; body: string }) => {
      if (!current || busy) return;
      setBusy(true);
      const res = await approveMessageAction(current.id, edited);
      setBusy(false);
      if (!res.ok) {
        toast.error(`No se pudo aprobar: ${res.error}`);
        return;
      }
      toast.success(
        edited ? "Aprobado con edicion" : `Aprobado ${current.contact.email}`,
      );
      removeAndAdvance(current.id);
    },
    [current, busy, removeAndAdvance],
  );

  const openRejectModal = React.useCallback(() => {
    if (!current || busy) return;
    setRejectModal({
      category: "tono",
      reasonText: "",
      alsoOptout: false,
    });
  }, [current, busy]);

  const closeRejectModal = React.useCallback(() => {
    setRejectModal(null);
  }, []);

  const submitReject = React.useCallback(async () => {
    if (!current || !rejectModal || busy) return;
    setBusy(true);
    const res = await rejectMessageAction({
      messageId: current.id,
      contactId: current.contact.id,
      category: rejectModal.category,
      reasonText: rejectModal.reasonText.trim() || null,
      alsoOptout: rejectModal.alsoOptout,
    });
    setBusy(false);
    if (!res.ok) {
      toast.error(`No se pudo rechazar: ${res.error}`);
      return;
    }
    toast.success(
      rejectModal.alsoOptout
        ? `Rechazado + opt-out ${current.contact.email}`
        : `Rechazado ${current.contact.email} (contact sigue activo)`,
    );
    closeRejectModal();
    removeAndAdvance(current.id);
  }, [current, rejectModal, busy, closeRejectModal, removeAndAdvance]);

  // Cuando cambia la categoria, ajusta el default de alsoOptout.
  const setRejectCategory = React.useCallback((cat: RejectionCategory) => {
    setRejectModal((prev) =>
      prev === null
        ? prev
        : { ...prev, category: cat, alsoOptout: DEFAULT_OPTOUT_FOR.has(cat) },
    );
  }, []);

  // Keyboard navigation
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Si el modal esta abierto, solo escapamos con Escape.
      if (rejectModal !== null) {
        if (e.key === "Escape") {
          e.preventDefault();
          closeRejectModal();
        }
        return;
      }
      // Si el foco esta en un input/textarea, no interceptamos teclas
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if (editor.mode === "editing") return;
      if (busy) return;

      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        skip();
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        back();
      } else if (e.key === "a") {
        e.preventDefault();
        void doApprove();
      } else if (e.key === "e") {
        e.preventDefault();
        startEditing();
      } else if (e.key === "x") {
        e.preventDefault();
        openRejectModal();
      } else if (e.key === "s") {
        e.preventDefault();
        skip();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [
    editor.mode,
    busy,
    skip,
    back,
    doApprove,
    startEditing,
    openRejectModal,
    rejectModal,
    closeRejectModal,
  ]);

  if (drafts.length === 0) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            Approval Queue
          </h1>
          <p className="text-sm text-muted-foreground">
            Cola HITL de drafts pendientes de aprobacion antes de envio.
          </p>
        </div>
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No hay drafts pendientes. Corre <code>generate_draft.py</code> o
            <code>follow_ups.py</code> para poblar la cola.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!current) {
    // Defensa contra index fuera de rango
    return null;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">
            Approval Queue
          </h1>
          <p className="text-sm text-muted-foreground">
            {drafts.length} draft{drafts.length === 1 ? "" : "s"} pendiente
            {drafts.length === 1 ? "" : "s"}. Posicion {index + 1}/{drafts.length}.
            Teclado: <kbd>j</kbd>/<kbd>k</kbd> nav, <kbd>a</kbd> aprobar,{" "}
            <kbd>e</kbd> editar, <kbd>x</kbd> rechazar+optout, <kbd>s</kbd> skip.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader className="space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-md bg-muted px-2 py-0.5 font-medium">
              {current.company.nif}
            </span>
            <span className="font-medium">{current.company.nombre}</span>
            {current.company.tier ? (
              <span className="rounded-md border px-2 py-0.5 text-xs uppercase">
                {current.company.tier}
              </span>
            ) : null}
            {current.company.web ? (
              <a
                href={`https://${current.company.web.replace(/^https?:\/\//, "")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-muted-foreground underline"
              >
                {current.company.web}
              </a>
            ) : null}
          </div>
          <div className="text-xs text-muted-foreground">
            <span>To: </span>
            <strong>{current.contact.email}</strong>
            <span>
              {" "}
              ({current.contact.email_type}, prio {current.contact.email_priority})
            </span>
            {current.contact.nombre ? (
              <span>
                {" "}
                · {current.contact.nombre}
                {current.contact.cargo ? ` (${current.contact.cargo})` : ""}
              </span>
            ) : null}
            <span> · step {current.step_index} ({current.angle})</span>
            {current.generation_cost_usd != null ? (
              <span> · ${current.generation_cost_usd.toFixed(4)}</span>
            ) : null}
          </div>
          {current.failed_validations && current.failed_validations.length > 0 ? (
            <div className="rounded-md bg-amber-100 px-3 py-2 text-xs text-amber-900">
              <strong>Validaciones automaticas con warning:</strong>{" "}
              {current.failed_validations.join(", ")}. Revisa antes de aprobar.
            </div>
          ) : null}
        </CardHeader>

        <Separator />

        <CardContent className="space-y-4 pt-4">
          {editor.mode === "view" ? (
            <>
              <div>
                <Label className="text-xs uppercase text-muted-foreground">
                  Subject
                </Label>
                <p className="font-medium">{current.subject}</p>
              </div>
              <div>
                <Label className="text-xs uppercase text-muted-foreground">
                  Body
                </Label>
                <pre className="whitespace-pre-wrap font-sans text-sm">
                  {current.body}
                </pre>
              </div>
            </>
          ) : (
            <>
              <div className="space-y-1.5">
                <Label htmlFor="edit-subject">Subject</Label>
                <Input
                  id="edit-subject"
                  value={editor.subject}
                  onChange={(e) =>
                    setEditor({ ...editor, subject: e.target.value })
                  }
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="edit-body">Body</Label>
                <Textarea
                  id="edit-body"
                  rows={14}
                  value={editor.body}
                  onChange={(e) =>
                    setEditor({ ...editor, body: e.target.value })
                  }
                />
              </div>
            </>
          )}
        </CardContent>

        <Separator />

        <CardContent className="flex flex-wrap gap-2 pt-4">
          {editor.mode === "view" ? (
            <>
              <Button onClick={() => doApprove()} disabled={busy}>
                {busy ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 size-4" />
                )}
                Aprobar (a)
              </Button>
              <Button variant="outline" onClick={startEditing} disabled={busy}>
                <Pencil className="mr-2 size-4" />
                Editar (e)
              </Button>
              <Button
                variant="destructive"
                onClick={openRejectModal}
                disabled={busy}
              >
                <XCircle className="mr-2 size-4" />
                Rechazar (x)
              </Button>
              <Button variant="ghost" onClick={skip} disabled={busy}>
                <SkipForward className="mr-2 size-4" />
                Skip (s)
              </Button>
            </>
          ) : (
            <>
              <Button
                onClick={() =>
                  doApprove({ subject: editor.subject, body: editor.body })
                }
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 size-4" />
                )}
                Aprobar con edicion
              </Button>
              <Button
                variant="ghost"
                onClick={() => setEditor({ mode: "view" })}
                disabled={busy}
              >
                Cancelar
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <div
        className={cn(
          "flex justify-between text-xs text-muted-foreground",
          drafts.length <= 1 && "hidden",
        )}
      >
        <button onClick={back} className="underline" disabled={index === 0}>
          ← Anterior (k)
        </button>
        <button
          onClick={skip}
          className="underline"
          disabled={index >= drafts.length - 1}
        >
          Siguiente (j) →
        </button>
      </div>

      {rejectModal !== null ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reject-modal-title"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeRejectModal();
          }}
        >
          <Card className="w-full max-w-lg">
            <CardHeader>
              <h2
                id="reject-modal-title"
                className="text-lg font-semibold"
              >
                Rechazar draft
              </h2>
              <p className="text-xs text-muted-foreground">
                To: {current.contact.email} · {current.company.nombre}
                {" · "}step {current.step_index} ({current.angle})
              </p>
            </CardHeader>
            <Separator />
            <CardContent className="space-y-4 pt-4">
              <div className="space-y-1.5">
                <Label htmlFor="reject-category">Categoria</Label>
                <select
                  id="reject-category"
                  value={rejectModal.category}
                  onChange={(e) =>
                    setRejectCategory(e.target.value as RejectionCategory)
                  }
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                  disabled={busy}
                >
                  {REJECTION_CATEGORIES.map((cat) => (
                    <option key={cat} value={cat}>
                      {CATEGORY_LABELS[cat]}
                    </option>
                  ))}
                </select>
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="reject-reason">
                  Motivo (opcional, libre)
                </Label>
                <Textarea
                  id="reject-reason"
                  rows={3}
                  placeholder="Texto libre. Ej. 'el hook 17 promociones no aparece en su web actual, research desactualizado'"
                  value={rejectModal.reasonText}
                  onChange={(e) =>
                    setRejectModal((prev) =>
                      prev === null
                        ? prev
                        : { ...prev, reasonText: e.target.value },
                    )
                  }
                  disabled={busy}
                />
              </div>

              <div className="flex items-start gap-2 rounded-md border bg-muted/30 p-3">
                <input
                  id="reject-also-optout"
                  type="checkbox"
                  checked={rejectModal.alsoOptout}
                  onChange={(e) =>
                    setRejectModal((prev) =>
                      prev === null
                        ? prev
                        : { ...prev, alsoOptout: e.target.checked },
                    )
                  }
                  disabled={busy}
                  className="mt-1"
                />
                <Label
                  htmlFor="reject-also-optout"
                  className="cursor-pointer text-xs leading-relaxed"
                >
                  Tambien marcar contact como <strong>opt-out permanente</strong>{" "}
                  (Apendice A regla 2). Marcado por defecto para{" "}
                  <code>no_icp</code> y <code>duplicado_contacto</code>; opcional
                  para el resto (tono/longitud/asunto regeneran con prompts
                  nuevos en cadencia futura).
                </Label>
              </div>
            </CardContent>
            <Separator />
            <CardContent className="flex flex-wrap justify-end gap-2 pt-4">
              <Button
                variant="ghost"
                onClick={closeRejectModal}
                disabled={busy}
              >
                Cancelar (Esc)
              </Button>
              <Button
                variant="destructive"
                onClick={() => void submitReject()}
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : (
                  <XCircle className="mr-2 size-4" />
                )}
                Confirmar rechazo
              </Button>
            </CardContent>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
