"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { DashboardShell, Loading } from "@/components/DashboardShell";
import { Badge, Button, Card, EmptyState, ErrorNote, SuccessNote } from "@/components/ui";
import { api, post } from "@/lib/api";
import { STATUS_LABEL, STATUS_STYLE, type TrainingClass } from "@/lib/classes";
import { useSession } from "@/lib/session";

export default function TraineeHome() {
  const me = useSession("trainee");
  const [classes, setClasses] = useState<TrainingClass[] | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [joined, setJoined] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<TrainingClass[]>("/classes")
      .then(setClasses)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (me) load();
  }, [me, load]);

  if (!me) return <Loading />;

  async function join(e: FormEvent) {
    e.preventDefault();
    if (!code.trim()) return setError("Enter the access code from your trainer.");
    setBusy(true);
    setError("");
    setJoined("");
    try {
      const cls = await post<TrainingClass>("/classes/join", { code });
      setJoined(`You’re in “${cls.name}”.`);
      setCode("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not join");
    } finally {
      setBusy(false);
    }
  }

  return (
    <DashboardShell me={me} title={`Welcome, ${me.full_name}`}>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-slate-500">My classes</h2>
          {classes === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : classes.length === 0 ? (
            <EmptyState title="You’re not in any classes yet">
              Ask your trainer for an access code, or wait for them to add you.
            </EmptyState>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2">
              {classes.map((c) => (
                <Card key={c.id}>
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-medium">{c.name}</h3>
                    {c.status !== "active" && <Badge className={STATUS_STYLE[c.status]}>{STATUS_LABEL[c.status]}</Badge>}
                  </div>
                  {c.description && <p className="mt-2 line-clamp-2 text-sm text-slate-500">{c.description}</p>}
                  <div className="mt-4 flex items-end justify-between">
                    <span className="text-xs text-slate-500">Trainer: {c.trainer_name}</span>
                    <span className="text-right">
                      <span className="block text-2xl font-semibold text-brand-700">{c.my_xp ?? 0}</span>
                      <span className="text-xs text-slate-500">XP</span>
                    </span>
                  </div>
                  <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400">
                    Sessions appear here once your trainer publishes them.
                  </p>
                </Card>
              ))}
            </div>
          )}
        </div>

        <Card className="h-fit">
          <h2 className="mb-1 font-medium">Join a class</h2>
          <p className="mb-4 text-sm text-slate-500">Enter the access code your trainer gave you.</p>
          <form onSubmit={join} className="space-y-3" noValidate>
            <input
              aria-label="Access code"
              placeholder="ABCD-2345"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="block w-full rounded-lg border border-slate-300 px-3 py-2 text-center font-mono text-lg uppercase tracking-widest outline-none focus:border-brand-600 focus:ring-2 focus:ring-brand-100"
            />
            <ErrorNote>{error}</ErrorNote>
            <SuccessNote>{joined}</SuccessNote>
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Joining…" : "Join class"}
            </Button>
          </form>
        </Card>
      </div>
    </DashboardShell>
  );
}
