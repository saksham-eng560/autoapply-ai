"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, cloneElement, isValidElement, useEffect, useId, useState } from "react";
import useSWR from "swr";
import { AlertTriangle, CheckCircle2, Copy, Download, KeyRound, Link2, Mail, Puzzle, Save, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/page-header";
import { TagInput } from "@/components/tag-input";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Modal } from "@/components/modal";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useToast } from "@/components/ui/toast";
import { useIntegrations, useMe } from "@/hooks/use-applications";
import { ApiError, api, del, fetcher, patch, post, put } from "@/lib/api-client";
import type { FieldMapping, Preferences, StandardField } from "@/lib/types";
import { PLATFORM_LABELS, cn, timeAgo } from "@/lib/utils";

const ALL_PLATFORMS = ["internships", "greenhouse", "lever", "ashby", "workday", "linkedin", "indeed", "glassdoor", "wellfound", "generic"];
const pill = (on: boolean) => cn("rounded-full border px-3 py-1 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
  on ? "border-primary bg-primary text-primary-foreground" : "border-foreground/30 hover:border-foreground");

const PRESETS = [
  { name: "internships", title: "Internships", text: "Intern roles, 4,000+ curated listings (SimplifyJobs, vanshb03) plus 110 startup boards, 100 applications/day." },
  { name: "startups", title: "Startups", text: "Adds 110 startup Greenhouse, Ashby and Lever boards to your sources, keeps your roles and job types." },
  { name: "new-grad", title: "New grad", text: "Entry-level full-time roles from the SimplifyJobs new-grad list plus the startup boards." },
] as const;

