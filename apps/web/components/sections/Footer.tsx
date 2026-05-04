import Link from "next/link";
import Image from "next/image";
import { InstagramIcon, LinkedInIcon } from "../icons/SocialIcons";

export default function Footer() {
  return (
    <footer className="bg-[var(--brand)] text-white/85">
      <div className="max-w-6xl mx-auto px-6 py-14">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 md:gap-8 items-start">
          <div>
            <Image
              src="/logo-demin.jpg"
              alt="DEMIN Group"
              width={180}
              height={180}
              className="w-32 h-auto mb-4"
              loading="lazy"
            />
            <p className="text-sm text-white/70 leading-relaxed max-w-xs">
              La fase cero de tu reforma.
            </p>
          </div>

          <nav className="flex flex-col gap-3 md:items-center" aria-label="Enlaces legales">
            <Link href="/aviso-legal" className="text-sm text-white/80 hover:text-[var(--accent)] transition-colors">
              Aviso legal
            </Link>
            <Link href="/privacidad" className="text-sm text-white/80 hover:text-[var(--accent)] transition-colors">
              Privacidad
            </Link>
            <Link href="/cookies" className="text-sm text-white/80 hover:text-[var(--accent)] transition-colors">
              Cookies
            </Link>
          </nav>

          <div className="flex flex-col gap-4 md:items-end">
            <div className="flex items-center gap-5">
              <a
                href="https://www.instagram.com/demin.group/"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Instagram de DEMIN Group"
                className="text-white/80 hover:text-[var(--accent)] transition-colors"
              >
                <InstagramIcon className="w-5 h-5" />
              </a>
              <a
                href="https://www.linkedin.com/company/demin-group/"
                target="_blank"
                rel="noopener noreferrer"
                aria-label="LinkedIn de DEMIN Group"
                className="text-white/80 hover:text-[var(--accent)] transition-colors"
              >
                <LinkedInIcon className="w-5 h-5" />
              </a>
            </div>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-white/10 text-xs text-white/60">
          © 2026 DEMIN Group · Madrid
        </div>
      </div>
    </footer>
  );
}
