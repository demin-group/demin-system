import { PlaceholderPanel } from "@/components/placeholder-panel";

export const metadata = { title: "Approval Queue" };

export default function ApprovalQueuePage() {
  return (
    <PlaceholderPanel
      title="Approval Queue"
      phase="Fase 1 (HITL)"
      description="Cola de drafts pendientes de aprobación humana antes de envío."
    />
  );
}
