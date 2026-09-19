"use client";

import Link from "next/link";
import { type FormEvent, useState } from "react";

import { Badge, Button, Card, EmptyState, ErrorNote, Field, Select, TextArea } from "@/components/ui";
import { post } from "@/lib/api";
import { STATUS_LABEL, STATUS_STYLE, type TrainingClass, type TraineeOption } from "@/lib/classes";

export function ClassGrid({ classes, showTrainer }: { classes: TrainingClass[]; showTrainer?: boolean }) {
  if (classes.length === 0) {
    return <EmptyState title="No classes yet">Create your first class to get started.</EmptyState>;
  }
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {classes.map((c) => (
        <Link key={c.id} href={`/classes/${c.id}`} className="group">
          <Card className="h-full transition group-hover:border-brand-600">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-medium group-hover:text-brand-700">{c.name}</h3>
              <Badge className={STATUS_STYLE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
            </div>
            {c.description && <p className="mt-2 line-clamp-2 text-sm text-slate-500">{c.description}</p>}
            <div className="mt-4 flex gap-4 text-xs text-slate-500">
              <span>
                {c.member_count} trainee{c.member_count === 1 ? "" : "s"}
              </span>
              <span>{c.initial_xp} starting XP</span>
              {showTrainer && <span>Trainer: {c.trainer_name}</span>}
            </div>
          </Card>
        </Link>
      ))}
    </div>
  );
}

export function CreateClassForm({
  trainers,
  onCreated,
}: {
  /** Developer only: pick the owning trainer. Trainers own what they create. */
  trainers?: TraineeOption[];
  onCreated: (c: TrainingClass) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [initialXp, setInitialXp] = useState("100");
  const [trainerId, setTrainerId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const xp = Number(initialXp);
    if (!name.trim()) return setError("Give the class a name.");
    if (!Number.isInteger(xp) || xp < 0) return setError("Starting XP must be a whole number, 0 or more.");
    if (trainers && !trainerId) return setError("Choose the trainer for this class.");
    setBusy(true);
    setError("");
    try {
      const created = await post<TrainingClass>("/classes", {
        name: name.trim(),
        description: description.trim() || null,
        initial_xp: xp,
        ...(trainers ? { trainer_id: trainerId } : {}),
      });
      setName("");
      setDescription("");
      onCreated(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create class");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <h2 className="mb-4 font-medium">New class</h2>
      <form onSubmit={submit} className="space-y-4" noValidate>
        <Field id="class-name" label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <TextArea
          id="class-description"
          label="Description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <Field
          id="class-xp"
          label="Starting XP for each trainee"
          type="number"
          min={0}
          value={initialXp}
          onChange={(e) => setInitialXp(e.target.value)}
        />
        {trainers && (
          <Select id="class-trainer" label="Trainer" value={trainerId} onChange={(e) => setTrainerId(e.target.value)}>
            <option value="">Choose a trainer…</option>
            {trainers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.full_name} ({t.username})
              </option>
            ))}
          </Select>
        )}
        <ErrorNote>{error}</ErrorNote>
        <Button type="submit" disabled={busy} className="w-full">
          {busy ? "Creating…" : "Create class"}
        </Button>
      </form>
    </Card>
  );
}
