import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de cookies — DEMIN Group",
  description: "Cookies utilizadas en el sitio web de DEMIN Group.",
  robots: { index: true, follow: true },
};

export default function CookiesPage() {
  return (
    <>
      <h1 className="text-3xl md:text-4xl font-semibold tracking-tight text-[var(--ink-primary)] mb-2">
        Política de cookies
      </h1>
      <p className="text-sm text-[var(--ink-secondary)] mb-10">
        Última actualización: 1 de mayo de 2026
      </p>

      <section className="space-y-4 text-[var(--ink-primary)] leading-relaxed">
        <h2 className="text-xl font-semibold mt-8 mb-2">1. ¿Qué son las cookies?</h2>
        <p>
          Una cookie es un pequeño fichero de información que un sitio web descarga en tu navegador cuando lo visitas. Sirven para que el sitio recuerde determinadas preferencias y mejore tu experiencia de uso.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">2. Cookies que usamos</h2>
        <p>
          Este sitio utiliza únicamente <strong>cookies técnicas necesarias</strong> para su funcionamiento. En concreto, almacenamos en tu navegador (mediante <code>localStorage</code>) la confirmación de que has cerrado el aviso de cookies, para no volver a mostrártelo.
        </p>
        <p>
          <strong>No usamos cookies de análisis, publicidad ni de seguimiento de terceros.</strong> No empleamos Google Analytics, Meta Pixel ni servicios similares.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">3. Cómo gestionar las cookies</h2>
        <p>
          Puedes borrar el almacenamiento del navegador desde la configuración del mismo. Al hacerlo, el aviso de cookies volverá a mostrarse en tu próxima visita.
        </p>

        <h2 className="text-xl font-semibold mt-8 mb-2">4. Cambios en esta política</h2>
        <p>
          Si en el futuro incorporáramos cookies adicionales, actualizaríamos esta página y solicitaríamos tu consentimiento previo cuando legalmente proceda.
        </p>
      </section>
    </>
  );
}
