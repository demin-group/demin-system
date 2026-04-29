import { LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";

export function LogoutButton() {
  return (
    <form action="/auth/logout" method="post">
      <Button
        type="submit"
        variant="ghost"
        size="sm"
        className="w-full justify-start gap-2 text-sidebar-foreground/80 hover:text-sidebar-foreground"
      >
        <LogOut className="size-4" aria-hidden />
        Cerrar sesión
      </Button>
    </form>
  );
}
