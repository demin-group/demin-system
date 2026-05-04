import { Resend } from "resend";

export type LeadNotificationInput = {
  nombre: string;
  empresa: string;
  telefono: string;
  email: string;
  mensaje: string;
};

const DEFAULT_FROM = "DEMIN Group <noreply@send.demingroupmadrid.com>";

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export async function sendLeadNotification(
  lead: LeadNotificationInput,
): Promise<string | null> {
  const apiKey = process.env.RESEND_API_KEY?.trim();
  const to = process.env.CONTACT_NOTIFICATION_EMAIL?.trim();
  const from = process.env.CONTACT_FROM_EMAIL?.trim() || DEFAULT_FROM;

  if (!apiKey) {
    console.warn(
      "[resend] RESEND_API_KEY ausente — omitiendo envío de notificación de lead",
    );
    return null;
  }
  if (!to) {
    console.warn(
      "[resend] CONTACT_NOTIFICATION_EMAIL ausente — omitiendo envío de notificación de lead",
    );
    return null;
  }

  try {
    const resend = new Resend(apiKey);

    const subject = `Nuevo lead — ${lead.nombre}${
      lead.empresa ? ` (${lead.empresa})` : ""
    }`;

    const fecha = new Date().toLocaleString("es-ES", {
      timeZone: "Europe/Madrid",
      dateStyle: "medium",
      timeStyle: "short",
    });

    const nombre = escapeHtml(lead.nombre);
    const empresa = lead.empresa ? escapeHtml(lead.empresa) : "—";
    const telefono = lead.telefono ? escapeHtml(lead.telefono) : "—";
    const email = escapeHtml(lead.email);
    const mensaje = escapeHtml(lead.mensaje).replace(/\n/g, "<br />");

    const html = `<h2>Nuevo lead inbound</h2>
<p><strong>Nombre:</strong> ${nombre}</p>
<p><strong>Empresa:</strong> ${empresa}</p>
<p><strong>Teléfono:</strong> ${telefono}</p>
<p><strong>Email:</strong> <a href="mailto:${email}">${email}</a></p>
<p><strong>Mensaje:</strong></p>
<blockquote style="border-left: 3px solid #B85C2C; padding-left: 12px; margin: 8px 0; color: #525252;">
${mensaje}
</blockquote>
<p style="font-size: 13px; color: #999; margin-top: 24px;">Recibido el ${fecha} desde demingroupmadrid.com</p>`;

    const result = await resend.emails.send({
      from,
      to,
      replyTo: lead.email,
      subject,
      html,
    });

    if (result.error) {
      console.error("[resend]", result.error);
      return null;
    }

    return result.data?.id ?? null;
  } catch (error) {
    console.error("[resend]", error);
    return null;
  }
}
