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

import { approveMessageAction, rejectAndOptoutAction } from "./actions";

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

export function ApprovalQueueContent({ initialDrafts }: Props) {
  const [drafts, setDrafts] = React.useState<DraftItem[]>(initialDrafts);
  const [index, setIndex] = React.useState(0);
  const [editor, setEditor] = React.useState<EditState>({ mode: "view" });
  const [busy, setBusy] = React.useState(false);

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

  const doRejectOptout = React.useCallback(async () => {
    if (!current || busy) return;
    const confirmed = window.confirm(
      `Rechazar y excluir permanentemente a ${current.contact.email}? ` +
        `Esto marca el contact como is_optout=true y cancela el draft. ` +
        `Apendice A regla 2: opt-out permanente.`,
    );
    if (!confirmed) return;
    setBusy(true);
    const res = await rejectAndOptoutAction(current.id, current.contact.id);
    setBusy(false);
    if (!res.ok) {
      toast.error(`No se pudo rechazar: ${res.error}`);
      return;
    }
    toast.success(`Rechazado + opt-out ${current.contact.email}`);
    removeAndAdvance(current.id);
  }, [current, busy, removeAndAdvance]);

  // Keyboard navigation
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Si el foco esta en un input/textarea, no interceptamos teclas
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea") return;
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
        void doRejectOptout();
      } else if (e.key === "s") {
        e.preventDefault();
        skip();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [editor.mode, busy, skip, back, doApprove, startEditing, doRejectOptout]);

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
                onClick={() => void doRejectOptout()}
                disabled={busy}
              >
                <XCircle className="mr-2 size-4" />
                Rechazar + opt-out (x)
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
    </div>
  );
}
