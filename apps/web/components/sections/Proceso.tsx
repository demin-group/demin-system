import SectionHeading from "../ui/SectionHeading";

const pasos = [
  {
    n: "01",
    titulo: "Contacto y visita técnica",
    descripcion: "Hablamos contigo, vemos el espacio en obra y entendemos los plazos del proyecto.",
  },
  {
    n: "02",
    titulo: "Presupuesto detallado",
    descripcion: "Te enviamos presupuesto desglosado con plazos y cronograma. Sin sorpresas, sin partidas escondidas.",
  },
  {
    n: "03",
    titulo: "Inicio según calendario",
    descripcion: "Empezamos el día acordado, con equipo dimensionado al alcance del trabajo.",
  },
  {
    n: "04",
    titulo: "Control de polvo, ruido y seguridad",
    descripcion: "Protegemos accesos, zonas comunes y elementos a conservar. Cumplimos normativa de prevención y coordinamos con la propiedad o la comunidad.",
  },
  {
    n: "05",
    titulo: "Retirada de escombros",
    descripcion: "Carga y transporte a gestor autorizado, con toda la documentación en regla.",
  },
  {
    n: "06",
    titulo: "Entrega del espacio limpio",
    descripcion: "Dejamos el espacio listo para que entre el siguiente gremio. Sin retrabajos, sin pendientes.",
  },
];

export default function Proceso() {
  return (
    <section id="proceso" className="bg-[var(--bg-section)] py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6">
        <SectionHeading
          title="Cómo trabajamos"
          subtitle="Un proceso pensado para que la demolición no sea el cuello de botella de tu obra."
        />

        <ol className="mt-14 grid grid-cols-1 md:grid-cols-3 gap-x-12 gap-y-16">
          {pasos.map((paso) => (
            <li key={paso.n}>
              <div className="text-[var(--accent)] font-semibold text-2xl tracking-tight mb-2">
                {paso.n}
              </div>
              <h3 className="text-lg font-semibold text-[var(--ink-primary)] mb-2">
                {paso.titulo}
              </h3>
              <p className="text-sm text-[var(--ink-secondary)] leading-relaxed">
                {paso.descripcion}
              </p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
