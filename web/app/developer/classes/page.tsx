"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { ClassGrid, CreateClassForm } from "@/components/ClassList";
import { DashboardShell, Loading } from "@/components/DashboardShell";
import { ErrorNote } from "@/components/ui";
import { api } from "@/lib/api";
import type { TraineeOption, TrainingClass } from "@/lib/classes";
import { useSession } from "@/lib/session";

export default function DeveloperClasses() {
  const me = useSession("developer");
  const router = useRouter();
  const [classes, setClasses] = useState<TrainingClass[] | null>(null);
  const [trainers, setTrainers] = useState<TraineeOption[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!me) return;
    Promise.all([
      api<TrainingClass[]>("/classes"),
      api<(TraineeOption & { is_active: boolean })[]>("/users?role=trainer"),
    ])
      .then(([cls, trainerUsers]) => {
        setClasses(cls);
        setTrainers(trainerUsers.filter((t) => t.is_active));
      })
      .catch((err) => setError(err.message));
  }, [me]);

  if (!me) return <Loading />;

  return (
    <DashboardShell me={me} title="All classes">
      <ErrorNote>{error}</ErrorNote>
      <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
        <div>
          {classes ? <ClassGrid classes={classes} showTrainer /> : <p className="text-sm text-slate-500">Loading…</p>}
        </div>
        <CreateClassForm trainers={trainers} onCreated={(c) => router.push(`/classes/${c.id}`)} />
      </div>
    </DashboardShell>
  );
}
