import Header from "@/components/sections/Header";
import Hero from "@/components/sections/Hero";
import Servicios from "@/components/sections/Servicios";
import Proceso from "@/components/sections/Proceso";
import Valores from "@/components/sections/Valores";
import Proyectos from "@/components/sections/Proyectos";
import Contacto from "@/components/sections/Contacto";
import Footer from "@/components/sections/Footer";
import WhatsAppFloat from "@/components/ui/WhatsAppFloat";
import CookieBanner from "@/components/ui/CookieBanner";
import LocalBusinessJsonLd from "@/components/seo/LocalBusinessJsonLd";

export default function Home() {
  return (
    <>
      <LocalBusinessJsonLd />
      <Header />
      <main>
        <Hero />
        <Servicios />
        <Proceso />
        <Valores />
        <Proyectos />
        <Contacto />
      </main>
      <Footer />
      <WhatsAppFloat />
      <CookieBanner />
    </>
  );
}
