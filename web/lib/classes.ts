export type ClassStatus = "draft" | "active" | "archived";

export interface TrainingClass {
  id: string;
  name: string;
  description: string | null;
  status: ClassStatus;
  initial_xp: number;
  trainer_id: string;
  trainer_name: string;
  member_count: number;
  my_xp: number | null;
  created_at: string;
}

export interface Member {
  user_id: string;
  username: string;
  full_name: string;
  is_active: boolean;
  xp: number;
  joined_at: string;
}

export interface TraineeOption {
  id: string;
  username: string;
  full_name: string;
}

export interface AccessCode {
  id: string;
  code: string;
  expires_at: string | null;
  max_uses: number | null;
  use_count: number;
  revoked_at: string | null;
  created_at: string;
}

export const STATUS_LABEL: Record<ClassStatus, string> = {
  draft: "Draft",
  active: "Active",
  archived: "Archived",
};

export const STATUS_STYLE: Record<ClassStatus, string> = {
  draft: "bg-amber-50 text-amber-700",
  active: "bg-emerald-50 text-emerald-700",
  archived: "bg-slate-100 text-slate-600",
};

/** "ABCD2345" → "ABCD-2345" for display; the API accepts either form. */
export const formatCode = (code: string) => `${code.slice(0, 4)}-${code.slice(4)}`;

export function codeState(c: AccessCode): "active" | "revoked" | "expired" | "used up" {
  if (c.revoked_at) return "revoked";
  if (c.expires_at && new Date(c.expires_at) <= new Date()) return "expired";
  if (c.max_uses !== null && c.use_count >= c.max_uses) return "used up";
  return "active";
}
