import Link from "next/link";
import { AlertTriangle, Building2, MapPin } from "lucide-react";
import { JobMatchBadge } from "@/components/job-match-badge";
import { StatusBadge } from "@/components/status-badge";
import type { ApplicationSummary } from "@/lib/types";
import { PLATFORM_LABELS, timeAgo } from "@/lib/utils";

export function ApplicationCard({ app }: { app: ApplicationSummary }) {
  const job = app.job;
  return (
    <Link href={`/dashboard/applications/${app.id}`}
      className="flex items-center gap-4 rounded-xl border bg-card p-4 shadow-sm transition-colors hover:border-primary/40 hover:bg-accent/40">
      <JobMatchBadge score={app.match_score} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate font-medium">{job?.role_title}</p>
          {app.needs_manual_review && <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-label="Needs review" />}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1"><Building2 className="h-3 w-3" />{job?.company_name}</span>
          {job?.location && <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" />{job.location}{job.is_remote ? " · Remote" : ""}</span>}
          <span>{PLATFORM_LABELS[job?.source_platform || ""] || job?.source_platform}</span>
          <span>updated {timeAgo(app.updated_at)}</span>
        </div>
      </div>
      <StatusBadge status={app.status} />
    </Link>
  );
}
