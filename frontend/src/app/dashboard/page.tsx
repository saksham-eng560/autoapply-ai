"use client";

import Link from "next/link";
import { useState } from "react";
import {
  ArrowRight, CalendarDays, CheckCircle2, Circle, Hand, Play, Radar, Send, Sparkles, Trophy,
} from "lucide-react";
import { ApplicationCard } from "@/components/application-card";
import { StatTile, TimelineChart } from "@/components/analytics-charts";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useAgentStatus, useApplications, useIntegrations, useMe, useOverview } from "@/hooks/use-applications";
import { ApiError, post } from "@/lib/api-client";
import { cn, formatDateTime, timeAgo, titleCase } from "@/lib/utils";

function Onboarding() {
  const { data: me } = useMe();
  const { data: status } = useAgentStatus();
  const { data: integrations } = useIntegrations();
  if (!me || !status) return null;
  const prefs = me.preferences;
  const hasSources = Object.values(prefs.sources || {}).some((v) => v.length) ||
    prefs.platforms.some((p) => ["linkedin", "indeed", "glassdoor", "wellfound"].includes(p));
  const steps = [
    { done: status.has_master_resume, label: "Upload your master resume", href: "/dashboard/resume" },
    { done: prefs.target_roles.length > 0, label: "Set target roles & locations", href: "/dashboard/settings" },
    { done: hasSources, label: "Choose job sources (boards, companies, career pages)", href: "/dashboard/settings?tab=sources" },
    { done: !!integrations?.google.connected, label: "Connect Gmail & Calendar (optional)", href: "/dashboard/settings?tab=integrations" },
    { done: !!integrations?.linkedin.connected, label: "Sync LinkedIn via the Chrome extension (optional)", href: "/dashboard/settings?tab=integrations" },
  ];
  const completed = steps.filter((s) => s.done).length;
  if (completed === steps.length) return null;
  return (
    <Card className="mb-6 border-primary/30 bg-primary/5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /> Get your agent ready</CardTitle>
        <CardDescription>{completed} of {steps.length} steps complete</CardDescription>
        <Progress value={(completed / steps.length) * 100} className="mt-2" />
      </CardHeader>
      <CardContent className="grid gap-2 sm:grid-cols-2">
        {steps.map((s) => (
          <Link key={s.label} href={s.href} className="flex items-center gap-2 rounded-lg p-2 text-sm hover:bg-background">
            {s.done ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Circle className="h-4 w-4 text-muted-foreground" />}
            <span className={cn(s.done && "text-muted-foreground line-through")}>{s.label}</span>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

export default function OverviewPage() {
  const toast = useToast();
  const { data: status, mutate: refreshStatus } = useAgentStatus();
  const { data: overview, isLoading } = useOverview();
  const { data: pending } = useApplications({ status: "pending_approval", page_size: 5, sort: "match" });
  const [scanning, setScanning] = useState(false);

  const running = status?.running_runs.find((r) => r.run_type === "scan");

  const startScan = async () => {
    setScanning(true);
    try {
      await post("/agent/start-scan", {});
      toast({ title: "Scan started", description: "The agent is searching your job sources.", tone: "success" });
      refreshStatus();
    } catch (err) {
      toast({ title: "Could not start scan", description: err instanceof ApiError ? err.message : String(err), tone: "error" });
    } finally {
      setScanning(false);
    }
  };

  const totals = overview?.totals;
  return (
    <div>
      <PageHeader
        title="Overview"
        description={status?.last_scan_at ? `Last scan ${timeAgo(status.last_scan_at)}${status.next_scan_at ? ` · next ${formatDateTime(status.next_scan_at)}` : ""}` : "Your agent hasn't scanned yet"}
        actions={
          <Button onClick={startScan} loading={scanning || !!running} disabled={!status?.has_master_resume}>
            {!running && <Play />} {running ? "Scanning…" : "Scan for jobs now"}
          </Button>
        }
      />
      <Onboarding />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {isLoading || !totals ? (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[104px] rounded-xl" />)
        ) : (
          <>
            <StatTile label="Awaiting your approval" value={totals.pending_approval} icon={<Hand className="h-4 w-4" />}
              hint={<Link href="/dashboard/applications?status=pending_approval" className="text-primary hover:underline">Review now →</Link>}
              className={totals.pending_approval ? "border-warning/60" : undefined} />
            <StatTile label="Applications sent" value={totals.applied} icon={<Send className="h-4 w-4" />}
              hint={`${status?.applied_today ?? 0} of ${status?.daily_limit ?? 25} today`} />
            <StatTile label="Response rate" value={`${overview.rates.response_rate}%`} icon={<Radar className="h-4 w-4" />}
              hint={overview.rates.avg_days_to_response != null ? `~${overview.rates.avg_days_to_response} days to first reply` : `${totals.responses} responses`} />
            <StatTile label="Interviews" value={totals.interviews} icon={<CalendarDays className="h-4 w-4" />}
              hint={`${overview.rates.interview_rate}% of applications`} />
            <StatTile label="Offers" value={totals.offers} icon={<Trophy className="h-4 w-4" />}
              hint={`${totals.matched + totals.preparing} more in the pipeline`} />
          </>
        )}
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Needs your approval</CardTitle>
              <CardDescription>Filled out and paused — nothing is sent until you approve.</CardDescription>
            </div>
            <Link href="/dashboard/applications?status=pending_approval" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              View all <ArrowRight />
            </Link>
          </CardHeader>
          <CardContent className="space-y-3">
            {!pending?.items.length ? (
              <EmptyState icon={Hand} title="Nothing waiting for review"
                description={status?.preparing ? `${status.preparing} application(s) are being prepared right now.` : "Run a scan — matched jobs will appear here once they're tailored and filled out."} />
            ) : (
              pending.items.map((app) => <ApplicationCard key={app.id} app={app} />)
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Upcoming interviews</CardTitle>
            <CardDescription>Synced to Google Calendar with prep notes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!overview?.upcoming_interviews.length && <p className="text-sm text-muted-foreground">No interviews scheduled yet.</p>}
            {overview?.upcoming_interviews.map((i) => (
              <Link key={i.id} href={`/dashboard/interviews?id=${i.id}`} className="block rounded-lg border p-3 hover:bg-accent">
                <p className="font-medium">{i.company}</p>
                <p className="text-sm text-muted-foreground">{i.role}</p>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(i.scheduled_at)} · {titleCase(i.type || "interview")}</p>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Activity — last 30 days</CardTitle>
            <CardDescription>Jobs discovered, applications submitted and employer responses per day</CardDescription>
          </CardHeader>
          <CardContent>
            {overview ? <TimelineChart data={overview.timeline} /> : <Skeleton className="h-[260px]" />}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle>Recent agent runs</CardTitle>
            <Link href="/dashboard/logs" className={buttonVariants({ variant: "ghost", size: "sm" })}>Logs <ArrowRight /></Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {!overview?.recent_runs.length && <p className="text-sm text-muted-foreground">No runs yet.</p>}
            {overview?.recent_runs.slice(0, 6).map((r) => (
              <Link key={r.id} href={`/dashboard/logs?run=${r.id}`} className="flex items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-accent">
                <span className="flex items-center gap-2">
                  <span className={cn("h-2 w-2 rounded-full", r.status === "completed" ? "bg-success" : r.status === "failed" ? "bg-destructive" : "bg-warning")} />
                  {titleCase(r.run_type)}
                  {r.run_type === "scan" && <span className="text-xs text-muted-foreground">{r.jobs_discovered} new · {r.jobs_matched} matched</span>}
                </span>
                <span className="text-xs text-muted-foreground">{timeAgo(r.started_at)}</span>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
