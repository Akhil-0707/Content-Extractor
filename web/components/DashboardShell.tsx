"use client";

import { useRouter } from "next/navigation";
import type { ReactNode } from "react";

import type { Me } from "@/lib/api";
import { logout } from "@/lib/session";

export function DashboardShell({ me, title, children }: { me: Me; title: string; children: ReactNode }) {
  const router = useRouter();
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-base font-semibold">Content Extractor</span>
            <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium capitalize text-brand-700">
              {me.role}
            </span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="hidden text-slate-600 sm:inline">{me.full_name}</span>
            <button onClick={() => logout(router)} className="font-medium text-slate-600 hover:text-slate-900">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">
        <h1 className="mb-6 text-2xl font-semibold">{title}</h1>
        {children}
      </main>
    </div>
  );
}

export function Loading() {
  return <div className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading…</div>;
}
