import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-border bg-surface-raised px-3 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-indigo-500",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

export const Select = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, children, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "h-9 rounded-md border border-border bg-surface-raised px-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-indigo-500",
      className,
    )}
    {...props}
  >
    {children}
  </select>
));
Select.displayName = "Select";
