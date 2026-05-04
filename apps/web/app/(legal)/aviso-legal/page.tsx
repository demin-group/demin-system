import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Aviso legal — DEMIN Group",
  description: "Información legal y titularidad del sitio web de DEMIN Group.",
  robots: { index: true, follow: true },
};

export default function AvisoLegalPage() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-[var(--ink-primary)] mb-2">
        Aviso legal
      </h1>
      <p className="text-sm text-[var(--ink-secondary)] mb-10">
        Última actualización: 1 de mayo de 2026
      </p>

      <section className="space-y-4 text-[var(--ink-primary)] leading-relaxed">
        <h2 className="text-xl font-semibold mt-8 mb-2">1. Titularidad del sitio</h2>
        <p>
          En cumplimiento del artículo 10 de la Ley 34/2002, de 11 de julio, de Servicios de la Sociedad de la Información y de Comercio Electrónico (LSSI-CE), se informa de los datos identificativos del titular del sitio web:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Titular:</strong> Gonzalo Pérez Sánchez-Marín</li>
          <li><strong>NIF:</strong> 06619073H</li>
          <li><strong>Domicilio:</strong> C/ de Alfonso X, 5 — 28010 Madrid</li>
          <li><strong>Email de contacto:</strong> contacto@demingroupmadrid.com</li>
          <li><strong>Nombre comercial:</strong> DEMIN Group</li>
        </ul>

        <h2 className="text-xl font-semibold mt-8 mb-2">2. Objeto</h2>
        <p>
          El presente aviso legal regula el uso del sitio web <strong>demingroupmadrid.com</strong> (en adelante, &ldquo;el sitio&rdquo;), titularidad del responsable identificado en el apartado anterior. El sitio tiene por finalidad la presentación de los servicios profesionales de demolición interior y vaciado de espacios prestados en la Comunidad de Madrid.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">3. Condiciones de uso</h2>
        <p>
          El acceso al sitio es libre y gratuito. La navegación atribuye la condición de usuario del sitio e implica la aceptación de las condiciones aquí recogidas. El usuario se compromete a hacer un uso adecuado de los contenidos y servicios y a no emplearlos para incurrir en actividades ilícitas, lesivas de derechos de terceros o que de cualquier forma puedan dañar el sitio o impedir su normal uso.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">4. Propiedad intelectual e industrial</h2>
        <p>
          Todos los contenidos del sitio, incluyendo textos, fotografías, diagramas, logotipos, marcas y código, son propiedad del titular o de terceros que han autorizado su uso. Queda prohibida la reproducción, distribución, comunicación pública o transformación, total o parcial, sin autorización expresa por escrito.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">5. Exención de responsabilidad</h2>
        <p>
          El titular procura que la información publicada en el sitio sea veraz y esté actualizada, pero no garantiza la ausencia de errores ni la disponibilidad ininterrumpida del servicio. El titular no asume responsabilidad alguna por los daños y perjuicios derivados del uso del sitio o de la información contenida en él, salvo en los casos en que la ley imponga otra cosa.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">6. Enlaces a sitios de terceros</h2>
        <p>
          El sitio puede contener enlaces a páginas de terceros (redes sociales, servicios de mensajería). El titular no se responsabiliza del contenido ni de las políticas de privacidad de dichos sitios externos.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">7. Legislación aplicable y jurisdicción</h2>
        <p>
          Las presentes condiciones se rigen por la legislación española. Para la resolución de cualquier controversia que pudiera derivarse del uso del sitio, las partes se someten a los Juzgados y Tribunales de Madrid capital, con renuncia expresa a cualquier otro fuero que pudiera corresponderles.
        </p>
      </section>
    </>
  );
}
