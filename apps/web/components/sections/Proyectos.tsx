"use client";

import Image from "next/image";
import { useState } from "react";
import SectionHeading from "../ui/SectionHeading";
import Lightbox from "../ui/Lightbox";
import { proyectos, type Proyecto } from "@/lib/proyectos";

export default function Proyectos() {
  const [activeProyecto, setActiveProyecto] = useState<Proyecto | null>(null);

  return (
    <section id="proyectos" className="bg-[var(--bg-section)] py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6">
        <SectionHeading
          title="Proyectos"
          subtitle="Una selección de proyectos entregados en Madrid."
        />

        <div className="mt-14 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {proyectos.map((p) => {
            const hasFotos = p.fotos.length > 0;

            if (hasFotos) {
              return (
                <button
                  key={p.slug}
                  type="button"
                  onClick={() => setActiveProyecto(p)}
                  className="group relative aspect-[4/3] overflow-hidden rounded-sm bg-white border border-[var(--border)] flex flex-col cursor-pointer text-left focus:outline-none focus:ring-2 focus:ring-[var(--accent)] hover:shadow-lg transition-shadow"
                  aria-label={`Ver fotos del proyecto en calle ${p.calle}, ${p.barrio}`}
                >
                  <span
                    aria-hidden="true"
                    className="absolute top-0 left-0 h-[2px] w-12 bg-[var(--accent)] z-10"
                  />
                  <div className="relative h-2/3 overflow-hidden bg-[var(--bg-section)]">
                    <Image
                      src={`/proyectos/${p.slug}/${p.fotos[0]}`}
                      alt={`Proyecto en calle ${p.calle}, ${p.barrio}`}
                      fill
                      loading="lazy"
                      quality={80}
                      sizes="(min-width: 1024px) 33vw, (min-width: 768px) 50vw, 100vw"
                      className="object-cover transition-transform duration-500 group-hover:scale-[1.03]"
                    />
                  </div>
                  <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
                    <span className="text-2xl md:text-3xl font-semibold tracking-tight text-[var(--ink-primary)]">
                      {p.calle}
                    </span>
                    <span className="mt-3 text-xs uppercase tracking-[0.18em] text-[var(--ink-secondary)]">
                      {p.barrio} · {p.anio}
                    </span>
                  </div>
                </button>
              );
            }

            return (
              <div
                key={p.slug}
                className="relative aspect-[4/3] overflow-hidden rounded-sm bg-white border border-[var(--border)] flex flex-col items-center justify-center px-6 text-center"
                aria-label={`Proyecto en calle ${p.calle}, ${p.barrio}, ${p.anio}`}
              >
                <span
                  aria-hidden="true"
                  className="absolute top-0 left-0 h-[2px] w-12 bg-[var(--accent)]"
                />
                <span className="text-2xl md:text-3xl font-semibold tracking-tight text-[var(--ink-primary)]">
                  {p.calle}
                </span>
                <span className="mt-3 text-xs uppercase tracking-[0.18em] text-[var(--ink-secondary)]">
                  {p.barrio} · {p.anio}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      <Lightbox
        open={activeProyecto !== null}
        fotos={
          activeProyecto
            ? activeProyecto.fotos.map((f) => ({
                src: `/proyectos/${activeProyecto.slug}/${f}`,
                alt: `Proyecto en calle ${activeProyecto.calle}, ${activeProyecto.barrio}`,
              }))
            : []
        }
        title={activeProyecto ? `Calle ${activeProyecto.calle}` : ""}
        subtitle={
          activeProyecto ? `${activeProyecto.barrio} · ${activeProyecto.anio}` : ""
        }
        onClose={() => setActiveProyecto(null)}
      />
    </section>
  );
}
