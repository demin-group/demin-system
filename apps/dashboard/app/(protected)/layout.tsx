import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { SidebarNav } from "@/components/sidebar-nav";
import { LogoutButton } from "@/components/logout-button";
import { Separator } from "@/components/ui/separator";

export default async function ProtectedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 shrink-0 border-r border-sidebar-border bg-sidebar md:flex md:flex-col">
        <div className="px-5 py-5">
          <p className="text-sm font-semibold tracking-tight text-sidebar-foreground">
            DEMIN
          </p>
          <p className="text-xs text-sidebar-foreground/60">Dashboard</p>
        </div>
        <Separator className="bg-sidebar-border" />
        <div className="flex-1 overflow-y-auto">
          <SidebarNav />
        </div>
        <Separator className="bg-sidebar-border" />
        <div className="px-3 py-3 space-y-2">
          <p className="px-3 text-xs text-sidebar-foreground/60 truncate">
            {user.email}
          </p>
          <LogoutButton />
        </div>
      </aside>
      <main className="flex-1 overflow-x-hidden">
        <div className="mx-auto w-full max-w-6xl p-6 md:p-10">{children}</div>
      </main>
    </div>
  );
}
