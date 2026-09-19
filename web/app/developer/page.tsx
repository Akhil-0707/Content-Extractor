"use client";

import { type FormEvent, useCallback, useEffect, useState } from "react";

import { DashboardShell, Loading } from "@/components/DashboardShell";
import { Button, Card, ErrorNote, Field } from "@/components/ui";
import { api, patch, post, type Role, ROLES } from "@/lib/api";
import { useSession } from "@/lib/session";

interface AdminUser {
  id: string;
  username: string;
  full_name: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  locked_until: string | null;
  last_login_at: string | null;
}

const EMPTY_FORM = { username: "", full_name: "", role: "trainee" as Role, password: "" };

export default function DeveloperHome() {
  const me = useSession("developer");
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [form, setForm] = useState(EMPTY_FORM);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<AdminUser[]>("/users")
      .then(setUsers)
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => {
    if (me) load();
  }, [me, load]);

  if (!me) return <Loading />;

  async function createUser(e: FormEvent) {
    e.preventDefault();
    if (!form.username.trim() || !form.full_name.trim() || !form.password) {
      setError("Fill in username, full name and a temporary password.");
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const created = await post<AdminUser>("/users", { ...form, username: form.username.trim() });
      setNotice(`Created ${created.username}. They must change the temporary password at first login.`);
      setForm(EMPTY_FORM);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create user");
    } finally {
      setBusy(false);
    }
  }

  async function update(user: AdminUser, changes: Record<string, unknown>) {
    setError("");
    setNotice("");
    try {
      await patch(`/users/${user.id}`, changes);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    }
  }

  const isLocked = (u: AdminUser) => u.locked_until !== null && new Date(u.locked_until) > new Date();

  return (
    <DashboardShell me={me} title="User accounts">
      <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
        <Card>
          <h2 className="mb-4 font-medium">Create account</h2>
          <form onSubmit={createUser} className="space-y-4" noValidate>
            <Field
              id="new-username"
              label="Username"
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
            <Field
              id="new-fullname"
              label="Full name"
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
            <div className="space-y-1.5">
              <label htmlFor="new-role" className="block text-sm font-medium text-slate-700">
                Role
              </label>
              <select
                id="new-role"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
                className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm"
              >
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>
            <Field
              id="new-password"
              label="Temporary password"
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <Button type="submit" disabled={busy} className="w-full">
              {busy ? "Creating…" : "Create account"}
            </Button>
          </form>
        </Card>

        <div className="space-y-4">
          <ErrorNote>{error}</ErrorNote>
          {notice && (
            <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              {notice}
            </p>
          )}
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-medium">User</th>
                  <th className="px-4 py-3 font-medium">Role</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Last login</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => (
                  <tr key={u.id} className={u.is_active ? "" : "text-slate-400"}>
                    <td className="px-4 py-3">
                      <div className="font-medium">{u.full_name}</div>
                      <div className="text-xs text-slate-500">{u.username}</div>
                    </td>
                    <td className="px-4 py-3 capitalize">{u.role}</td>
                    <td className="px-4 py-3">
                      {!u.is_active ? "Deactivated" : isLocked(u) ? "Locked" : u.must_change_password ? "Must change password" : "Active"}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : "Never"}
                    </td>
                    <td className="space-x-3 whitespace-nowrap px-4 py-3 text-right">
                      {isLocked(u) && (
                        <button onClick={() => update(u, { unlock: true })} className="text-brand-700 hover:underline">
                          Unlock
                        </button>
                      )}
                      {u.id !== me.id && (
                        <button
                          onClick={() => update(u, { is_active: !u.is_active })}
                          className="text-slate-600 hover:underline"
                        >
                          {u.is_active ? "Deactivate" : "Reactivate"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </div>
      </div>
    </DashboardShell>
  );
}
