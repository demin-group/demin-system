"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  archiveReplyAction,
  markRespondedAction,
  reclassifyReplyAction,
} from "./actions";
import { REPLY_CATEGORIES, type ReplyCategory } from "./categories";

type Props = {
  replyId: string;
  currentCategory: string | null;
};

/**
 * Botonera cliente para una reply: marcar respondida / reclasificar / archivar.
 * Leccion 45: NO incluye boton de "responder con draft IA". Gonzalo responde
 * fuera del dashboard (Gmail directo). El dashboard solo es panel de senal.
 */
export function ReplyActions({ replyId, currentCategory }: Props) {
  const [pending, startTransition] = React.useTransition();
  const [reclassifying, setReclassifying] = React.useState(false);
  const [newCat, setNewCat] = React.useState<ReplyCategory>(
    (currentCategory as ReplyCategory) ?? "desconocido",
  );

  const doMarkResponded = () => {
    startTransition(async () => {
      const res = await markRespondedAction(replyId);
      if (!res.ok) toast.error(`No se pudo marcar: ${res.error}`);
      else toast.success("Marcada como respondida");
    });
  };

  const doArchive = () => {
    startTransition(async () => {
      const res = await archiveReplyAction(replyId);
      if (!res.ok) toast.error(`No se pudo archivar: ${res.error}`);
      else toast.success("Archivada");
    });
  };

  const doReclassify = () => {
    startTransition(async () => {
      const res = await reclassifyReplyAction(replyId, newCat);
      if (!res.ok) toast.error(`No se pudo reclasificar: ${res.error}`);
      else {
        toast.success(`Reclasificada como ${newCat}`);
        setReclassifying(false);
      }
    });
  };

  if (reclassifying) {
    return (
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Nueva categoría:</span>
        <select
          value={newCat}
          onChange={(e) => setNewCat(e.target.value as ReplyCategory)}
          className="rounded-md border bg-background px-2 py-1 text-xs"
          disabled={pending}
        >
          {REPLY_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <Button
          size="sm"
          variant="default"
          onClick={doReclassify}
          disabled={pending || newCat === currentCategory}
        >
          Confirmar
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setReclassifying(false)}
          disabled={pending}
        >
          Cancelar
        </Button>
      </div>
    );
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      <Button
        size="sm"
        variant="default"
        onClick={doMarkResponded}
        disabled={pending}
      >
        Marcar como respondida
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => setReclassifying(true)}
        disabled={pending}
      >
        Reclasificar
      </Button>
      <Button
        size="sm"
        variant="ghost"
        onClick={doArchive}
        disabled={pending}
      >
        Archivar
      </Button>
    </div>
  );
}
