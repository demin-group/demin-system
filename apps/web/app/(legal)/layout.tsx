import Header from "@/components/sections/Header";
import Footer from "@/components/sections/Footer";
import CookieBanner from "@/components/ui/CookieBanner";

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Header />
      <main className="bg-white">
        <article className="max-w-3xl mx-auto px-6 py-20 md:py-28 prose-spacing">
          {children}
        </article>
      </main>
      <Footer />
      <CookieBanner />
    </>
  );
}
