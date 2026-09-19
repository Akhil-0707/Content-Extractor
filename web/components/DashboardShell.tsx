"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import type { Me, Role } from "@/lib/api";
import { logout } from "@/lib/session";

const NAV: Record<Role, { href: string; label: string }[]> = {
  trainee: [{ href: "/trainee", label: "My classes" }],
  trainer: [{ href: "/trainer", label: "My classes" }],
  developer: [
    { href: "/developer", label: "Users" },
    { href: "/developer/classes", label: "Classes" },
  ],
};

export function DashboardShell({
  me,
  title,
  actions,
  children,
}: {
  me: Me;
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href={`/${me.role}`} className="text-base font-semibold">
              Content Extractor
            </Link>
            <nav className="flex gap-1 text-sm">
              {NAV[me.role].map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`rounded-md px-3 py-1.5 font-medium ${
                    pathname === item.href ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="hidden text-slate-600 sm:inline">
              {me.full_name} <span className="text-slate-400">·</span>{" "}
              <span className="capitalize text-slate-500">{me.role}</span>
            </span>
            <button onClick={() => logout(router)} className="font-medium text-slate-600 hover:text-slate-900">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-2xl font-semibold">{title}</h1>
          {actions}
        </div>
        {children}
      </main>
    </div>
  );
}

export function Loading() {
  return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading…</div>;
}
