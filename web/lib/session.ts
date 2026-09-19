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
export function useSession(role?: Role): Me | null {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Me>("/auth/me")
      .then((user) => {
        if (cancelled) return;
        if (user.must_change_password && role) router.replace("/change-password");
        else if (role && user.role !== role) router.replace(homeFor(user));
        else setMe(user);
      })
      .catch((err) => {
        if (!cancelled && err instanceof ApiError && err.status === 401) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [role, router]);

  return me;
}

export async function logout(router: ReturnType<typeof useRouter>) {
  try {
    await post("/auth/logout");
  } finally {
    router.replace("/login");
  }
}
