import SectionHeading from "../ui/SectionHeading";
import ContactForm from "../ui/ContactForm";
import { InstagramIcon, LinkedInIcon } from "../icons/SocialIcons";

export default function Contacto() {
  return (
    <section id="contacto" className="bg-[var(--bg-primary)] py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-6">
        <SectionHeading
          title="¿Tienes una obra que arranca pronto?"
          subtitle="Cuéntanos qué necesitas y te respondemos en menos de 24 horas."
        />

        <div className="mt-14 grid grid-cols-1 lg:grid-cols-2 gap-12 lg:gap-16 items-start">
          <ContactForm />

          <div className="border-l-0 lg:border-l border-[var(--border)] lg:pl-12">
            <dl className="space-y-8 text-[var(--ink-primary)]">
              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-[var(--ink-secondary)] mb-2">
                  Dirección
                </dt>
                <dd className="text-base leading-relaxed">
                  DEMIN Group
                  <br />
                  C/ de Alfonso X, 5
                  <br />
                  28010 Madrid
                </dd>
              </div>

              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-[var(--ink-secondary)] mb-2">
                  Teléfono / WhatsApp
                </dt>
                <dd>
                  <a
                    href="tel:+34692319217"
                    className="text-base hover:text-[var(--accent)] transition-colors"
                  >
                    +34 692 319 217
                  </a>
                </dd>
              </div>

              <div>
                <dt className="text-xs uppercase tracking-[0.18em] text-[var(--ink-secondary)] mb-2">
                  Email
                </dt>
                <dd>
                  <a
                    href="mailto:contacto@demingroupmadrid.com"
                    className="text-base hover:text-[var(--accent)] transition-colors break-all"
                  >
                    contacto@demingroupmadrid.com
                  </a>
                </dd>
              </div>

              <div className="pt-2">
                <div className="flex items-center gap-5">
                  <a
                    href="https://www.instagram.com/demin.group/"
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="Instagram de DEMIN Group"
                    className="text-[var(--ink-secondary)] hover:text-[var(--accent)] transition-colors"
                  >
                    <InstagramIcon className="w-5 h-5" />
                  </a>
                  <a
                    href="https://www.linkedin.com/company/demin-group/"
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="LinkedIn de DEMIN Group"
                    className="text-[var(--ink-secondary)] hover:text-[var(--accent)] transition-colors"
                  >
                    <LinkedInIcon className="w-5 h-5" />
                  </a>
                </div>
              </div>
            </dl>
          </div>
        </div>
      </div>
    </section>
  );
}
