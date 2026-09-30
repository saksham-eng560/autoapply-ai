"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Search, Send } from "lucide-react";
import { ApplicationCard } from "@/components/application-card";
import { EmptyState } from "@/components/empty-state";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplications } from "@/hooks/use-applications";
import { STATUS_LABELS, cn } from "@/lib/utils";
import type { ApplicationStatus } from "@/lib/types";

const FILTERS: { key: string; label: string; statuses?: string }[] = [
  { key: "all", label: "All active" },
  { key: "pending_approval", label: "Needs approval", statuses: "pending_approval" },
  { key: "in_progress", label: "In progress", statuses: "preparing,approved" },
  { key: "applied", label: "Applied", statuses: "applied,acknowledged" },
  { key: "interviewing", label: "Interviewing", statuses: "screening,interview,assessment,final_round" },
  { key: "offers", label: "Offers", statuses: "offer,accepted" },
  { key: "closed", label: "Closed", statuses: "rejected,withdrawn,failed" },
];

function ApplicationsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const initial = params.get("status") || "all";
  const [filter, setFilter] = useState(FILTERS.some((f) => f.key === initial) ? initial : "all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("updated");
  const [page, setPage] = useState(1);
  const statuses = FILTERS.find((f) => f.key === filter)?.statuses;
  const { data, isLoading } = useApplications({ status: statuses, q, sort, page, page_size: 20 });
  const counts = data?.counts || {};
  const count = (s?: string) => (s ? s.split(",").reduce((n, k) => n + (counts[k] || 0), 0) : undefined);

  return (
    <div>
      <PageHeader title="Applications" description="Every application the agent has prepared, submitted or tracked." />
      <div className="mb-4 flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f.key} onClick={() => { setFilter(f.key); setPage(1); router.replace(`/dashboard/applications${f.key === "all" ? "" : `?status=${f.key}`}`); }}
            className={cn("rounded-full border px-3 py-1 text-sm transition-colors", filter === f.key ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>
            {f.label}
            {count(f.statuses) ? <span className="ml-1.5 opacity-80">{count(f.statuses)}</span> : null}
          </button>
        ))}
      </div>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input className="pl-9" placeholder="Search company or role…" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Select className="sm:w-48" value={sort} onChange={(e) => setSort(e.target.value)}>
          <option value="updated">Recently updated</option>
          <option value="match">Best match</option>
          <option value="created">Newest</option>
          <option value="company">Company A–Z</option>
        </Select>
      </div>
      <div className="space-y-3">
        {isLoading && Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[76px]" />)}
        {!isLoading && !data?.items.length && (
          <EmptyState icon={Send} title="No applications here" description="Run a scan from the Overview page, or add a job by URL on the Jobs page." />
        )}
        {data?.items.map((app) => <ApplicationCard key={app.id} app={app} />)}
      </div>
      {data && data.total > 20 && (
        <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
          <span>{data.total} applications</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
            <Button variant="outline" size="sm" disabled={page * 20 >= data.total} onClick={() => setPage((p) => p + 1)}>Next</Button>
          </div>
        </div>
      )}
      <p className="sr-only">{Object.keys(STATUS_LABELS as Record<ApplicationStatus, string>).length} statuses</p>
    </div>
  );
}

export default function ApplicationsPage() {
  return <Suspense><ApplicationsInner /></Suspense>;
}
