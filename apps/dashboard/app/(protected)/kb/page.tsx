import { PlaceholderPanel } from "@/components/placeholder-panel";

export const metadata = { title: "KB" };

export default function KbPage() {
  return (
    <PlaceholderPanel
      title="Knowledge Base"
      phase="Fase 1"
      description="Editor de documentos del KB: proyectos, FAQs, casos. Embeddings vía pgvector."
    />
  );
}
