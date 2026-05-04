import SectionHeading from "../ui/SectionHeading";

const valores = [
  {
    titulo: "Plazos que se cumplen.",
    descripcion: "Cuando decimos cuánto tardamos, tardamos eso.",
  },
  {
    titulo: "Limpieza desde el primer día.",
    descripcion: "Protegemos lo que se queda y nos llevamos lo que sobra.",
  },
  {
    titulo: "Comunicación directa.",
    descripcion: "Trato directo, sin intermediarios. Decisiones rápidas.",
  },
  {
    titulo: "Normativa al día.",
    descripcion: "Gestión de residuos legalizada, documentación en regla.",
  },
  {
    titulo: "Especializados.",
    descripcion: "Solo hacemos demoliciones interiores. Es lo que sabemos.",
  },
];

export default function Valores() {
  return (
    <section className="bg-[var(--bg-primary)] py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6">
        <SectionHeading
          title="Por qué DEMIN"
          subtitle="Trabajamos como nos gustaría que trabajaran con nosotros."
        />
        <div className="mt-14 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8 lg:gap-6">
          {valores.map((v) => (
            <div key={v.titulo} className="border-t-2 border-[var(--ink-primary)] pt-5">
              <h3 className="text-base font-semibold text-[var(--ink-primary)] mb-2 leading-snug">
                {v.titulo}
              </h3>
              <p className="text-sm text-[var(--ink-secondary)] leading-relaxed">
                {v.descripcion}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
