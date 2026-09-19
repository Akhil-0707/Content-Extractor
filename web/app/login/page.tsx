"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import { Button, Card, ErrorNote, Field } from "@/components/ui";
import { api, type Me, post, type Role, ROLES } from "@/lib/api";
import { homeFor } from "@/lib/session";

export default function LoginPage() {
  const router = useRouter();
  const [role, setRole] = useState<Role>("trainee");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // Already signed in? Skip the form.
  useEffect(() => {
    api<Me>("/auth/me")
      .then((me) => router.replace(homeFor(me)))
      .catch(() => {});
  }, [router]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const me = await post<Me>("/auth/login", { username: username.trim(), password, role });
      router.replace(homeFor(me));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold">Content Extractor</h1>
          <p className="mt-1 text-sm text-slate-500">Sign in to your training account</p>
        </div>
        <Card>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <fieldset>
              <legend className="mb-1.5 block text-sm font-medium text-slate-700">Sign in as</legend>
              <div role="radiogroup" className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
                {ROLES.map((r) => (
                  <button
                    key={r.value}
                    type="button"
                    role="radio"
                    aria-checked={role === r.value}
                    onClick={() => setRole(r.value)}
                    className={`rounded-md px-2 py-1.5 text-sm font-medium transition ${
                      role === r.value ? "bg-white text-brand-700 shadow-sm" : "text-slate-600 hover:text-slate-900"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <Field
              id="username"
              label="Username"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <Field
              id="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <ErrorNote>{error}</ErrorNote>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Signing in…" : `Sign in as ${ROLES.find((r) => r.value === role)!.label}`}
            </Button>
          </form>
        </Card>
        <p className="mt-6 text-center text-xs text-slate-500">
          Accounts are created by your developer. Ask them if you can’t sign in.
        </p>
      </div>
    </main>
  );
}