function MassApplyPanel() {
  const { data: me, mutate } = useMe();
  const toast = useToast();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [applying, setApplying] = useState<string | null>(null);
  const { saving, run } = useSaver();
  useEffect(() => { if (me) setPrefs(me.preferences); }, [me]);
  if (!prefs) return null;
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setPrefs({ ...prefs, [k]: v });
  const save = () => run(async () => {
    await put("/users/me/preferences", { preferences: {
      review_mode: prefs.review_mode, auto_submit_kept: prefs.auto_submit_kept, trust_generated_answers: prefs.trust_generated_answers,
      auto_keep_min_score: prefs.auto_keep_min_score, max_jobs_per_source: prefs.max_jobs_per_source,
      exclude_no_sponsorship: prefs.exclude_no_sponsorship, max_applications_per_day: prefs.max_applications_per_day,
      sources: { internship_lists: prefs.sources.internship_lists || [] },
    } });
    await mutate();
  });
  const applyPreset = async (name: string) => {
    setApplying(name);
    try {
      await post(`/users/me/preferences/preset/${name}`);
      await mutate();
      toast({ title: "Preset applied", description: "Your roles, sources and limits are set for mass applying. Run a scan to fill your deck.", tone: "success" });
    } catch (err) {
      toast({ title: "Could not apply preset", description: err instanceof ApiError ? err.message : String(err), tone: "error" });
    } finally {
      setApplying(null);
    }
  };
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>One-click presets</CardTitle>
          <CardDescription>Presets extend your settings — your own roles, boards and exclusions are kept.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-px border-t bg-border p-0 md:grid-cols-3">
          {PRESETS.map((p) => (
            <div key={p.name} className="flex flex-col bg-card p-5">
              <p className="display text-xl">{p.title}</p>
              <p className="mt-2 flex-1 text-sm text-muted-foreground">{p.text}</p>
              <Button className="mt-4 self-start" size="sm" loading={applying === p.name} onClick={() => applyPreset(p.name)}>Apply preset</Button>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>How jobs are picked</CardTitle>
          <CardDescription>Swipe mode never skips a job for a low score — you decide in Swipe Review.</CardDescription>
        </CardHeader>
        <CardContent>
          <Row label="Review mode" hint="Auto mode skips jobs under your match threshold and prepares the rest for approval.">
            <div className="flex flex-wrap gap-2">
              {(["swipe", "auto"] as const).map((m) => (
                <button key={m} type="button" className={pill(prefs.review_mode === m)} aria-pressed={prefs.review_mode === m} onClick={() => set("review_mode", m)}>
                  {m === "swipe" ? "Swipe Review (recommended)" : "Automatic threshold"}
                </button>
              ))}
            </div>
          </Row>
          <Row label="Apply automatically after I keep" hint="Kept jobs are submitted as soon as the form is filled. Blank eligibility questions always wait for you.">
            <Switch checked={prefs.auto_submit_kept} onCheckedChange={(v) => set("auto_submit_kept", v)} label="Apply automatically after keeping" />
          </Row>
          <Row label="Trust AI answers to open questions" hint="“Why this company?”-style answers written by the agent won't hold a kept job back. Visa, work authorization and background questions are never guessed.">
            <Switch checked={prefs.trust_generated_answers} onCheckedChange={(v) => set("trust_generated_answers", v)} label="Trust generated answers" />
          </Row>
          <Row label="Keep automatically at score" hint="Optional: jobs scoring at least this are kept without a swipe. Leave empty to swipe everything yourself.">
            <Input type="number" min={0} max={100} className="max-w-[8rem]" placeholder="off" value={prefs.auto_keep_min_score ?? ""}
              onChange={(e) => set("auto_keep_min_score", e.target.value === "" ? null : Number(e.target.value))} />
          </Row>
          <Row label="Skip jobs without visa sponsorship" hint="For international students: drop postings that say they don't sponsor or require citizenship.">
            <Switch checked={prefs.exclude_no_sponsorship} onCheckedChange={(v) => set("exclude_no_sponsorship", v)} label="Skip jobs without sponsorship" />
          </Row>
          <Row label="Max applications per day" hint="Per-platform caps (e.g. 40 Greenhouse, 10 Workday) still apply to stay under the radar.">
            <Input type="number" min={1} max={200} className="max-w-[8rem]" value={prefs.max_applications_per_day} onChange={(e) => set("max_applications_per_day", Number(e.target.value))} />
          </Row>
          <Row label="Jobs per source per scan" hint="How many postings each source may return per scan (10–1000).">
            <Input type="number" min={10} max={1000} className="max-w-[8rem]" placeholder="50" value={prefs.max_jobs_per_source ?? ""}
              onChange={(e) => set("max_jobs_per_source", e.target.value === "" ? null : Number(e.target.value))} />
          </Row>
          <Row label="Curated internship lists" hint="simplify-internships, vanshb03-internships, simplify-new-grad — or any listings.json URL in the same format.">
            <TagInput value={prefs.sources.internship_lists || []} onChange={(v) => setPrefs({ ...prefs, sources: { ...prefs.sources, internship_lists: v } })} placeholder="simplify-internships" />
          </Row>
          <div className="pt-4"><Button onClick={save} loading={saving}><Save /> Save mass-apply settings</Button></div>
        </CardContent>
      </Card>
    </div>
  );
}

// Controls a Row can label directly (htmlFor/id); anything else is wrapped in a labelled group.
const LABELLABLE: unknown[] = [Input, Select, Switch, TagInput];

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  const id = useId();
  const single = isValidElement<{ id?: string }>(children) && LABELLABLE.includes(children.type) && !children.props.id;
  return (
    <div className="grid grid-cols-1 gap-2 border-b border-border/70 py-5 last:border-0 md:grid-cols-[18rem_minmax(0,1fr)] md:gap-8">
      <div>
        <Label id={`${id}-label`} htmlFor={single ? id : undefined} className="text-sm font-semibold">{label}</Label>
        {hint && <p className="mt-1 break-words text-xs text-muted-foreground">{hint}</p>}
      </div>
      {single ? <div>{cloneElement(children, { id })}</div> : <div role="group" aria-labelledby={`${id}-label`}>{children}</div>}
    </div>
  );
}

function useSaver() {
  const toast = useToast();
  const [saving, setSaving] = useState(false);
  const run = async (fn: () => Promise<unknown>, ok = "Saved") => {
    setSaving(true);
    try {
      await fn();
      toast({ title: ok, tone: "success" });
      return true;
    } catch (err) {
      toast({ title: "Could not save", description: err instanceof ApiError ? err.message : String(err), tone: "error" });
      return false;
    } finally {
      setSaving(false);
    }
  };
  return { saving, run };
}

function PreferencesForm({ sourcesOnly = false }: { sourcesOnly?: boolean }) {
  const { data: me, mutate } = useMe();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const { saving, run } = useSaver();
  useEffect(() => { if (me) setPrefs(me.preferences); }, [me]);
  if (!prefs) return null;
  const set = <K extends keyof Preferences>(k: K, v: Preferences[K]) => setPrefs({ ...prefs, [k]: v });
  const setSource = (k: keyof Preferences["sources"], v: string[]) => setPrefs({ ...prefs, sources: { ...prefs.sources, [k]: v } });
  const save = () => run(async () => { await put("/users/me/preferences", { preferences: prefs }); await mutate(); });

  if (sourcesOnly) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Job sources</CardTitle>
          <CardDescription>Where the agent looks. ATS boards use public APIs (fast, no login). Job boards search by your target roles & locations.</CardDescription>
        </CardHeader>
        <CardContent>
          <Row label="Platforms to scan" hint="Indeed, Glassdoor and Wellfound use a real browser and may need residential proxies to avoid bot blocks.">
            <div className="flex flex-wrap gap-2">
              {ALL_PLATFORMS.map((p) => (
                <button key={p} type="button" onClick={() => set("platforms", prefs.platforms.includes(p) ? prefs.platforms.filter((x) => x !== p) : [...prefs.platforms, p])}
                  className={pill(prefs.platforms.includes(p))} aria-pressed={prefs.platforms.includes(p)}>
                  {PLATFORM_LABELS[p] || p}
                </button>
              ))}
            </div>
          </Row>
          <Row label="Greenhouse boards" hint="Board tokens, e.g. “stripe” from job-boards.greenhouse.io/stripe">
            <TagInput value={prefs.sources.greenhouse_boards} onChange={(v) => setSource("greenhouse_boards", v)} placeholder="stripe, airbnb…" />
          </Row>
          <Row label="Lever companies" hint="Slug from jobs.lever.co/<company>">
            <TagInput value={prefs.sources.lever_companies} onChange={(v) => setSource("lever_companies", v)} placeholder="netflix…" />
          </Row>
          <Row label="Ashby boards" hint="Slug from jobs.ashbyhq.com/<board>">
            <TagInput value={prefs.sources.ashby_boards} onChange={(v) => setSource("ashby_boards", v)} placeholder="openai…" />
          </Row>
          <Row label="Workday career sites" hint="Full site URL, e.g. https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite">
            <TagInput value={prefs.sources.workday_sites} onChange={(v) => setSource("workday_sites", v)} placeholder="https://…myworkdayjobs.com/…" />
          </Row>
          <Row label="Company careers pages" hint="Any careers page — the agent reads JSON-LD job postings and follows embedded ATS boards.">
            <TagInput value={prefs.sources.career_pages} onChange={(v) => setSource("career_pages", v)} placeholder="https://company.com/careers" />
          </Row>
          <div className="pt-4"><Button onClick={save} loading={saving}><Save /> Save sources</Button></div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Search preferences</CardTitle>
        <CardDescription>What the agent looks for and how aggressively it applies.</CardDescription>
      </CardHeader>
      <CardContent>
        <Row label="Target roles" hint="Job titles to look for">
          <TagInput value={prefs.target_roles} onChange={(v) => set("target_roles", v)} placeholder="Software Engineer, Backend Engineer…" />
        </Row>
        <Row label="Target locations">
          <TagInput value={prefs.target_locations} onChange={(v) => set("target_locations", v)} placeholder="San Francisco, New York…" />
        </Row>
        <Row label="Work arrangement">
          <Select value={prefs.remote_preference} onChange={(e) => set("remote_preference", e.target.value as Preferences["remote_preference"])} className="max-w-xs">
            <option value="any">Any</option><option value="remote">Remote only</option><option value="hybrid">Hybrid / remote OK</option><option value="onsite">On-site</option>
          </Select>
        </Row>
        <Row label="Job types">
          <div className="flex flex-wrap gap-2">
            {["full-time", "part-time", "internship", "contract", "freelance"].map((t) => (
              <button key={t} type="button" onClick={() => set("job_types", prefs.job_types.includes(t) ? prefs.job_types.filter((x) => x !== t) : [...prefs.job_types, t])}
                className={cn(pill(prefs.job_types.includes(t)), "capitalize")} aria-pressed={prefs.job_types.includes(t)}>{t}</button>
            ))}
          </div>
        </Row>
        <Row label="Salary range" hint="Salary questions are answered with the bottom of this range.">
          <div className="flex max-w-md items-center gap-2">
            <Input type="number" placeholder="Min" aria-label="Minimum salary" value={prefs.salary_min ?? ""} onChange={(e) => set("salary_min", e.target.value ? Number(e.target.value) : null)} />
            <span className="text-muted-foreground">–</span>
            <Input type="number" placeholder="Max" aria-label="Maximum salary" value={prefs.salary_max ?? ""} onChange={(e) => set("salary_max", e.target.value ? Number(e.target.value) : null)} />
            <Input className="w-24" aria-label="Salary currency" value={prefs.salary_currency} onChange={(e) => set("salary_currency", e.target.value.toUpperCase())} />
          </div>
        </Row>
        <Row label="Companies to avoid">
          <TagInput value={prefs.companies_to_avoid} onChange={(v) => set("companies_to_avoid", v)} />
        </Row>
        <Row label="Companies to target">
          <TagInput value={prefs.companies_to_target} onChange={(v) => set("companies_to_target", v)} />
        </Row>
        <Row label="Exclude titles containing">
          <TagInput value={prefs.keywords_exclude} onChange={(v) => set("keywords_exclude", v)} placeholder="Principal, Manager…" />
        </Row>
        <Row label="Match threshold" hint="Automatic mode only: jobs scoring at or above this are prepared for you. Swipe mode never skips on score.">
          <div className="flex max-w-md items-center gap-4">
            <input type="range" min={0} max={100} aria-label="Match threshold" value={prefs.auto_apply_threshold} onChange={(e) => set("auto_apply_threshold", Number(e.target.value))} className="flex-1 accent-[hsl(var(--primary))]" />
            <span className="w-10 text-right font-medium tabular-nums">{prefs.auto_apply_threshold}</span>
          </div>
        </Row>
        <Row label="Max applications per day">
          <Input type="number" min={1} max={200} className="max-w-[8rem]" value={prefs.max_applications_per_day} onChange={(e) => set("max_applications_per_day", Number(e.target.value))} />
        </Row>
        <Row label="Posted within (days)">
          <Input type="number" min={1} max={90} className="max-w-[8rem]" value={prefs.posted_within_days} onChange={(e) => set("posted_within_days", Number(e.target.value))} />
        </Row>
        <Row label="Automatic scans" hint="Celery Beat checks hourly and scans when your interval has elapsed.">
          <div className="flex items-center gap-3">
            <Switch checked={prefs.scan_enabled} onCheckedChange={(v) => set("scan_enabled", v)} label="Automatic scans" />
            <span className="text-sm text-muted-foreground">every</span>
            <Input type="number" min={1} max={168} className="w-20" aria-label="Scan interval in hours" value={prefs.scan_interval_hours} onChange={(e) => set("scan_interval_hours", Number(e.target.value))} />
            <span className="text-sm text-muted-foreground">hours</span>
          </div>
        </Row>
        <Row label="Cover letters">
          <Switch checked={prefs.cover_letter_enabled} onCheckedChange={(v) => set("cover_letter_enabled", v)} label="Generate cover letters" />
        </Row>
        <Row label="Resume PDF template">
          <Select className="max-w-xs" value={prefs.resume_template || "classic"} onChange={(e) => set("resume_template", e.target.value)}>
            <option value="classic">Classic</option><option value="modern">Modern</option>
          </Select>
        </Row>
        <Row label="Timezone" hint="Used to interpret interview times in e-mails.">
          <Input className="max-w-xs" value={prefs.timezone} onChange={(e) => set("timezone", e.target.value)} placeholder={Intl.DateTimeFormat().resolvedOptions().timeZone} />
        </Row>
        <div className="pt-4"><Button onClick={save} loading={saving}><Save /> Save preferences</Button></div>
      </CardContent>
    </Card>
  );
}

