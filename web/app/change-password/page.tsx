"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { Loading } from "@/components/DashboardShell";
import { Button, Card, ErrorNote, Field } from "@/components/ui";
import { type Me, post } from "@/lib/api";
import { homeFor, logout, useSession } from "@/lib/session";

export default function ChangePasswordPage() {
  const router = useRouter();
  const me = useSession();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (!me) return <Loading />;

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!current || !next) return setError("Fill in all fields.");
    if (next !== confirm) return setError("The new passwords don’t match.");
    setBusy(true);
    setError("");
    try {
      const updated = await post<Me>("/auth/change-password", { current_password: current, new_password: next });
      router.replace(homeFor(updated));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not change password");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <h1 className="text-2xl font-semibold">Change your password</h1>
          <p className="mt-1 text-sm text-slate-500">
            {me.must_change_password
              ? "Choose a new password before continuing."
              : `Signed in as ${me.username}.`}
          </p>
        </div>
        <Card>
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <Field
              id="current"
              label="Current password"
              type="password"
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
            <Field
              id="new"
              label="New password"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
            <Field
              id="confirm"
              label="Confirm new password"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
            <p className="text-xs text-slate-500">
              At least 10 characters, with upper- and lower-case letters and a digit. Must not contain your username.
            </p>
            <ErrorNote>{error}</ErrorNote>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Saving…" : "Save new password"}
            </Button>
          </form>
        </Card>
        <button
          onClick={() => logout(router)}
          className="mt-6 block w-full text-center text-sm text-slate-500 hover:text-slate-800"
        >
          Log out
        </button>
      </div>
    </main>
  );
}
