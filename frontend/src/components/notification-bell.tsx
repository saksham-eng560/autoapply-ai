"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Bell, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNotifications } from "@/hooks/use-applications";
import { post } from "@/lib/api-client";
import { cn, timeAgo } from "@/lib/utils";

export function NotificationBell() {
  const { data, mutate } = useNotifications();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const markAll = async () => {
    await post("/notifications/read-all");
    mutate();
  };

  return (
    <div className="relative" ref={ref}>
      <Button variant="ghost" size="icon" onClick={() => setOpen((o) => !o)} aria-label="Notifications">
        <Bell />
        {!!data?.unread && (
          <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold text-destructive-foreground">
            {data.unread > 9 ? "9+" : data.unread}
          </span>
        )}
      </Button>
      {open && (
        <div className="absolute right-0 z-40 mt-2 w-96 animate-fade-in rounded-xl border bg-background shadow-xl">
          <div className="flex items-center justify-between border-b px-4 py-3">
            <p className="text-sm font-semibold">Notifications</p>
            <Button variant="ghost" size="sm" onClick={markAll}><Check /> Mark all read</Button>
          </div>
          <div className="max-h-96 overflow-y-auto scrollbar-thin">
            {!data?.items.length && <p className="p-6 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>}
            {data?.items.map((n) => (
              <Link key={n.id} href={n.link || "#"} onClick={() => { setOpen(false); if (!n.is_read) post(`/notifications/${n.id}/read`).then(() => mutate()); }}
                className={cn("block border-b px-4 py-3 text-sm last:border-0 hover:bg-accent", !n.is_read && "bg-primary/5")}>
                <div className="flex items-start gap-2">
                  {!n.is_read && <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-primary" />}
                  <div className="min-w-0">
                    <p className="font-medium">{n.title}</p>
                    {n.body && <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">{n.body}</p>}
                    <p className="mt-1 text-[11px] text-muted-foreground">{timeAgo(n.created_at)}</p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
