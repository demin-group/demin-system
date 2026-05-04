"use client";

import * as React from "react";
import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  CATEGORY_META,
  CATEGORY_ORDER,
  type KbCategory,
  categoryMeta,
} from "./category-meta";

export type KbDoc = {
  id: string;
  category: string;
  titulo: string;
  contenido: string;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  embeddings_updated_at: string | null;
  n_chunks: number;
};

type Props = { initialDocs: KbDoc[] };

type EditorState =
  | { mode: "idle" }
  | { mode: "creating" }
  | { mode: "editing"; id: string };

const NEW_DOC_DEFAULT: Pick<KbDoc, "category" | "titulo" | "contenido"> = {
  category: "otro",
  titulo: "",
  contenido: "",
};

export function KbContent({ initialDocs }: Props) {
  const [docs, setDocs] = React.useState<KbDoc[]>(initialDocs);
  const [editor, setEditor] = React.useState<EditorState>({ mode: "idle" });

  const refresh = React.useCallback(async () => {
    const res = await fetch("/api/kb", { cache: "no-store" });
    if (!res.ok) {
      toast.error("No se pudo refrescar la lista de documentos");
      return;
    }
    const data: { documents: KbDoc[] } = await res.json();
    setDocs(data.documents);
  }, []);

  const grouped = React.useMemo(() => {
    const map = new Map<string, KbDoc[]>();
    for (const d of docs) {
      const arr = map.get(d.category) ?? [];
      arr.push(d);
      map.set(d.category, arr);
    }
    return map;
  }, [docs]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h1 className="text-3xl font-semibold tracking-tight">Knowledge Base</h1>
          <p className="text-sm text-muted-foreground">
            Documentos que alimentan la redaccion de correos y la clasificacion
            de respuestas. Al guardar, los embeddings se regeneran
            automaticamente.
          </p>
        </div>
        <Button
          onClick={() => setEditor({ mode: "creating" })}
          disabled={editor.mode !== "idle"}
        >
          <Plus className="mr-2 size-4" /> Nuevo documento
        </Button>
      </div>

      {editor.mode === "creating" && (
        <DocEditor
          mode="create"
          initial={NEW_DOC_DEFAULT}
          onCancel={() => setEditor({ mode: "idle" })}
          onSaved={async () => {
            setEditor({ mode: "idle" });
            await refresh();
          }}
        />
      )}

      <div className="space-y-8">
        {CATEGORY_ORDER.map((cat) => {
          const items = grouped.get(cat) ?? [];
          if (items.length === 0) return null;
          const meta = CATEGORY_META[cat];
          return (
            <section key={cat} className="space-y-3">
              <div className="flex items-baseline gap-3">
                <span
                  className={cn(
                    "rounded-md px-2 py-0.5 text-xs font-medium",
                    meta.badgeClass,
                  )}
                >
                  {meta.label}
                </span>
                <span className="text-xs text-muted-foreground">
                  {meta.description}
                </span>
              </div>
              <div className="grid gap-3">
                {items.map((doc) =>
                  editor.mode === "editing" && editor.id === doc.id ? (
                    <DocEditor
                      key={doc.id}
                      mode="edit"
                      initial={doc}
                      onCancel={() => setEditor({ mode: "idle" })}
                      onSaved={async () => {
                        setEditor({ mode: "idle" });
                        await refresh();
                      }}
                    />
                  ) : (
                    <DocRow
                      key={doc.id}
                      doc={doc}
                      onEdit={() => setEditor({ mode: "editing", id: doc.id })}
                      onDeleted={refresh}
                    />
                  ),
                )}
              </div>
            </section>
          );
        })}

        {docs.length === 0 && editor.mode !== "creating" && (
          <Card className="border-dashed">
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              No hay documentos cargados todavia. Pulsa{" "}
              <strong>Nuevo documento</strong> para empezar.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function DocRow({
  doc,
  onEdit,
  onDeleted,
}: {
  doc: KbDoc;
  onEdit: () => void;
  onDeleted: () => Promise<void>;
}) {
  const [deleting, setDeleting] = React.useState(false);

  const handleDelete = async () => {
    if (
      !window.confirm(
        `Eliminar "${doc.titulo}"? Se borraran tambien sus ${doc.n_chunks} chunk(s).`,
      )
    ) {
      return;
    }
    setDeleting(true);
    try {
      const res = await fetch(`/api/kb/${doc.id}`, { method: "DELETE" });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      toast.success(`"${doc.titulo}" eliminado`);
      await onDeleted();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`No se pudo eliminar: ${msg}`);
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-3 space-y-0">
        <div className="space-y-1.5">
          <h2 className="text-lg font-semibold leading-tight">{doc.titulo}</h2>
          <p className="text-xs text-muted-foreground">
            {doc.contenido.length} caracteres · {doc.n_chunks} chunk(s) ·{" "}
            <EmbeddingsAge value={doc.embeddings_updated_at} />
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil className="mr-1.5 size-4" /> Editar
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleDelete}
            disabled={deleting}
            className="text-destructive hover:text-destructive"
          >
            {deleting ? (
              <Loader2 className="mr-1.5 size-4 animate-spin" />
            ) : (
              <Trash2 className="mr-1.5 size-4" />
            )}
            Eliminar
          </Button>
        </div>
      </CardHeader>
    </Card>
  );
}

function DocEditor({
  mode,
  initial,
  onCancel,
  onSaved,
}: {
  mode: "create" | "edit";
  initial: { id?: string; category: string; titulo: string; contenido: string };
  onCancel: () => void;
  onSaved: () => void | Promise<void>;
}) {
  const [category, setCategory] = React.useState(initial.category);
  const [titulo, setTitulo] = React.useState(initial.titulo);
  const [contenido, setContenido] = React.useState(initial.contenido);
  const [busy, setBusy] = React.useState<null | "saving" | "embedding">(null);

  const isEdit = mode === "edit";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!titulo.trim()) {
      toast.error("El titulo no puede ir vacio");
      return;
    }
    setBusy("saving");
    try {
      const url = isEdit ? `/api/kb/${initial.id}` : "/api/kb";
      const method = isEdit ? "PATCH" : "POST";
      // Mostrar feedback de embedding tras el primer round-trip — el server
      // hace insert + reembed atomico, asi que cuando responde ya esta hecho.
      // El estado "embedding" cubre el periodo donde el usuario espera la
      // respuesta del POST/PATCH (el server esta llamando a Voyage).
      setBusy("embedding");
      const res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          category,
          titulo: titulo.trim(),
          contenido,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok && res.status !== 207) {
        throw new Error(body.error ?? `HTTP ${res.status}`);
      }
      if (res.status === 207) {
        toast.warning(
          `Documento ${isEdit ? "actualizado" : "creado"} pero el reembed fallo: ${body.error}`,
        );
      } else if (body.reembed) {
        toast.success(
          `Guardado y embebido en ${(body.reembed.elapsedMs / 1000).toFixed(1)}s — ${body.reembed.nChunks} chunk(s)`,
        );
      } else {
        toast.success("Guardado (sin cambios en contenido, no se reembebió)");
      }
      await onSaved();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      toast.error(`No se pudo guardar: ${msg}`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card>
      <CardContent className="pt-6">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[200px_1fr]">
            <div className="space-y-2">
              <Label htmlFor="kb-category">Categoria</Label>
              <select
                id="kb-category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                disabled={busy !== null}
                className={cn(
                  "h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm",
                  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                )}
              >
                {CATEGORY_ORDER.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_META[c as KbCategory].label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="kb-titulo">Titulo</Label>
              <Input
                id="kb-titulo"
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                disabled={busy !== null}
                placeholder="Ej: Servicios — que hace y que no hace DEMIN"
                required
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="kb-contenido">Contenido (Markdown)</Label>
            <Textarea
              id="kb-contenido"
              value={contenido}
              onChange={(e) => setContenido(e.target.value)}
              disabled={busy !== null}
              rows={20}
              placeholder="# Titulo&#10;&#10;Contenido del documento en Markdown..."
            />
            <p className="text-xs text-muted-foreground">
              {contenido.length} caracteres. Al guardar, el documento se
              chunkea (~2000 chars) y se reembebe con Voyage.
            </p>
          </div>

          <Separator />

          <div className="flex items-center justify-between gap-3">
            <p className="text-xs text-muted-foreground">
              {busy === "embedding"
                ? "Embebiendo… esto puede tardar 5-30s segun rate limit de Voyage."
                : busy === "saving"
                  ? "Guardando…"
                  : isEdit
                    ? "Editar guarda y reembeba si cambio el contenido."
                    : "Crear guarda y reembeba el contenido."}
            </p>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={onCancel}
                disabled={busy !== null}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={busy !== null}>
                {busy !== null && (
                  <Loader2 className="mr-2 size-4 animate-spin" />
                )}
                {isEdit ? "Guardar cambios" : "Crear documento"}
              </Button>
            </div>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function EmbeddingsAge({ value }: { value: string | null }) {
  if (!value) return <span className="text-amber-700 dark:text-amber-400">sin embebir</span>;
  const ts = new Date(value);
  const now = Date.now();
  const seconds = Math.max(0, Math.round((now - ts.getTime()) / 1000));

  let text: string;
  if (seconds < 60) text = `embebido hace ${seconds} s`;
  else if (seconds < 3600) text = `embebido hace ${Math.round(seconds / 60)} min`;
  else if (seconds < 86_400) text = `embebido hace ${Math.round(seconds / 3600)} h`;
  else text = `embebido hace ${Math.round(seconds / 86_400)} d`;

  return <span title={ts.toLocaleString("es-ES")}>{text}</span>;
}

// Suprime el warning de TypeScript si CATEGORY_META no se referencia en este
// scope tras refactor (lo mantengo para tipado defensivo).
void categoryMeta;
