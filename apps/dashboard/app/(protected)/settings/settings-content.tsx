"use client";

import * as React from "react";
import { AlertTriangle, Bot, Loader2, Play, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import {
  cancelScheduledSwitchAction,
  emergencyPauseAction,
  resumeAllAction,
  toggleAutoSwitchEnabledAction,
  toggleHitlModeAction,
} from "./actions";

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
  auto_switch_enabled: boolean;
  scheduled_autonomous_switch_at: string | null;
};

export type AutonomousConditionResult = {
  name: string;
  label: string;
  ok: boolean;
  detail: string;
};

type Props = {
  initialMailboxes: MailboxRow[];
  anyActive: boolean;
  anyPaused: boolean;
  autonomousConditions: AutonomousConditionResult[];
};

export function SettingsContent({
  initialMailboxes,
  anyActive,
  anyPaused,
  autonomousConditions,
}: Props) {
  const [busy, setBusy] = React.useState(false);
  const allGreen = autonomousConditions.every((c) => c.ok);
  const greenCount = autonomousConditions.filter((c) => c.ok).length;

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

  const doToggleAutoSwitch = React.useCallback(
    async (mailboxId: string, enabled: boolean) => {
      if (busy) return;
      const confirmed = window.confirm(
        enabled
          ? "Activar auto-switch: el sistema podra programar el cambio a " +
              "AUTONOMO (hitl_mode=false) automaticamente cuando las 7 " +
              "condiciones del Bloque 6 esten verdes. Recibiras email 24h " +
              "antes con boton para cancelar. Continuar?"
          : "Desactivar auto-switch: el sistema evaluara condiciones pero " +
              "NUNCA programara cambio automatico. Si hay un switch ya " +
              "programado, se cancela. PM tendra que activar manualmente " +
              "via 'Cambiar a AUTONOMO' en la seccion HITL. Continuar?",
      );
      if (!confirmed) return;
      setBusy(true);
      const res = await toggleAutoSwitchEnabledAction(mailboxId, enabled);
      setBusy(false);
      if (!res.ok) {
        toast.error(`No se pudo cambiar: ${res.error}`);
        return;
      }
      toast.success(
        enabled
          ? "Auto-switch ACTIVADO"
          : "Auto-switch DESACTIVADO + schedule cancelado si lo habia",
      );
      window.location.reload();
    },
    [busy],
  );

  const doCancelSchedule = React.useCallback(
    async (mailboxId: string) => {
      if (busy) return;
      const confirmed = window.confirm(
        "Cancelar el switch programado. El sistema sigue evaluando " +
          "condiciones; si se mantienen verdes el worker programara de " +
          "nuevo en el proximo run (con email 24h antes). Para impedirlo " +
          "completamente, desactiva el toggle auto-switch. Continuar?",
      );
      if (!confirmed) return;
      setBusy(true);
      const res = await cancelScheduledSwitchAction(mailboxId);
      setBusy(false);
      if (!res.ok) {
        toast.error(`No se pudo cancelar: ${res.error}`);
        return;
      }
      toast.success("Schedule cancelado");
      window.location.reload();
    },
    [busy],
  );

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

      <Card>
        <CardHeader>
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <Bot className="size-5" />
            Auto-switch a autónomo (Bloque 6 — L50)
          </h2>
          <p className="text-sm text-muted-foreground">
            Cuando las 7 condiciones del Bloque 6 estén verdes Y el toggle
            auto-switch esté activo, el worker{" "}
            <code>auto_switch_to_autonomous.py</code> (timer 6h) programa
            el cambio a AUTONOMO con email previo 24h. PM puede cancelar
            desde aquí en cualquier momento.
          </p>
        </CardHeader>
        <Separator />
        <CardContent className="space-y-4 pt-4">
          {initialMailboxes.map((mb) => {
            const scheduled = mb.scheduled_autonomous_switch_at
              ? new Date(mb.scheduled_autonomous_switch_at)
              : null;
            return (
              <div
                key={`autosw-${mb.id}`}
                className="space-y-3 rounded-md border p-3"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <strong>{mb.email}</strong>
                      {mb.auto_switch_enabled ? (
                        <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs uppercase text-emerald-900">
                          auto-switch ON
                        </span>
                      ) : (
                        <span className="rounded-md bg-muted px-2 py-0.5 text-xs uppercase text-muted-foreground">
                          auto-switch OFF
                        </span>
                      )}
                    </div>
                  </div>
                  <Button
                    variant={mb.auto_switch_enabled ? "outline" : "default"}
                    size="sm"
                    onClick={() =>
                      void doToggleAutoSwitch(mb.id, !mb.auto_switch_enabled)
                    }
                    disabled={busy}
                  >
                    {mb.auto_switch_enabled ? "Desactivar auto-switch" : "Activar auto-switch"}
                  </Button>
                </div>

                {scheduled ? (
                  <div className="rounded-md border border-amber-400 bg-amber-50 p-3">
                    <p className="text-sm font-medium text-amber-900">
                      ⏰ Switch a AUTONOMO programado para:{" "}
                      <strong>
                        {scheduled.toLocaleString("es-ES", {
                          timeZone: "Europe/Madrid",
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </strong>
                    </p>
                    <Button
                      variant="outline"
                      size="sm"
                      className="mt-2"
                      onClick={() => void doCancelSchedule(mb.id)}
                      disabled={busy}
                    >
                      Cancelar switch programado
                    </Button>
                  </div>
                ) : null}

                {!mb.hitl_mode ? (
                  <div className="rounded-md border-2 border-destructive bg-destructive/10 p-3">
                    <p className="text-sm font-medium text-destructive">
                      🤖 SISTEMA EN MODO AUTONOMO. Drafts se aprueban sin intervención humana.
                    </p>
                    <Button
                      variant="destructive"
                      size="lg"
                      className="mt-3 w-full"
                      onClick={() => void doToggleHitl(mb.id, mb.email, true)}
                      disabled={busy}
                    >
                      🔙 Volver a HITL ahora (rollback de emergencia)
                    </Button>
                  </div>
                ) : null}
              </div>
            );
          })}

          <div className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-sm font-semibold">
                Estado de las 7 condiciones ({greenCount}/7 verdes)
              </h3>
              {allGreen ? (
                <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-bold uppercase text-emerald-900">
                  TODAS VERDES
                </span>
              ) : (
                <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-bold uppercase text-amber-900">
                  {7 - greenCount} pendiente{7 - greenCount === 1 ? "" : "s"}
                </span>
              )}
            </div>
            <table className="w-full text-xs">
              <thead className="text-left uppercase text-muted-foreground">
                <tr>
                  <th className="pb-2">Condición</th>
                  <th className="pb-2 text-center">OK</th>
                  <th className="pb-2">Detalle</th>
                </tr>
              </thead>
              <tbody>
                {autonomousConditions.map((c) => (
                  <tr key={c.name} className="border-t">
                    <td className="py-2">{c.label}</td>
                    <td className="py-2 text-center text-lg">
                      {c.ok ? "✅" : "❌"}
                    </td>
                    <td className="py-2 font-mono text-xs text-muted-foreground">
                      {c.detail}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-muted-foreground">
              Decisión PM L50: pool threshold ajustado a ≥50 (no 100).
              Aprobaciones threshold ≥50. Detalle de las 7 condiciones en
              prompt /goal v4 Bloque 6.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
