import { type VariantProps, cva } from "class-variance-authority";
import * as React from "react";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset whitespace-nowrap",
  {
    variants: {
      variant: {
        neutral: "bg-white/5 text-muted ring-border",
        info: "bg-sky-500/10 text-sky-400 ring-sky-500/30",
        success: "bg-emerald-500/10 text-emerald-400 ring-emerald-500/30",
        warning: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
        danger: "bg-rose-500/10 text-rose-400 ring-rose-500/30",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
