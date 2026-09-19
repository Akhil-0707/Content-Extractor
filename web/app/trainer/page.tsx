"use client";

import { DashboardShell, Loading } from "@/components/DashboardShell";
import { Card } from "@/components/ui";
import { useSession } from "@/lib/session";

export default function TrainerHome() {
  const me = useSession("trainer");
  if (!me) return <Loading />;
  return (
    <DashboardShell me={me} title={`Welcome, ${me.full_name}`}>
      <Card>
        <h2 className="font-medium">My classes</h2>
        <p className="mt-1 text-sm text-slate-500">
          Create classes and grant trainees access here. Class management arrives in Phase 3.
        </p>
      </Card>
    </DashboardShell>
  );
}
