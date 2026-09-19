"use client";

import { DashboardShell, Loading } from "@/components/DashboardShell";
import { Card } from "@/components/ui";
import { useSession } from "@/lib/session";

export default function TraineeHome() {
  const me = useSession("trainee");
  if (!me) return <Loading />;
  return (
    <DashboardShell me={me} title={`Welcome, ${me.full_name}`}>
      <Card>
        <h2 className="font-medium">My classes</h2>
        <p className="mt-1 text-sm text-slate-500">
          Classes you’ve been given access to will appear here. Joining with an access code arrives in Phase 3.
        </p>
      </Card>
    </DashboardShell>
  );
}
