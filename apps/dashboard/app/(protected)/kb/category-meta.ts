/**
 * Mapeo de categorias del KB a etiqueta humana en espanol y color visual.
 * Las 8 categorias son las del schema (§6.2 todo.md). El color se usa en
 * badges/cabeceras de la pantalla /kb para que Gonzalo distinga rapido.
 *
 * Tailwind classes precomputadas: el JIT no descubre clases interpoladas,
 * asi que el mapping va con strings literales.
 */

export type KbCategory =
  | "servicios"
  | "icp"
  | "objeciones"
  | "casos_exito"
  | "tono"
  | "diferenciador"
  | "correos_gonzalo"
  | "otro";

type Meta = {
  label: string;
  badgeClass: string;
  description: string;
};

export const CATEGORY_META: Record<KbCategory, Meta> = {
  servicios: {
    label: "Servicios",
    badgeClass: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200",
    description: "Que hace y que no hace DEMIN.",
  },
  icp: {
    label: "Cliente ideal",
    badgeClass: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-200",
    description: "Quien es el buen cliente y quien no.",
  },
  objeciones: {
    label: "Objeciones",
    badgeClass: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200",
    description: "Como Gonzalo responde a frenos del prospecto.",
  },
  casos_exito: {
    label: "Casos reales",
    badgeClass: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-200",
    description: "Material concreto con permisos de uso.",
  },
  tono: {
    label: "Tono",
    badgeClass: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200",
    description: "Como escribe Gonzalo y como NO escribe.",
  },
  diferenciador: {
    label: "Diferenciador",
    badgeClass: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200",
    description: "Por que DEMIN encaja con quien le contrata.",
  },
  correos_gonzalo: {
    label: "Correos de Gonzalo",
    badgeClass: "bg-stone-100 text-stone-800 dark:bg-stone-900 dark:text-stone-200",
    description: "Standby permanente (Leccion 11).",
  },
  otro: {
    label: "Otro",
    badgeClass: "bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-200",
    description: "Material que no encaja en las 7 anteriores.",
  },
};

export const CATEGORY_ORDER: KbCategory[] = [
  "servicios",
  "icp",
  "objeciones",
  "casos_exito",
  "tono",
  "diferenciador",
  "correos_gonzalo",
  "otro",
];

export function categoryMeta(c: string): Meta {
  return CATEGORY_META[c as KbCategory] ?? CATEGORY_META.otro;
}
