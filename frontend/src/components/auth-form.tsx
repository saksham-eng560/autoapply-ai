"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR from "swr";
import { FileText } from "lucide-react";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, fetcher, post } from "@/lib/api-client";
import { cn } from "@/lib/utils";

const ERRORS: Record<string, string> = {
  google_oauth_failed: "Google sign-in failed. Please try again.",
  registration_disabled: "Registration is disabled on this server.",
  session_expired: "Your session expired — sign in again.",
};

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { data: config } = useSWR<{ google_enabled: boolean; registration_enabled: boolean }>("/auth/config", fetcher);

  useEffect(() => {
    const e = params.get("error");
    if (e) setError(ERRORS[e] || e);
  }, [params]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") await post("/auth/login", { email, password });
      else await post("/auth/register", { email, password, full_name: fullName });
      router.replace(mode === "register" ? "/dashboard?welcome=1" : next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-b from-primary/5 to-background p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <Link href="/" className="mb-2 flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <FileText className="h-5 w-5" />
          </Link>
          <CardTitle className="text-xl">{mode === "login" ? "Welcome back" : "Create your account"}</CardTitle>
          <CardDescription>{mode === "login" ? "Sign in to your AutoApply AI dashboard" : "Set up your job-search agent in minutes"}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            {mode === "register" && (
              <div className="space-y-1.5">
                <Label htmlFor="name">Full name</Label>
                <Input id="name" value={fullName} onChange={(e) => setFullName(e.target.value)} required autoComplete="name" />
              </div>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                minLength={mode === "register" ? 8 : undefined} autoComplete={mode === "login" ? "current-password" : "new-password"} />
            </div>
            {error && <p className="rounded-md bg-destructive/10 p-2 text-sm text-destructive">{error}</p>}
            <Button type="submit" className="w-full" loading={loading}>{mode === "login" ? "Sign in" : "Create account"}</Button>
          </form>
          {config?.google_enabled && (
            <>
              <div className="my-4 flex items-center gap-3 text-xs text-muted-foreground">
                <div className="h-px flex-1 bg-border" /> or <div className="h-px flex-1 bg-border" />
              </div>
              <a href={`/api/v1/auth/google/login?next=${encodeURIComponent(next)}`} className={cn(buttonVariants({ variant: "outline" }), "w-full")}>
                <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden><path fill="#EA4335" d="M12 10.2v3.9h5.5c-.2 1.3-1.6 3.9-5.5 3.9-3.3 0-6-2.7-6-6.1s2.7-6.1 6-6.1c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.3 14.6 2.4 12 2.4 6.7 2.4 2.4 6.7 2.4 12s4.3 9.6 9.6 9.6c5.5 0 9.2-3.9 9.2-9.4 0-.6-.1-1.1-.2-1.6H12z"/></svg>
                Continue with Google
              </a>
            </>
          )}
          <p className="mt-4 text-center text-sm text-muted-foreground">
            {mode === "login" ? (
              <>No account? <Link href="/register" className="font-medium text-primary hover:underline">Create one</Link></>
            ) : (
              <>Already registered? <Link href="/login" className="font-medium text-primary hover:underline">Sign in</Link></>
            )}
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
