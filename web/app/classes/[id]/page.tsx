"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { DashboardShell, Loading } from "@/components/DashboardShell";
import { Badge, Button, Card, EmptyState, ErrorNote, Field, Select, SuccessNote } from "@/components/ui";
import { api, type Me, patch, post } from "@/lib/api";
import {
  type AccessCode,
  type ClassStatus,
  codeState,
  formatCode,
  type Member,
  STATUS_LABEL,
  STATUS_STYLE,
  type TraineeOption,
  type TrainingClass,
} from "@/lib/classes";
import { useSession } from "@/lib/session";

export default function ClassPage() {
  const me = useSession(["trainer", "developer"]);
  const { id } = useParams<{ id: string }>();
  const [cls, setCls] = useState<TrainingClass | null>(null);
  const [notFound, setNotFound] = useState(false);

  const loadClass = useCallback(() => {
    api<TrainingClass>(`/classes/${id}`)
      .then(setCls)
      .catch(() => setNotFound(true));
  }, [id]);

  useEffect(() => {
    if (me) loadClass();
  }, [me, loadClass]);

  if (!me) return <Loading />;
  const back = me.role === "developer" ? "/developer/classes" : "/trainer";

  if (notFound) {
    return (
      <DashboardShell me={me} title="Class not found">
        <EmptyState title="This class doesn’t exist or isn’t yours.">
          <Link href={back} className="text-brand-700 hover:underline">
            Back to classes
          </Link>
        </EmptyState>
      </DashboardShell>
    );
  }
  if (!cls) return <Loading />;

  return (
    <DashboardShell
      me={me}
      title={
        <span className="flex items-center gap-3">
          {cls.name}
          <Badge className={STATUS_STYLE[cls.status]}>{STATUS_LABEL[cls.status]}</Badge>
        </span>
      }
      actions={
        <Link href={back} className="text-sm text-slate-600 hover:text-slate-900">
          ← All classes
        </Link>
      }
    >
      {cls.description && <p className="-mt-3 mb-6 max-w-3xl text-sm text-slate-600">{cls.description}</p>}
      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <MembersPanel classId={cls.id} onChange={loadClass} />
        <div className="space-y-6">
          <AccessCodesPanel classId={cls.id} active={cls.status === "active"} />
          <SettingsPanel me={me} cls={cls} onSaved={setCls} />
        </div>
      </div>
    </DashboardShell>
  );
}

