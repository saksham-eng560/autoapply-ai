import Link from "next/link";
import { ArrowRight, Bot, CalendarDays, FileText, Hand, Mail, Radar, ShieldCheck, Sparkles } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const features = [
  { icon: Radar, title: "Discovers jobs", text: "LinkedIn, Indeed, Glassdoor, Wellfound, Greenhouse, Lever, Ashby, Workday and any careers page." },
  { icon: Sparkles, title: "Tailors every resume", text: "Claude reorders and rephrases your real experience for each role — never invents skills." },
  { icon: Bot, title: "Fills the forms", text: "Platform-aware form filling with human-like typing, uploads and custom question answers." },
  { icon: Hand, title: "Waits for your OK", text: "Every application pauses with a full preview and screenshot until you approve it." },
  { icon: Mail, title: "Reads recruiter mail", text: "Classifies Gmail replies, updates statuses, labels threads and drafts responses." },
  { icon: CalendarDays, title: "Books interviews", text: "Creates Google Calendar events with AI prep notes and likely questions." },
];

export default function Landing() {
  return (
    <main className="min-h-screen bg-gradient-to-b from-primary/5 via-background to-background">
      <header className="container flex h-16 items-center justify-between">
        <div className="flex items-center gap-2 font-semibold">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <FileText className="h-4 w-4" />
          </div>
          AutoApply AI
        </div>
        <nav className="flex items-center gap-2">
          <Link href="/login" className={buttonVariants({ variant: "ghost" })}>Sign in</Link>
          <Link href="/register" className={buttonVariants()}>Get started</Link>
        </nav>
      </header>
      <section className="container py-20 text-center">
        <div className="mx-auto inline-flex items-center gap-2 rounded-full border bg-background px-3 py-1 text-xs text-muted-foreground">
          <ShieldCheck className="h-3.5 w-3.5 text-success" /> Human-in-the-loop · nothing is submitted without your approval
        </div>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-bold tracking-tight sm:text-6xl">
          Your autonomous job-search agent
        </h1>
        <p className="mx-auto mt-5 max-w-2xl text-lg text-muted-foreground">
          AutoApply AI finds relevant openings, tailors your resume and cover letter truthfully, fills out every
          application — then waits for your go-ahead before it hits submit.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link href="/register" className={cn(buttonVariants({ size: "lg" }))}>
            Start applying smarter <ArrowRight />
          </Link>
          <Link href="/login" className={buttonVariants({ size: "lg", variant: "outline" })}>I have an account</Link>
        </div>
      </section>
      <section className="container grid gap-4 pb-24 sm:grid-cols-2 lg:grid-cols-3">
        {features.map(({ icon: Icon, title, text }) => (
          <div key={title} className="rounded-xl border bg-card p-6 shadow-sm">
            <Icon className="h-5 w-5 text-primary" />
            <h3 className="mt-3 font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{text}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
