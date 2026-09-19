"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { api, ApiError, type Me, post, type Role } from "./api";

export const homeFor = (me: Me) => (me.must_change_password ? "/change-password" : `/${me.role}`);

/**
 * Load the signed-in user and send them where they belong:
 * not signed in → /login, must change password → /change-password, wrong role → their own dashboard.
 * The API enforces all of this too; this only keeps the UI consistent.
 */
export function useSession(role?: Role | Role[]): Me | null {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const allowed = role === undefined ? null : Array.isArray(role) ? role : [role];
  const allowedKey = allowed?.join(",");

  useEffect(() => {
    let cancelled = false;
    const roles = allowedKey ? (allowedKey.split(",") as Role[]) : null;
    api<Me>("/auth/me")
      .then((user) => {
        if (cancelled) return;
        if (user.must_change_password && roles) router.replace("/change-password");
        else if (roles && !roles.includes(user.role)) router.replace(homeFor(user));
        else setMe(user);
      })
      .catch((err) => {
        if (!cancelled && err instanceof ApiError && err.status === 401) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [allowedKey, router]);

  return me;
}

export async function logout(router: ReturnType<typeof useRouter>) {
  try {
    await post("/auth/logout");
  } finally {
    router.replace("/login");
  }
}