function ProfileForm() {
  const { data: me, mutate } = useMe();
  const [form, setForm] = useState({ full_name: "", phone: "", location: "", linkedin_url: "" });
  const { saving, run } = useSaver();
  useEffect(() => {
    if (me) setForm({ full_name: me.full_name, phone: me.phone || "", location: me.location || "", linkedin_url: me.linkedin_url || "" });
  }, [me]);
  return (
    <Card>
      <CardHeader><CardTitle>Profile</CardTitle><CardDescription>{me?.email}</CardDescription></CardHeader>
      <CardContent>
        <div className="grid max-w-2xl gap-4 sm:grid-cols-2">
          {([["full_name", "Full name"], ["phone", "Phone"], ["location", "Location"], ["linkedin_url", "LinkedIn URL"]] as const).map(([k, label]) => (
            <div key={k} className="space-y-1.5"><Label htmlFor={`profile-${k}`}>{label}</Label><Input id={`profile-${k}`} value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></div>
          ))}
        </div>
        <Button className="mt-4" loading={saving} onClick={() => run(async () => { await patch("/users/me", form); await mutate(); })}><Save /> Save profile</Button>
      </CardContent>
    </Card>
  );
}

function FieldMappingsForm() {
  const { data, mutate } = useSWR<{ mappings: FieldMapping[]; standard_fields: Record<string, StandardField> }>("/users/me/field-mappings", fetcher);
  const [values, setValues] = useState<Record<string, string>>({});
  const [custom, setCustom] = useState({ name: "", value: "" });
  const { saving, run } = useSaver();
  useEffect(() => {
    if (data) setValues(Object.fromEntries(data.mappings.map((m) => [m.field_name, m.field_value])));
  }, [data]);
  if (!data) return null;
  const standardKeys = Object.keys(data.standard_fields);
  const customMappings = data.mappings.filter((m) => !standardKeys.includes(m.field_name));
  const save = () => run(async () => {
    const mappings = Object.entries(values).filter(([, v]) => v !== "" && v !== "********").map(([field_name, field_value]) => ({ field_name, field_value }));
    await put("/users/me/field-mappings", { mappings });
    await mutate();
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle>Saved answers</CardTitle>
        <CardDescription>Exact answers for common application questions. These always win over AI-generated answers. Passwords are stored encrypted.</CardDescription>
      </CardHeader>
      <CardContent>
        {Object.entries(data.standard_fields).map(([key, field]) => (
          <Row key={key} label={field.label}>
            {field.options ? (
              <Select className="max-w-sm" value={values[key] || ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })}>
                <option value="">— not set —</option>
                {field.options.map((o) => <option key={o} value={o}>{o}</option>)}
              </Select>
            ) : (
              <Input className="max-w-sm" type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
                value={values[key] || ""} onChange={(e) => setValues({ ...values, [key]: e.target.value })}
                placeholder={field.type === "password" ? "Used when an ATS requires an account" : ""} />
            )}
          </Row>
        ))}
        {customMappings.map((m) => (
          <Row key={m.field_name} label={m.field_name}>
            <div className="flex max-w-sm gap-2">
              <Input aria-label={m.field_name} value={values[m.field_name] || ""} onChange={(e) => setValues({ ...values, [m.field_name]: e.target.value })} />
              <Button variant="ghost" size="icon" aria-label={`Delete ${m.field_name}`} onClick={() => run(async () => { await del(`/users/me/field-mappings/${m.field_name}`); await mutate(); }, "Deleted")}><Trash2 /></Button>
            </div>
          </Row>
        ))}
        <Row label="Add a custom answer" hint="Use the question wording, e.g. “Do you have a driver's license”">
          <div className="flex max-w-xl gap-2">
            <Input placeholder="Question / field name" aria-label="Question or field name" value={custom.name} onChange={(e) => setCustom({ ...custom, name: e.target.value })} />
            <Input placeholder="Answer" aria-label="Answer" value={custom.value} onChange={(e) => setCustom({ ...custom, value: e.target.value })} />
            <Button variant="outline" disabled={!custom.name || !custom.value} onClick={() => { setValues({ ...values, [custom.name.toLowerCase().replace(/\s+/g, "_")]: custom.value }); setCustom({ name: "", value: "" }); }}>Add</Button>
          </div>
        </Row>
        <div className="pt-4"><Button onClick={save} loading={saving}><Save /> Save answers</Button></div>
      </CardContent>
    </Card>
  );
}

