import { PlaceholderPanel } from "@/components/placeholder-panel";

export const metadata = { title: "Inbox" };

export default function InboxPage() {
  return (
    <PlaceholderPanel
      title="Inbox"
      phase="Fase 1"
      description="Respuestas entrantes clasificadas (interesado, no interesado, opt-out, etc.) con sugerencias de respuesta."
    />
  );
}
