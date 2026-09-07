"use client";

import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/lib/config";

export function Topbar() {
  const [ok, setOk] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const res = await fetch(`${API_BASE_URL}/api/health`, { cache: "no-store" });
        const data = await res.json();
        if (!cancelled) setOk(data.status === "ok");
      } catch {
        if (!cancelled) setOk(false);
      }
    }
    check();
    const interval = setInterval(check, 20_000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-3 border-b border-border bg-surface px-6">
      <div className="flex items-center gap-1.5 text-xs text-muted">
        <span
          className={`h-1.5 w-1.5 rounded-full ${
            ok === null ? "bg-slate-600" : ok ? "bg-emerald-400" : "bg-rose-400"
          }`}
        />
        {ok === null ? "Connecting…" : ok ? "All systems operational" : "Backend unreachable"}
      </div>
    </header>
  );
}
