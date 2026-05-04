import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de privacidad — DEMIN Group",
  description: "Cómo trata DEMIN Group los datos personales recogidos a través de su sitio web.",
  robots: { index: true, follow: true },
};

export default function PrivacidadPage() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-[var(--ink-primary)] mb-2">
        Política de privacidad
      </h1>
      <p className="text-sm text-[var(--ink-secondary)] mb-10">
        Última actualización: 1 de mayo de 2026
      </p>

      <section className="space-y-4 text-[var(--ink-primary)] leading-relaxed">
        <h2 className="text-xl font-semibold mt-8 mb-2">1. Responsable del tratamiento</h2>
        <p>
          El responsable del tratamiento de los datos personales recogidos a través de este sitio es <strong>Gonzalo Pérez Sánchez-Marín</strong> (DEMIN Group), con domicilio en C/ de Alfonso X, 5 — 28010 Madrid. Email de contacto: <a className="underline hover:text-[var(--accent)]" href="mailto:contacto@demingroupmadrid.com">contacto@demingroupmadrid.com</a>.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">2. Finalidad del tratamiento</h2>
        <p>
          Los datos que nos facilites a través del formulario de contacto serán tratados con la única finalidad de gestionar tu consulta y, en su caso, elaborar y remitir un presupuesto. No usamos los datos para envíos comerciales ajenos a la solicitud realizada.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">3. Base jurídica</h2>
        <p>
          La base legal para el tratamiento de tus datos es el <strong>consentimiento</strong> que prestas al enviar el formulario y el <strong>interés legítimo</strong> en responder a tu solicitud. Puedes retirar el consentimiento en cualquier momento sin que ello afecte a la licitud del tratamiento previo.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">4. Plazo de conservación</h2>
        <p>
          Conservamos los datos durante el tiempo necesario para atender tu solicitud y, si esta deriva en una relación profesional, durante los plazos legales aplicables. En caso de no llegar a contratación, los datos se conservarán un máximo de <strong>2 años</strong> y posteriormente serán eliminados.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">5. Destinatarios y encargados de tratamiento</h2>
        <p>
          Para prestar el servicio, los datos personales son tratados por los siguientes encargados de tratamiento:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li><strong>Supabase Inc.</strong> — almacenamiento de los leads en la base de datos (servidores en la Unión Europea, región <code>eu-west-1</code>, Fráncfort).</li>
          <li><strong>Resend Inc.</strong> — envío de la notificación interna a DEMIN al recibir una consulta (infraestructura en la Unión Europea, región <code>eu-west-1</code>, Dublín).</li>
          <li><strong>Vercel Inc.</strong> — hosting del sitio web (CDN global con presencia en la Unión Europea).</li>
        </ul>
        <p>
          El almacenamiento de los datos del formulario se realiza en la Unión Europea. No cedemos los datos a terceros salvo obligación legal.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">6. Tus derechos</h2>
        <p>
          Tienes derecho a acceder a tus datos, rectificarlos, suprimirlos, limitar u oponerte a su tratamiento y a la portabilidad de los mismos. Puedes ejercer estos derechos enviando un correo a <a className="underline hover:text-[var(--accent)]" href="mailto:contacto@demingroupmadrid.com">contacto@demingroupmadrid.com</a>. Asimismo, puedes presentar una reclamación ante la Agencia Española de Protección de Datos (AEPD) si consideras que tus derechos no han sido atendidos: <a className="underline hover:text-[var(--accent)]" href="https://www.aepd.es" target="_blank" rel="noopener noreferrer">www.aepd.es</a>.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">7. Seguridad</h2>
        <p>
          Aplicamos las medidas técnicas y organizativas razonables para proteger tus datos frente a accesos no autorizados, pérdida o alteración.
        </p>
      </section>
    </>
  );
}
