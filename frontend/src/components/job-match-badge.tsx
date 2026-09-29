import { cn } from "@/lib/utils";

export function scoreTone(score: number | null | undefined) {
  if (score == null) return "text-muted-foreground bg-muted";
  if (score >= 80) return "text-emerald-700 bg-emerald-500/10 dark:text-emerald-300";
  if (score >= 60) return "text-sky-700 bg-sky-500/10 dark:text-sky-300";
  if (score >= 40) return "text-amber-700 bg-amber-500/15 dark:text-amber-300";
  return "text-red-700 bg-red-500/10 dark:text-red-300";
}

export function JobMatchBadge({ score, size = "md" }: { score: number | null | undefined; size?: "sm" | "md" | "lg" }) {
  const dims = { sm: "h-8 w-8 text-xs", md: "h-11 w-11 text-sm", lg: "h-16 w-16 text-xl" }[size];
  return (
    <div className={cn("flex shrink-0 flex-col items-center justify-center rounded-full font-semibold tabular-nums", dims, scoreTone(score))}
      title={score == null ? "Not evaluated yet" : `Match score ${score}/100`}>
      {score ?? "—"}
    </div>
  );
}
