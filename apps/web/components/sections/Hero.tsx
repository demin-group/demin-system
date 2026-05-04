export default function Hero() {
  return (
    <section className="relative min-h-[85vh] flex items-center overflow-hidden">
      <video
        src="/videos/hero-demolicion.mp4"
        poster="/obras/hero-boveda-ladrillo.jpg"
        autoPlay
        muted
        loop
        playsInline
        preload="metadata"
        aria-hidden="true"
        className="absolute inset-0 w-full h-full object-cover"
      />
      <div className="absolute inset-0 bg-black/55" aria-hidden="true" />

      <div className="relative max-w-6xl mx-auto px-6 py-24 md:py-32 w-full">
        <div className="max-w-3xl">
          <h1 className="text-5xl md:text-6xl lg:text-7xl font-semibold tracking-tight text-white leading-[1.05]">
            La fase cero de tu reforma, sin contratiempos.
          </h1>
          <p className="mt-6 md:mt-8 text-base md:text-lg text-white/85 max-w-2xl leading-relaxed">
            Demoliciones interiores en Madrid. Vaciamos el espacio, retiramos los escombros y entregamos la obra lista para que tu equipo empiece a construir desde el primer día.
          </p>
          <div className="mt-10 flex flex-col sm:flex-row gap-3 sm:gap-4">
            <a
              href="#contacto"
              className="inline-flex items-center justify-center px-7 py-3.5 text-base font-semibold text-white bg-[var(--accent)] hover:bg-[var(--accent-hover)] transition-colors rounded-sm"
            >
              Solicitar presupuesto
            </a>
            <a
              href="https://wa.me/34692319217?text=Hola%2C%20os%20escribo%20desde%20la%20web%20de%20DEMIN%20Group"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2.5 px-7 py-3.5 text-base font-semibold text-white bg-[#25D366] hover:bg-[#1FB855] rounded-sm transition-colors"
            >
              <svg
                viewBox="0 0 24 24"
                width="20"
                height="20"
                fill="#FFFFFF"
                aria-hidden="true"
                style={{ display: "block" }}
              >
                <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448L.057 24zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z" />
              </svg>
              WhatsApp
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
