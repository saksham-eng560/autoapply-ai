"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useSWRConfig } from "swr";
import {
  BarChart3, Briefcase, CalendarDays, FileText, Inbox, LayoutDashboard, LogOut, Menu, ScrollText, Send, Settings, X,
} from "lucide-react";
import { NotificationBell } from "@/components/notification-bell";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useAgentStatus, useMe } from "@/hooks/use-applications";
import { useWebSocket } from "@/hooks/use-websocket";
import { post } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/applications", label: "Applications", icon: Send, badge: "pending" as const },
  { href: "/dashboard/jobs", label: "Jobs", icon: Briefcase },
  { href: "/dashboard/emails", label: "Emails", icon: Inbox },
  { href: "/dashboard/interviews", label: "Interviews", icon: CalendarDays },
  { href: "/dashboard/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/dashboard/resume", label: "Resume Lab", icon: FileText },
  { href: "/dashboard/logs", label: "Agent Logs", icon: ScrollText },
  { href: "/dashboard/settings", label: "Settings", icon: Settings },
];

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { data: me, isLoading } = useMe();
  const { data: status } = useAgentStatus();
  const { mutate } = useSWRConfig();
  const toast = useToast();
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);

  const live = useWebSocket((event) => {
    if (event.type === "notification") {
      const d = event.data as { title?: string; body?: string; event_type?: string; link?: string };
      toast({ title: d.title || "Update", description: d.body, tone: d.event_type?.includes("error") || d.event_type?.includes("failed") ? "error" : "info" });
      if (document.hidden && "Notification" in window && Notification.permission === "granted") {
        navigator.serviceWorker?.controller?.postMessage({ type: "notify", title: d.title, body: d.body, link: d.link });
      }
      mutate((key) => typeof key === "string" && (key.startsWith("/notifications") || key.startsWith("/agent")));
    }
    if (event.type === "application_updated" || event.type === "agent_run_updated") {
      mutate((key) => typeof key === "string" && (key.startsWith("/applications") || key.startsWith("/agent") || key.startsWith("/analytics") || key.startsWith("/jobs")));
    }
  });

  const logout = async () => {
    await post("/auth/logout");
    router.replace("/login");
  };

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 p-3">
      {NAV.map(({ href, label, icon: Icon, badge }) => {
        const active = href === "/dashboard" ? pathname === href : pathname.startsWith(href);
        return (
          <Link key={href} href={href} onClick={() => setMobileOpen(false)}
            className={cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
              active ? "bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-accent hover:text-foreground")}>
            <Icon className="h-4 w-4" />
            <span className="flex-1">{label}</span>
            {badge === "pending" && !!status?.pending_approval && (
              <span className="rounded-full bg-warning px-1.5 text-[11px] font-semibold text-warning-foreground">{status.pending_approval}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r bg-card lg:flex">
        <Link href="/dashboard" className="flex h-16 items-center gap-2 border-b px-5 font-semibold">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"><FileText className="h-4 w-4" /></div>
          AutoApply AI
        </Link>
        {nav}
        <div className="border-t p-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-2 px-2">
            <span className={cn("h-2 w-2 rounded-full", live ? "bg-success" : "bg-muted-foreground/40")} />
            {live ? "Live updates on" : "Polling for updates"}
          </div>
        </div>
      </aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute left-0 top-0 flex h-full w-64 flex-col bg-card shadow-xl">
            <div className="flex h-16 items-center justify-between border-b px-4 font-semibold">
              AutoApply AI
              <Button variant="ghost" size="icon" onClick={() => setMobileOpen(false)}><X /></Button>
            </div>
            {nav}
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur lg:px-8">
          <Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setMobileOpen(true)} aria-label="Open menu"><Menu /></Button>
          <div className="flex-1" />
          <NotificationBell />
          <ThemeToggle />
          <div className="hidden text-right text-sm sm:block">
            {isLoading ? <Skeleton className="h-4 w-28" /> : <p className="font-medium leading-tight">{me?.full_name}</p>}
            <p className="text-xs text-muted-foreground">{me?.email}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={logout} aria-label="Sign out"><LogOut /></Button>
        </header>
        <main className="flex-1 p-4 lg:p-8">{children}</main>
      </div>
    </div>
  );
}
