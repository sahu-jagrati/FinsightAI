import type { LucideIcon } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function StatCard({
  label,
  value,
  icon: Icon,
  hint,
  accent,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
  hint?: string;
  accent?: "indigo" | "emerald" | "amber" | "sky";
}) {
  const accentClass = {
    indigo: "text-indigo-400 bg-indigo-500/10",
    emerald: "text-emerald-400 bg-emerald-500/10",
    amber: "text-amber-400 bg-amber-500/10",
    sky: "text-sky-400 bg-sky-500/10",
  }[accent ?? "indigo"];

  return (
    <Card>
      <CardContent className="flex items-start justify-between p-5">
        <div>
          <div className="text-xs font-medium text-muted">{label}</div>
          <div className="mt-1.5 text-2xl font-semibold tracking-tight text-foreground">
            {value}
          </div>
          {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
        </div>
        <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", accentClass)}>
          <Icon className="h-5 w-5" strokeWidth={2} />
        </div>
      </CardContent>
    </Card>
  );
}
