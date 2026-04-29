import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Props = {
  title: string;
  phase: string;
  description: string;
};

export function PlaceholderPanel({ title, phase, description }: Props) {
  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      <Card className="border-dashed">
        <CardHeader>
          <CardTitle className="text-lg">Próximamente — {phase}</CardTitle>
          <CardDescription>
            Esta sección se construye en {phase}. El skeleton del dashboard
            (auth, navegación, layout) ya está listo.
          </CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Si necesitas referencias del contenido planeado para esta vista,
          consulta <code className="font-mono">tasks/todo.md</code>.
        </CardContent>
      </Card>
    </div>
  );
}
