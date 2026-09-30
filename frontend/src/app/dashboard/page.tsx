"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import {
  ArrowRight, ArrowUpRight, CalendarDays, CheckCircle2, Circle, Hand, Layers, Play, Radar, Send, Trophy,
} from "lucide-react";
import { ApplicationCard } from "@/components/application-card";
import { StatTile, TimelineChart } from "@/components/analytics-charts";
import { TunnelGrid } from "@/components/brand";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { useAgentStatus, useApplications, useIntegrations, useMe, useOverview } from "@/hooks/use-applications";
import { ApiError, fetcher, post } from "@/lib/api-client";
import type { FieldMapping } from "@/lib/types";
import { cn, formatDateTime, timeAgo, titleCase } from "@/lib/utils";

function Onboarding() {
  const { data: me } = useMe();
  const { data: status } = useAgentStatus();
  const { data: integrations } = useIntegrations();
  const { data: answers } = useSWR<{ mappings: FieldMapping[] }>("/users/me/field-mappings", fetcher);
  if (!me || !status) return null;
  const prefs = me.preferences;
  const hasSources = Object.values(prefs.sources || {}).some((v) => (v || []).length) ||
    prefs.platforms.some((p) => ["linkedin", "indeed", "glassdoor", "wellfound", "internships"].includes(p));
  const saved = new Set((answers?.mappings || []).map((m) => m.field_name));
  const steps = [
    { done: status.has_master_resume, label: "Upload your master resume", href: "/dashboard/resume" },
    { done: prefs.target_roles.length > 0, label: "Set target roles & locations", href: "/dashboard/settings?tab=preferences" },
    { done: hasSources && (prefs.sources.internship_lists || []).length > 0 && prefs.platforms.includes("internships"),
      label: "Apply the Internships preset (mass apply)", href: "/dashboard/settings?tab=mass-apply" },
    { done: saved.has("work_authorization") && saved.has("requires_sponsorship"),
      label: "Save work-authorization & visa answers", href: "/dashboard/settings?tab=answers" },
    { done: !!integrations?.google.connected, label: "Connect Gmail & Calendar (optional)", href: "/dashboard/settings?tab=integrations" },
  ];
  const completed = steps.filter((s) => s.done).length;
  if (completed === steps.length) return null;
  return (
    <Card className="mb-8">
      <CardHeader className="flex-row items-end justify-between gap-6 space-y-0">
        <div>
          <CardTitle>Get your agent ready</CardTitle>
          <CardDescription className="mt-2">{completed} of {steps.length} done — kept jobs only auto-submit once your eligibility answers are saved.</CardDescription>
        </div>
        <span className="font-display text-3xl tabular-nums text-primary">{Math.round((completed / steps.length) * 100)}%</span>
      </CardHeader>
      <div className="px-5"><Progress value={(completed / steps.length) * 100} /></div>
      <CardContent className="mt-4 grid gap-px bg-border p-0 sm:grid-cols-2 lg:grid-cols-5">
        {steps.map((s, i) => (
          <Link key={s.label} href={s.href} className="group flex items-start gap-3 bg-card p-4 text-sm transition-colors hover:bg-accent">
            {s.done ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" /> : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />}
            <span className={cn("flex-1", s.done && "text-muted-foreground line-through")}>
              <span className="mr-1 font-mono text-xs text-muted-foreground">0{i + 1}</span> {s.label}
            </span>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

function SwipeBand({ count, onScan, scanning, disabled }: { count: number; onScan: () => void; scanning: boolean; disabled: boolean }) {
  return (
    <div className="relative mb-8 grid overflow-hidden border md:grid-cols-[1fr_auto]">
      <TunnelGrid className="absolute inset-0 opacity-25" animated={false} />
      <div className={cn("relative p-6 sm:p-8", count > 0 && "bg-primary text-primary-foreground")}>
        <p className="label-caps text-[11px] opacity-80">Swipe Review</p>
        <p className="display mt-3 text-3xl sm:text-5xl">
          {count > 0 ? <>{count} {count === 1 ? "job is" : "jobs are"}<br />waiting for you</> : <>Deck is empty.<br />Go find more.</>}
        </p>
      </div>
      <div className="relative flex items-center gap-3 border-t bg-background/80 p-6 backdrop-blur md:border-l md:border-t-0 sm:p-8">
        {count > 0 ? (
          <Link href="/dashboard/review" className={buttonVariants({ size: "xl" })}><Layers /> Start swiping</Link>
        ) : (
          <Button size="xl" onClick={onScan} loading={scanning} disabled={disabled}><Play /> Scan now</Button>
        )}
      </div>
    </div>
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
      toast({ title: "Scan started", description: "New jobs will land in Swipe Review as they're scored.", tone: "success" });
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
        eyebrow="Dashboard"
        title="Overview"
        description={status?.last_scan_at ? `Last scan ${timeAgo(status.last_scan_at)}${status.next_scan_at ? ` · next ${formatDateTime(status.next_scan_at)}` : ""}` : "Your agent hasn't scanned yet."}
        actions={
          <Button onClick={startScan} loading={scanning || !!running} disabled={!status?.has_master_resume}>
            {!running && <Radar />} {running ? "Scanning…" : "Scan for jobs now"}
          </Button>
        }
      />
      <Onboarding />
      {status && <SwipeBand count={status.to_review} onScan={startScan} scanning={scanning || !!running} disabled={!status.has_master_resume} />}

      <div className="grid border sm:grid-cols-2 xl:grid-cols-5 grid-lines">
        {isLoading || !totals ? (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[132px]" />)
        ) : (
          <>
            <StatTile className="border-0" label="Awaiting your approval" value={totals.pending_approval} icon={<Hand className="h-4 w-4" />}
              hint={<Link href="/dashboard/applications?status=pending_approval" className="font-semibold text-primary hover:underline">Review now →</Link>} />
            <StatTile className="border-0" label="Applications sent" value={totals.applied} icon={<Send className="h-4 w-4" />}
              hint={`${status?.applied_today ?? 0} of ${status?.daily_limit ?? 25} today`} />
            <StatTile className="border-0" label="Response rate" value={`${overview.rates.response_rate}%`} icon={<Radar className="h-4 w-4" />}
              hint={overview.rates.avg_days_to_response != null ? `~${overview.rates.avg_days_to_response} days to first reply` : `${totals.responses} responses`} />
            <StatTile className="border-0" label="Interviews" value={totals.interviews} icon={<CalendarDays className="h-4 w-4" />}
              hint={`${overview.rates.interview_rate}% of applications`} />
            <StatTile className="border-0" label="Offers" value={totals.offers} icon={<Trophy className="h-4 w-4" />}
              hint={`${(totals.preparing || 0) + (status?.approved || 0)} more in the pipeline`} />
          </>
        )}
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle>Needs your approval</CardTitle>
              <CardDescription className="mt-2">Filled out and paused — the agent needs an answer only you can give.</CardDescription>
            </div>
            <Link href="/dashboard/applications?status=pending_approval" className={buttonVariants({ variant: "ghost", size: "sm" })}>
              View all <ArrowRight />
            </Link>
          </CardHeader>
          <CardContent className="space-y-2">
            {!pending?.items.length ? (
              <EmptyState icon={Hand} title="Nothing waiting for review"
                description={status?.preparing ? `${status.preparing} kept job(s) are being tailored and filled right now.` : "Keep jobs in Swipe Review — anything the agent can't answer on its own shows up here."} />
            ) : (
              pending.items.map((app) => <ApplicationCard key={app.id} app={app} />)
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Upcoming interviews</CardTitle>
            <CardDescription className="mt-2">Synced to Google Calendar with prep notes</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {!overview?.upcoming_interviews.length && <p className="text-sm text-muted-foreground">No interviews scheduled yet.</p>}
            {overview?.upcoming_interviews.map((i) => (
              <Link key={i.id} href={`/dashboard/interviews?id=${i.id}`} className="group block border p-3 transition-colors hover:border-foreground/60">
                <div className="flex items-center justify-between">
                  <p className="font-semibold">{i.company}</p>
                  <ArrowUpRight className="h-4 w-4 text-muted-foreground group-hover:text-primary" />
                </div>
                <p className="text-sm text-muted-foreground">{i.role}</p>
                <p className="mt-1 text-xs text-muted-foreground">{formatDateTime(i.scheduled_at)} · {titleCase(i.type || "interview")}</p>
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Activity — last 30 days</CardTitle>
            <CardDescription className="mt-2">Jobs discovered, applications submitted and employer responses per day</CardDescription>
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
          <CardContent className="space-y-1">
            {!overview?.recent_runs.length && <p className="text-sm text-muted-foreground">No runs yet.</p>}
            {overview?.recent_runs.slice(0, 6).map((r) => (
              <Link key={r.id} href={`/dashboard/logs?run=${r.id}`} className="flex items-center justify-between border-b border-border/60 px-1 py-2.5 text-sm last:border-0 hover:bg-accent">
                <span className="flex items-center gap-2">
                  <span className={cn("h-2 w-2", r.status === "completed" ? "bg-success" : r.status === "failed" ? "bg-primary" : "animate-pulse-dot bg-warning")} />
                  <span className="font-medium">{titleCase(r.run_type)}</span>
                  {r.run_type === "scan" && <span className="text-xs text-muted-foreground">{r.jobs_discovered} new · {r.jobs_matched} scored</span>}
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
