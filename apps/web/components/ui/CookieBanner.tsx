"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const STORAGE_KEY = "demin-cookies-ack-v1";

export default function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      const ack = window.localStorage.getItem(STORAGE_KEY);
      if (!ack) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  function accept() {
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // ignore — visitor may have storage disabled
    }
    setVisible(false);
  }

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-label="Aviso de cookies"
      className="fixed bottom-0 inset-x-0 z-40 bg-[var(--brand)] text-white/90 border-t border-white/10"
    >
      <div className="max-w-6xl mx-auto px-6 py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <p className="text-sm leading-relaxed">
          Esta web usa cookies técnicas necesarias.{" "}
          <Link href="/cookies" className="underline hover:text-[var(--accent)] transition-colors">
            Más info
          </Link>
        </p>
        <button
          type="button"
          onClick={accept}
          className="inline-flex items-center justify-center px-5 py-2 text-sm font-semibold text-white bg-[var(--accent)] hover:bg-[var(--accent-hover)] transition-colors rounded-sm whitespace-nowrap"
        >
          Entendido
        </button>
      </div>
    </div>
  );
}
