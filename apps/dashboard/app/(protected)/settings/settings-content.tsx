"use client";

import * as React from "react";
import { AlertTriangle, Loader2, Play } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";

import { emergencyPauseAction, resumeAllAction } from "./actions";

export type MailboxRow = {
  id: string;
  email: string;
  display_name: string | null;
  daily_cap: number;
  current_day_sent: number;
  warmup_status: string;
  status: "active" | "paused" | "disabled";
  pause_reason: string | null;
};

type Props = {
  initialMailboxes: MailboxRow[];
  anyActive: boolean;
  anyPaused: boolean;
};

export function SettingsContent({ anyActive, anyPaused }: Props) {
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

  return (
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
  );
}
