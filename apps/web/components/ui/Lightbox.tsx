"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";

export type Foto = {
  src: string;
  alt: string;
};

type Props = {
  fotos: Foto[];
  open: boolean;
  initialIndex?: number;
  title?: string;
  subtitle?: string;
  onClose: () => void;
};

export default function Lightbox({
  fotos,
  open,
  initialIndex = 0,
  title,
  subtitle,
  onClose,
}: Props) {
  const [activeIndex, setActiveIndex] = useState(initialIndex);
  const dialogRef = useRef<HTMLDialogElement | null>(null);

  useEffect(() => {
    if (open) setActiveIndex(initialIndex);
  }, [open, initialIndex]);

  const next = useCallback(() => {
    if (fotos.length === 0) return;
    setActiveIndex((curr) => (curr + 1) % fotos.length);
  }, [fotos.length]);

  const prev = useCallback(() => {
    if (fotos.length === 0) return;
    setActiveIndex((curr) => (curr - 1 + fotos.length) % fotos.length);
  }, [fotos.length]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open) {
      if (!dialog.open) dialog.showModal();
    } else {
      if (dialog.open) dialog.close();
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") prev();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, next, prev]);

  function handleBackdropClick(e: React.MouseEvent<HTMLDialogElement>) {
    if (e.target === dialogRef.current) onClose();
  }

  const activeFoto = fotos[activeIndex];
  const hasMultiple = fotos.length > 1;

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onClick={handleBackdropClick}
      className="m-0 p-0 max-w-none max-h-none w-screen h-screen bg-transparent border-0"
      aria-label={title ?? "Galería ampliada"}
    >
      {open && activeFoto && (
        <div className="relative w-full h-full flex flex-col p-6 md:p-12">
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="absolute top-4 right-4 md:top-6 md:right-6 text-white/90 hover:text-white p-2 z-10"
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>

          {hasMultiple && (
            <>
              <button
                type="button"
                onClick={prev}
                aria-label="Foto anterior"
                className="absolute left-2 md:left-6 top-1/2 -translate-y-1/2 text-white/80 hover:text-white p-3 z-10"
              >
                <svg
                  width="32"
                  height="32"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>

              <button
                type="button"
                onClick={next}
                aria-label="Foto siguiente"
                className="absolute right-2 md:right-6 top-1/2 -translate-y-1/2 text-white/80 hover:text-white p-3 z-10"
              >
                <svg
                  width="32"
                  height="32"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </button>
            </>
          )}

          <div className="relative flex-1 min-h-0 w-full max-w-6xl mx-auto">
            <Image
              src={activeFoto.src}
              alt={activeFoto.alt}
              fill
              quality={90}
              sizes="100vw"
              className="object-contain"
            />
          </div>

          {(title || subtitle) && (
            <div className="w-full max-w-6xl mx-auto pt-6 md:pt-8 text-center text-white/90 shrink-0">
              <div className="text-sm md:text-base">
                {title}
                {title && subtitle && <span className="text-white/50"> · </span>}
                {subtitle}
              </div>
              {hasMultiple && (
                <div className="mt-2 text-xs text-white/60 tabular-nums">
                  {activeIndex + 1} / {fotos.length}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </dialog>
  );
}