function MembersPanel({ classId, onChange }: { classId: string; onChange: () => void }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [trainees, setTrainees] = useState<TraineeOption[]>([]);
  const [picking, setPicking] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Member[]>(`/classes/${classId}/members`)
      .then(setMembers)
      .catch((err) => setError(err.message));
  }, [classId]);

  useEffect(load, [load]);

  const candidates = useMemo(() => {
    const inClass = new Set(members?.map((m) => m.user_id));
    const q = filter.trim().toLowerCase();
    return trainees.filter(
      (t) => !inClass.has(t.id) && (!q || t.full_name.toLowerCase().includes(q) || t.username.toLowerCase().includes(q)),
    );
  }, [trainees, members, filter]);

  async function openPicker() {
    setError("");
    try {
      setTrainees(await api<TraineeOption[]>("/trainees"));
      setSelected(new Set());
      setFilter("");
      setPicking(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load trainees");
    }
  }

  async function addSelected() {
    if (selected.size === 0) return setError("Select at least one trainee.");
    setError("");
    try {
      setMembers(await post<Member[]>(`/classes/${classId}/members`, { user_ids: [...selected] }));
      setPicking(false);
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add trainees");
    }
  }

  async function remove(m: Member) {
    if (!confirm(`Remove ${m.full_name} from this class? Their XP history is kept if they rejoin.`)) return;
    setError("");
    try {
      await api(`/classes/${classId}/members/${m.user_id}`, { method: "DELETE" });
      load();
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove trainee");
    }
  }

  return (
    <Card className="p-0">
      <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
        <h2 className="font-medium">
          Trainees {members && <span className="text-slate-400">({members.length})</span>}
        </h2>
        {!picking && (
          <Button variant="secondary" onClick={openPicker}>
            Add trainees
          </Button>
        )}
      </div>

      {picking && (
        <div className="space-y-3 border-b border-slate-200 bg-slate-50 px-6 py-4">
          <input
            aria-label="Search trainees"
            placeholder="Search by name or username"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
          />
          <div className="max-h-56 space-y-1 overflow-y-auto">
            {candidates.length === 0 ? (
              <p className="py-2 text-sm text-slate-500">No other trainee accounts to add.</p>
            ) : (
              candidates.map((t) => (
                <label key={t.id} className="flex cursor-pointer items-center gap-3 rounded-md px-2 py-1.5 hover:bg-white">
                  <input
                    type="checkbox"
                    checked={selected.has(t.id)}
                    onChange={(e) => {
                      const next = new Set(selected);
                      if (e.target.checked) next.add(t.id);
                      else next.delete(t.id);
                      setSelected(next);
                    }}
                  />
                  <span className="text-sm">
                    {t.full_name} <span className="text-slate-400">{t.username}</span>
                  </span>
                </label>
              ))
            )}
          </div>
          <div className="flex gap-2">
            <Button onClick={addSelected}>Add {selected.size || ""} selected</Button>
            <Button variant="secondary" onClick={() => setPicking(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <div className="px-6 pt-4">
        <ErrorNote>{error}</ErrorNote>
      </div>
      {members === null ? (
        <p className="px-6 py-4 text-sm text-slate-500">Loading…</p>
      ) : members.length === 0 ? (
        <p className="px-6 pb-6 text-sm text-slate-500">
          No trainees yet. Add them directly, or share an access code.
        </p>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-6 py-2 font-medium">Trainee</th>
              <th className="px-6 py-2 text-right font-medium">XP</th>
              <th className="px-6 py-2 font-medium">Joined</th>
              <th className="px-6 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {members.map((m) => (
              <tr key={m.user_id} className={m.is_active ? "" : "text-slate-400"}>
                <td className="px-6 py-3">
                  <div className="font-medium">{m.full_name}</div>
                  <div className="text-xs text-slate-500">
                    {m.username}
                    {!m.is_active && " · deactivated"}
                  </div>
                </td>
                <td className="px-6 py-3 text-right font-medium tabular-nums">{m.xp}</td>
                <td className="px-6 py-3 text-slate-500">{new Date(m.joined_at).toLocaleDateString()}</td>
                <td className="px-6 py-3 text-right">
                  <button onClick={() => remove(m)} className="text-slate-500 hover:text-red-600">
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Card>
  );
}

function AccessCodesPanel({ classId, active }: { classId: string; active: boolean }) {
  const [codes, setCodes] = useState<AccessCode[]>([]);
  const [hours, setHours] = useState("72");
  const [maxUses, setMaxUses] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState("");

  const load = useCallback(() => {
    api<AccessCode[]>(`/classes/${classId}/access-codes`)
      .then(setCodes)
      .catch((err) => setError(err.message));
  }, [classId]);

  useEffect(load, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    const h = hours === "" ? null : Number(hours);
    const uses = maxUses === "" ? null : Number(maxUses);
    if (h !== null && (!Number.isInteger(h) || h < 1)) return setError("Expiry must be a whole number of hours.");
    if (uses !== null && (!Number.isInteger(uses) || uses < 1)) return setError("Max uses must be 1 or more.");
    setError("");
    try {
      await post(`/classes/${classId}/access-codes`, { expires_in_hours: h, max_uses: uses });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create code");
    }
  }

  async function revoke(c: AccessCode) {
    try {
      await api(`/classes/${classId}/access-codes/${c.id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke code");
    }
  }

  async function copy(c: AccessCode) {
    try {
      await navigator.clipboard.writeText(formatCode(c.code));
      setCopied(c.id);
      setTimeout(() => setCopied(""), 1500);
    } catch {
      // clipboard blocked; the code is visible anyway
    }
  }

  const visible = codes.filter((c) => codeState(c) === "active");
  const inactiveCount = codes.length - visible.length;

  return (
    <Card>
      <h2 className="font-medium">Access codes</h2>
      <p className="mb-4 mt-1 text-sm text-slate-500">Trainees enter a code on their dashboard to join.</p>
      {!active && (
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
          Codes only work while the class is Active.
        </p>
      )}
      <form onSubmit={create} className="mb-4 grid grid-cols-2 gap-3" noValidate>
        <Field
          id="code-hours"
          label="Expires after (hours)"
          type="number"
          min={1}
          placeholder="Never"
          value={hours}
          onChange={(e) => setHours(e.target.value)}
        />
        <Field
          id="code-uses"
          label="Max uses"
          type="number"
          min={1}
          placeholder="Unlimited"
          value={maxUses}
          onChange={(e) => setMaxUses(e.target.value)}
        />
        <Button type="submit" className="col-span-2">
          Generate code
        </Button>
      </form>
      <ErrorNote>{error}</ErrorNote>
      <ul className="space-y-2">
        {visible.map((c) => (
          <li key={c.id} className="rounded-lg border border-slate-200 px-3 py-2">
            <div className="flex items-center justify-between">
              <button
                onClick={() => copy(c)}
                title="Copy"
                className="font-mono text-base font-semibold tracking-wider text-brand-700"
              >
                {formatCode(c.code)}
              </button>
              <span className="flex gap-3 text-xs">
                <span className="text-emerald-600">{copied === c.id ? "Copied" : ""}</span>
                <button onClick={() => revoke(c)} className="text-slate-500 hover:text-red-600">
                  Revoke
                </button>
              </span>
            </div>
            <div className="mt-1 text-xs text-slate-500">
              Used {c.use_count}
              {c.max_uses !== null && ` / ${c.max_uses}`}
              {" · "}
              {c.expires_at ? `expires ${new Date(c.expires_at).toLocaleString()}` : "never expires"}
            </div>
          </li>
        ))}
      </ul>
      {visible.length === 0 && <p className="text-sm text-slate-500">No active codes.</p>}
      {inactiveCount > 0 && (
        <p className="mt-3 text-xs text-slate-400">
          {inactiveCount} expired, used-up or revoked code{inactiveCount === 1 ? "" : "s"} hidden.
        </p>
      )}
    </Card>
  );
}

function SettingsPanel({ me, cls, onSaved }: { me: Me; cls: TrainingClass; onSaved: (c: TrainingClass) => void }) {
  const [name, setName] = useState(cls.name);
  const [status, setStatus] = useState<ClassStatus>(cls.status);
  const [initialXp, setInitialXp] = useState(String(cls.initial_xp));
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");

  async function save(e: FormEvent) {
    e.preventDefault();
    const xp = Number(initialXp);
    if (!name.trim()) return setError("Name can’t be empty.");
    if (!Number.isInteger(xp) || xp < 0) return setError("Starting XP must be a whole number, 0 or more.");
    setError("");
    setSaved("");
    try {
      onSaved(await patch<TrainingClass>(`/classes/${cls.id}`, { name: name.trim(), status, initial_xp: xp }));
      setSaved("Saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  return (
    <Card>
      <h2 className="mb-4 font-medium">Settings</h2>
      <form onSubmit={save} className="space-y-4" noValidate>
        <Field id="set-name" label="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <Select id="set-status" label="Status" value={status} onChange={(e) => setStatus(e.target.value as ClassStatus)}>
          <option value="active">Active: visible to trainees, codes work</option>
          <option value="draft">Draft: hidden from trainees</option>
          <option value="archived">Archived: read-only for trainees</option>
        </Select>
        <Field
          id="set-xp"
          label="Starting XP (applies to trainees added from now on)"
          type="number"
          min={0}
          value={initialXp}
          onChange={(e) => setInitialXp(e.target.value)}
        />
        {me.role === "developer" && <p className="text-xs text-slate-500">Trainer: {cls.trainer_name}</p>}
        <ErrorNote>{error}</ErrorNote>
        <SuccessNote>{saved}</SuccessNote>
        <Button type="submit" variant="secondary" className="w-full">
          Save settings
        </Button>
      </form>
    </Card>
  );
}
