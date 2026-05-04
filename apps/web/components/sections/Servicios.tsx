import SectionHeading from "../ui/SectionHeading";

const servicios = [
  {
    titulo: "Demolición interior",
    descripcion:
      "Desmontaje de tabiquería, falsos techos, suelos, revestimientos y carpintería. Trabajamos sobre la estructura existente sin comprometer elementos portantes. Para vaciados completos antes de reforma integral.",
  },
  {
    titulo: "Vaciado técnico de locales",
    descripcion:
      "Locales comerciales, oficinas y plantas industriales. Retirada de instalaciones obsoletas, mobiliario fijo y elementos divisorios. Entregamos el espacio diáfano y listo para el nuevo proyecto.",
  },
  {
    titulo: "Retirada y gestión de escombros",
    descripcion:
      "Carga, transporte y depósito en gestor autorizado. Toda la documentación de gestión de residuos legalizada conforme a la normativa de la Comunidad de Madrid.",
  },
  {
    titulo: "Limpieza final de obra",
    descripcion:
      "Eliminación de polvo, restos y residuos tras la demolición. Entregamos el espacio en condiciones para que el siguiente gremio entre directamente, sin trabajo previo.",
  },
];

export default function Servicios() {
  return (
    <section id="servicios" className="bg-[var(--bg-primary)] py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6">
        <SectionHeading
          title="Servicios"
          subtitle="Lo que hacemos antes de que entren los gremios."
        />
        <div className="mt-14 grid grid-cols-1 md:grid-cols-2 gap-6">
          {servicios.map((s) => (
            <article
              key={s.titulo}
              className="group relative p-8 border border-[var(--border)] bg-white rounded-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-[0_4px_20px_-8px_rgba(0,0,0,0.08)]"
            >
              <span
                aria-hidden="true"
                className="absolute top-0 left-0 h-[2px] w-12 bg-[var(--accent)]"
              />
              <h3 className="text-xl font-semibold text-[var(--ink-primary)] mb-3">
                {s.titulo}
              </h3>
              <p className="text-[var(--ink-secondary)] leading-relaxed">
                {s.descripcion}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
