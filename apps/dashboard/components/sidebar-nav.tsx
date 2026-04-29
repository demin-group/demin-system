"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  CheckCircle2,
  Inbox,
  BookOpen,
  BarChart3,
  Settings as SettingsIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

const NAV = [
  { href: "/pipeline", label: "Pipeline", icon: LayoutDashboard },
  { href: "/approval-queue", label: "Approval Queue", icon: CheckCircle2 },
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/kb", label: "KB", icon: BookOpen },
  { href: "/metrics", label: "Metrics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: SettingsIcon },
] as const;

export function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav className="flex flex-col gap-1 p-3" aria-label="Navegación principal">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active =
          pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
            )}
          >
            <Icon className="size-4" aria-hidden />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