function IntegrationsPanel() {
  const { data: integ, mutate } = useIntegrations();
  const { data: me, mutate: mutateMe } = useMe();
  const [token, setToken] = useState<{ token: string; api_url: string } | null>(null);
  const [webhooks, setWebhooks] = useState({ discord: "", slack: "" });
  const [channels, setChannels] = useState<string[]>([]);
  const { saving, run } = useSaver();
  const toast = useToast();
  useEffect(() => {
    if (me) {
      setWebhooks({ discord: me.preferences.discord_webhook_url || "", slack: me.preferences.slack_webhook_url || "" });
      setChannels(me.preferences.notification_channels);
    }
  }, [me]);
  if (!integ) return null;

  const connectGoogle = () => run(async () => {
    const { url } = await api<{ url: string }>("/auth/google/connect");
    window.location.href = url;
  }, "Redirecting to Google…");

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Mail className="h-4 w-4" /> Google — Gmail & Calendar</CardTitle>
          <CardDescription>Reads recruiter e-mails, labels them, drafts replies and creates interview events. Minimal scopes; revocable any time.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {!integ.google.configured ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground"><AlertTriangle className="h-4 w-4 text-warning" /> Google OAuth isn&apos;t configured on this server (set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).</p>
          ) : integ.google.connected ? (
            <>
              <p className="flex items-center gap-2 text-sm"><CheckCircle2 className="h-4 w-4 text-success" /> Connected as {integ.google.email}</p>
              <div className="flex gap-2">
                <Badge tone={integ.google.gmail ? "success" : "muted"}>Gmail</Badge>
                <Badge tone={integ.google.calendar ? "success" : "muted"}>Calendar</Badge>
                {integ.google.push_enabled && <Badge tone="info">Push notifications</Badge>}
              </div>
              {integ.google.last_polled_at && <p className="text-xs text-muted-foreground">Inbox checked {timeAgo(integ.google.last_polled_at)}</p>}
              <Button variant="outline" size="sm" loading={saving} onClick={() => run(async () => { await post("/auth/google/disconnect"); await mutate(); }, "Google disconnected")}>Disconnect</Button>
            </>
          ) : (
            <Button onClick={connectGoogle} loading={saving}><Link2 /> Connect Google account</Button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2"><Puzzle className="h-4 w-4" /> LinkedIn — Chrome extension</CardTitle>
          <CardDescription>The extension securely syncs your LinkedIn session so the agent can use Easy Apply and keep your resume in sync.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {integ.linkedin.connected ? (
            <p className="flex items-center gap-2">
              {integ.linkedin.session_valid ? <CheckCircle2 className="h-4 w-4 text-success" /> : <AlertTriangle className="h-4 w-4 text-warning" />}
              {integ.linkedin.session_valid ? "Session synced" : "Session expired — re-sync from the extension"} · {timeAgo(integ.linkedin.updated_at)}
            </p>
          ) : <p className="text-muted-foreground">Not connected.</p>}
          <ol className="list-decimal space-y-1 pl-5 text-muted-foreground">
            <li>Load the <code>extension/</code> folder in Chrome (chrome://extensions → Developer mode → Load unpacked).</li>
            <li>Generate a token below and paste it, with the dashboard URL, into the extension popup.</li>
            <li>Log into LinkedIn, then click “Sync LinkedIn session”.</li>
          </ol>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => run(async () => setToken(await post("/auth/extension-token")), "Token generated")}><KeyRound /> Generate extension token</Button>
            {integ.linkedin.connected && (
              <Button variant="ghost" size="sm" onClick={() => run(async () => { await del("/users/me/integrations/linkedin"); await mutate(); }, "LinkedIn disconnected")}>Disconnect</Button>
            )}
          </div>
          {token && (
            <div className="space-y-2 bg-muted p-3">
              <p className="text-xs text-muted-foreground">Dashboard URL: <code>{window.location.origin}</code></p>
              <div className="flex gap-2">
                <Input readOnly aria-label="Extension token" value={token.token} className="font-mono text-xs" />
                <Button size="icon" variant="outline" aria-label="Copy token" onClick={() => { navigator.clipboard.writeText(token.token); toast({ title: "Copied", tone: "success" }); }}><Copy /></Button>
              </div>
              <p className="text-xs text-muted-foreground">This token can only sync your LinkedIn session. It expires in 180 days.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Notifications</CardTitle>
          <CardDescription>Dashboard alerts are always on. E-mail uses SMTP when configured, otherwise your connected Gmail.</CardDescription>
        </CardHeader>
        <CardContent>
          <Row label="Channels">
            <div className="flex flex-wrap gap-2">
              {["dashboard", "email", "discord", "slack"].map((c) => (
                <button key={c} type="button" onClick={() => setChannels(channels.includes(c) ? channels.filter((x) => x !== c) : [...channels, c])}
                  className={cn(pill(channels.includes(c)), "capitalize")} aria-pressed={channels.includes(c)}>{c}</button>
              ))}
            </div>
          </Row>
          <Row label="Browser notifications" hint="System notifications while the dashboard is open in the background.">
            <Button variant="outline" size="sm" onClick={async () => {
              if (!("Notification" in window)) return toast({ title: "Not supported in this browser", tone: "error" });
              const result = await Notification.requestPermission();
              toast({ title: result === "granted" ? "Browser notifications enabled" : "Permission not granted", tone: result === "granted" ? "success" : "error" });
            }}>Enable browser notifications</Button>
          </Row>
          <Row label="Discord webhook URL"><Input value={webhooks.discord} onChange={(e) => setWebhooks({ ...webhooks, discord: e.target.value })} placeholder="https://discord.com/api/webhooks/…" /></Row>
          <Row label="Slack webhook URL"><Input value={webhooks.slack} onChange={(e) => setWebhooks({ ...webhooks, slack: e.target.value })} placeholder="https://hooks.slack.com/services/…" /></Row>
          <div className="pt-4">
            <Button loading={saving} onClick={() => run(async () => {
              await put("/users/me/preferences", { preferences: { notification_channels: channels, discord_webhook_url: webhooks.discord || null, slack_webhook_url: webhooks.slack || null } });
              await mutateMe();
              await mutate();
            })}><Save /> Save notifications</Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Agent capabilities</CardTitle><CardDescription>Server-side configuration (set via environment variables).</CardDescription></CardHeader>
        <CardContent className="grid gap-3 text-sm sm:grid-cols-2">
          <p>AI model: <span className="font-medium">{integ.llm.model || (integ.llm.providers.length ? integ.llm.providers.join(", ") : "not configured — using built-in heuristics")}</span></p>
          <p>Embeddings: <span className="font-medium">{integ.llm.embedding_provider}</span></p>
          <p>Residential proxies: <span className="font-medium">{integ.automation.proxies || "none"}</span></p>
          <p>CAPTCHA solver: <span className="font-medium">{integ.automation.captcha ? "configured" : "not configured"}</span></p>
          <p>Auto-fill forms: <span className="font-medium">{integ.automation.auto_stage ? "on" : "off"}</span></p>
          <p>Dry-run mode: <span className="font-medium">{integ.automation.dry_run ? "ON (submit is never clicked)" : "off"}</span></p>
        </CardContent>
      </Card>
    </div>
  );
}

function PrivacyPanel() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const { saving, run } = useSaver();
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Export your data</CardTitle><CardDescription>Download everything stored about you as JSON (GDPR / CCPA right to access).</CardDescription></CardHeader>
        <CardContent><a href="/api/v1/users/me/export" className={buttonVariants({ variant: "outline" })}><Download /> Download export</a></CardContent>
      </Card>
      <Card className="border-destructive/40">
        <CardHeader><CardTitle className="text-destructive">Delete my account</CardTitle><CardDescription>Permanently deletes your resumes (database and file storage), applications, e-mails, interviews, OAuth tokens and account. This cannot be undone.</CardDescription></CardHeader>
        <CardContent><Button variant="destructive" onClick={() => setOpen(true)}><Trash2 /> Delete everything</Button></CardContent>
      </Card>
      <Modal open={open} onOpenChange={setOpen} title="Delete your account?" description="Type DELETE to confirm."
        footer={<Button variant="destructive" disabled={confirmText !== "DELETE"} loading={saving}
          onClick={() => run(async () => { await del("/users/me", { confirm: "DELETE" }); router.replace("/"); }, "Account deleted")}>Delete permanently</Button>}>
        <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="DELETE" aria-label="Type DELETE to confirm" />
      </Modal>
    </div>
  );
}

function SettingsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const tab = params.get("tab") || "mass-apply";
  useEffect(() => {
    if (params.get("google") === "connected") router.replace("/dashboard/settings?tab=integrations");
  }, [params, router]);
  return (
    <div>
      <PageHeader eyebrow="Setup" title="Settings" description="Tell the agent what you want, where to look, and how to answer." />
      <Tabs value={tab} onValueChange={(v) => router.replace(`/dashboard/settings?tab=${v}`)}>
        <TabsList className="h-auto w-full flex-wrap">
          <TabsTrigger value="mass-apply">Mass apply</TabsTrigger>
          <TabsTrigger value="preferences">Preferences</TabsTrigger>
          <TabsTrigger value="sources">Job sources</TabsTrigger>
          <TabsTrigger value="answers">Saved answers</TabsTrigger>
          <TabsTrigger value="integrations">Integrations</TabsTrigger>
          <TabsTrigger value="profile">Profile</TabsTrigger>
          <TabsTrigger value="privacy">Privacy</TabsTrigger>
        </TabsList>
        <TabsContent value="mass-apply"><MassApplyPanel /></TabsContent>
        <TabsContent value="preferences"><PreferencesForm /></TabsContent>
        <TabsContent value="sources"><PreferencesForm sourcesOnly /></TabsContent>
        <TabsContent value="answers"><FieldMappingsForm /></TabsContent>
        <TabsContent value="integrations"><IntegrationsPanel /></TabsContent>
        <TabsContent value="profile"><ProfileForm /></TabsContent>
        <TabsContent value="privacy"><PrivacyPanel /></TabsContent>
      </Tabs>
    </div>
  );
}

export default function SettingsPage() {
  return <Suspense><SettingsInner /></Suspense>;
}
