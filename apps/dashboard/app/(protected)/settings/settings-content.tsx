"use client";

import * as React from "react";
import { AlertTriangle, Bot, Loader2, Play, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import { emergencyPauseAction, resumeAllAction, toggleHitlModeAction } from "./actions";

export type MailboxRow = {
  id: string;
  email: string;
  display_name: string | null;
  daily_cap: number;
  current_day_sent: number;
  warmup_status: string;
  status: "active" | "paused" | "disabled";
  pause_reason: string | null;
  hitl_mode: boolean;
};

type Props = {
  initialMailboxes: MailboxRow[];
  anyActive: boolean;
  anyPaused: boolean;
};

export function SettingsContent({ initialMailboxes, anyActive, anyPaused }: Props) {
  const [busy, setBusy] = React.useState(false);

  const doPause = React.useCallback(async () => {
    if (busy) return;
    const confirmed = window.confirm(
      "PAUSA DE EMERGENCIA. Esto detiene todos los envios futuros (los " +
        "messages scheduled quedan en BD pero send_gmail no los procesa " +
        "hasta que reanudes manualmente). Continuar?",
    );
    if (!confirmed) return;
    setBusy(true);
    const res = await emergencyPauseAction();
    setBusy(false);
    if (!res.ok) {
      toast.error(`No se pudo pausar: ${res.error}`);
      return;
    }
    toast.success(`Pausados ${res.paused} mailbox(es)`);
    window.location.reload();
  }, [busy]);

  const doResume = React.useCallback(async () => {
    if (busy) return;
    const confirmed = window.confirm(
      "Reanudar todos los buzones paused. Apendice A regla 6: la auto-pausa " +
        "no debe reactivarse sin verificar la causa primero. Has investigado " +
        "el motivo de la pausa? Continuar?",
    );
    if (!confirmed) return;
    setBusy(true);
    const res = await resumeAllAction();
    setBusy(false);
    if (!res.ok) {
      toast.error(`No se pudo reanudar: ${res.error}`);
      return;
    }
    toast.success(`Reanudados ${res.resumed} mailbox(es)`);
    window.location.reload();
  }, [busy]);

  const doToggleHitl = React.useCallback(
    async (mailboxId: string, mailboxEmail: string, targetMode: boolean) => {
      if (busy) return;
      // Doble confirm requerido (Apendice A regla 1 analog: cambio modo
      // operativo requiere paper trail + accion humana explicita).
      const modeName = targetMode ? "HITL (Gonzalo aprueba drafts)" : "AUTONOMO (auto_approve.py aprueba drafts)";
      const confirm1 = window.confirm(
        `Cambiar ${mailboxEmail} a modo ${modeName}.\n\n` +
          (targetMode
            ? "Modo HITL: drafts esperan aprobacion humana en /approval-queue. " +
              "Mas seguro. Modo por defecto."
            : "Modo AUTONOMO: drafts se aprueban automaticamente por worker. " +
              "Apendice A regla 1 sigue cumplida (cola HITL existe, aprobador " +
              "es worker en lugar de humano). NO recomendado antes de 7 dias " +
              "piloto con bounce <2% y spam <0.1% confirmados.") +
          "\n\nPrimer confirm: continuar?",
      );
      if (!confirm1) return;
      const confirm2 = window.confirm(
        targetMode
          ? "Segundo confirm: volver a HITL es seguro pero detiene la automatizacion. Confirmar?"
          : "SEGUNDO CONFIRM CRITICO: confirmar que has revisado metricas 7d " +
              "y bounce <2%, spam <0.1%, sin escalados graves? Esta accion " +
              "queda en paper trail events.mode_changed. Confirmar?",
      );
      if (!confirm2) return;
      setBusy(true);
      const res = await toggleHitlModeAction(mailboxId, targetMode);
      setBusy(false);
      if (!res.ok) {
        toast.error(`No se pudo cambiar modo: ${res.error}`);
        return;
      }
      toast.success(
        `Modo cambiado a ${res.new_mode ? "HITL" : "AUTONOMO"} para ${mailboxEmail}`,
      );
      window.location.reload();
    },
    [busy],
  );

  return (
    <div className="space-y-4">
      <Card className="border-destructive/50">
        <CardHeader>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <AlertTriangle className="size-5 text-destructive" />
            Pausa de emergencia
          </h2>
          <p className="text-sm text-muted-foreground">
            Detiene todos los envios futuros sin afectar los ya enviados.
            Reversible: el boton &quot;Reanudar todo&quot; devuelve los mailbox a active.
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="flex flex-wrap gap-3 pt-4">
          <Button
            variant="destructive"
            onClick={() => void doPause()}
            disabled={busy || !anyActive}
          >
            {busy ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <AlertTriangle className="mr-2 size-4" />
            )}
            Pausar todos los activos
          </Button>
          <Button
            variant="outline"
            onClick={() => void doResume()}
            disabled={busy || !anyPaused}
          >
            {busy ? (
              <Loader2 className="mr-2 size-4 animate-spin" />
            ) : (
              <Play className="mr-2 size-4" />
            )}
            Reanudar todos los paused
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Bot className="size-5" />
            Modo HITL ↔ Autonomo (por buzon)
          </h2>
          <p className="text-sm text-muted-foreground">
            HITL = Gonzalo aprueba drafts manualmente. Autonomo = auto_approve.py
            aprueba drafts automaticamente. <strong>Default: HITL</strong>. Cambio
            requiere doble confirm + paper trail. Apendice A regla 1: la cola
            HITL existe en ambos modos (cambia el aprobador, no el flow).
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="space-y-3 pt-4">
          {initialMailboxes.map((mb) => (
            <div
              key={`hitl-${mb.id}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border p-3"
            >
              <div>
                <div className="flex items-center gap-2">
                  <strong>{mb.email}</strong>
                  {mb.hitl_mode ? (
                    <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs uppercase text-emerald-900">
                      <ShieldCheck className="mr-1 inline size-3" />
                      HITL (seguro)
                    </span>
                  ) : (
                    <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs uppercase text-amber-900">
                      <Bot className="mr-1 inline size-3" />
                      AUTONOMO
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {mb.hitl_mode
                    ? "Drafts esperan a Gonzalo en /approval-queue. Modo seguro."
                    : "auto_approve.py aprueba automaticamente. Verifica metricas 7d."}
                </p>
              </div>
              <Button
                variant={mb.hitl_mode ? "default" : "outline"}
                size="sm"
                onClick={() =>
                  void doToggleHitl(mb.id, mb.email, !mb.hitl_mode)
                }
                disabled={busy}
              >
                {busy ? (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                ) : null}
                Cambiar a {mb.hitl_mode ? "AUTONOMO" : "HITL"}
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
