"use client";

import { useEffect, useState } from "react";

export default function WhatsAppFloat() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = window.setTimeout(() => setVisible(true), 800);
    return () => window.clearTimeout(t);
  }, []);

  if (!visible) return null;

  return (
    <>
      <style>{`
        #demin-whatsapp-float {
          position: fixed !important;
          bottom: 1.5rem !important;
          right: 1.5rem !important;
          width: 3.5rem !important;
          height: 3.5rem !important;
          display: flex !important;
          align-items: center !important;
          justify-content: center !important;
          border-radius: 9999px !important;
          background-color: #25D366 !important;
          color: #FFFFFF !important;
          opacity: 1 !important;
          filter: none !important;
          mix-blend-mode: normal !important;
          backdrop-filter: none !important;
          isolation: isolate !important;
          z-index: 9999 !important;
          box-shadow: 0 6px 20px rgba(37, 211, 102, 0.45) !important;
          transition: background-color 150ms ease-out, transform 150ms ease-out, box-shadow 150ms ease-out !important;
          text-decoration: none !important;
          color-scheme: only light !important;
        }
        #demin-whatsapp-float:hover {
          background-color: #1FB855 !important;
          box-shadow: 0 8px 28px rgba(37, 211, 102, 0.6) !important;
          transform: scale(1.05) !important;
        }
        #demin-whatsapp-float svg {
          display: block !important;
          width: 28px !important;
          height: 28px !important;
        }
        #demin-whatsapp-float svg path {
          fill: #FFFFFF !important;
        }
      `}</style>
      <a
        id="demin-whatsapp-float"
        href="https://wa.me/34692319217?text=Hola%2C%20os%20escribo%20desde%20la%20web%20de%20DEMIN%20Group"
        target="_blank"
        rel="noopener noreferrer"
        aria-label="Escribir por WhatsApp"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M.057 24l1.687-6.163c-1.041-1.804-1.588-3.849-1.587-5.946.003-6.556 5.338-11.891 11.893-11.891 3.181.001 6.167 1.24 8.413 3.488 2.245 2.248 3.481 5.236 3.48 8.414-.003 6.557-5.338 11.892-11.893 11.892-1.99-.001-3.951-.5-5.688-1.448L.057 24zm6.597-3.807c1.676.995 3.276 1.591 5.392 1.592 5.448 0 9.886-4.434 9.889-9.885.002-5.462-4.415-9.89-9.881-9.892-5.452 0-9.887 4.434-9.889 9.884-.001 2.225.651 3.891 1.746 5.634l-.999 3.648 3.742-.981zm11.387-5.464c-.074-.124-.272-.198-.57-.347-.297-.149-1.758-.868-2.031-.967-.272-.099-.47-.149-.669.149-.198.297-.768.967-.941 1.165-.173.198-.347.223-.644.074-.297-.149-1.255-.462-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.521.151-.172.2-.296.3-.495.099-.198.05-.372-.025-.521-.075-.148-.669-1.611-.916-2.206-.242-.579-.487-.501-.669-.51l-.57-.01c-.198 0-.52.074-.792.372s-1.04 1.016-1.04 2.479 1.065 2.876 1.213 3.074c.149.198 2.095 3.2 5.076 4.487.709.306 1.263.489 1.694.626.712.226 1.36.194 1.872.118.571-.085 1.758-.719 2.006-1.413.248-.695.248-1.29.173-1.414z" />
        </svg>
      </a>
    </>
  );
}
