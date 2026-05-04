"use client";

import { useState, type FormEvent } from "react";

type Status = "idle" | "submitting" | "success" | "error";

export default function ContactForm() {
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (status === "submitting") return;

    const form = e.currentTarget;
    const formData = new FormData(form);
    const payload = {
      nombre: String(formData.get("nombre") ?? "").trim(),
      empresa: String(formData.get("empresa") ?? "").trim(),
      telefono: String(formData.get("telefono") ?? "").trim(),
      email: String(formData.get("email") ?? "").trim(),
      mensaje: String(formData.get("mensaje") ?? "").trim(),
      website: String(formData.get("website") ?? ""),
    };

    setStatus("submitting");
    setErrorMsg("");

    try {
      const res = await fetch("/api/contact", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        error?: string;
      };

      if (res.ok && data.ok) {
        setStatus("success");
      } else {
        setStatus("error");
        setErrorMsg(data.error ?? "No hemos podido enviar el mensaje. Inténtalo de nuevo.");
      }
    } catch {
      setStatus("error");
      setErrorMsg("Problema de conexión. Inténtalo de nuevo en un momento.");
    }
  }

  if (status === "success") {
    return (
      <div className="border border-[var(--border)] bg-white p-8 rounded-sm">
        <p className="text-lg font-semibold text-[var(--ink-primary)] mb-2">
          Gracias.
        </p>
        <p className="text-[var(--ink-secondary)] leading-relaxed">
          Te respondemos en menos de 24 horas.
        </p>
      </div>
    );
  }

  const inputClass =
    "w-full px-4 py-3 text-base bg-white border border-[var(--border)] rounded-sm focus:outline-none focus:border-[var(--accent)] focus:ring-1 focus:ring-[var(--accent)] transition-colors text-[var(--ink-primary)] placeholder:text-[var(--ink-secondary)]/60";

  const labelClass =
    "block text-xs uppercase tracking-[0.16em] text-[var(--ink-secondary)] mb-2";

  return (
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <div
        aria-hidden="true"
        style={{ position: "absolute", left: "-10000px", top: "auto", width: "1px", height: "1px", overflow: "hidden" }}
      >
        <label htmlFor="website">No rellenar</label>
        <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
      </div>

      <div>
        <label htmlFor="nombre" className={labelClass}>
          Nombre <span className="text-[var(--accent)]">*</span>
        </label>
        <input
          id="nombre"
          name="nombre"
          type="text"
          required
          autoComplete="name"
          className={inputClass}
          disabled={status === "submitting"}
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
        <div>
          <label htmlFor="empresa" className={labelClass}>
            Empresa
          </label>
          <input
            id="empresa"
            name="empresa"
            type="text"
            autoComplete="organization"
            className={inputClass}
            disabled={status === "submitting"}
          />
        </div>
        <div>
          <label htmlFor="telefono" className={labelClass}>
            Teléfono
          </label>
          <input
            id="telefono"
            name="telefono"
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            className={inputClass}
            disabled={status === "submitting"}
          />
        </div>
      </div>

      <div>
        <label htmlFor="email" className={labelClass}>
          Email <span className="text-[var(--accent)]">*</span>
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          className={inputClass}
          disabled={status === "submitting"}
        />
      </div>

      <div>
        <label htmlFor="mensaje" className={labelClass}>
          Mensaje <span className="text-[var(--accent)]">*</span>
        </label>
        <textarea
          id="mensaje"
          name="mensaje"
          rows={4}
          required
          minLength={10}
          className={`${inputClass} resize-y min-h-[120px]`}
          disabled={status === "submitting"}
          placeholder="Cuéntanos qué necesitas, plazos y dirección de la obra"
        />
      </div>

      <button
        type="submit"
        disabled={status === "submitting"}
        className="w-full inline-flex items-center justify-center px-6 py-3.5 text-base font-semibold text-white bg-[var(--accent)] hover:bg-[var(--accent-hover)] transition-colors rounded-sm disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {status === "submitting" ? "Enviando…" : "Enviar mensaje"}
      </button>

      {status === "error" && (
        <p role="alert" className="text-sm text-red-600">
          {errorMsg}
        </p>
      )}
    </form>
  );
}
