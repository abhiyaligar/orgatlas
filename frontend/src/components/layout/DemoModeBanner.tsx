import { cn } from "@/lib/utils";

interface DemoModeBannerProps {
  className?: string;
}

export function DemoModeBanner({ className }: DemoModeBannerProps) {
  return (
<div
        role="note"
        className={cn(
          // The amber text was a fixed light shade, which was unreadable once
          // light became the default theme.
          "flex items-center justify-center gap-2 border-b border-amber-500/40 bg-amber-50 px-4 py-1.5 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
          className,
        )}
      >
        <span
          aria-hidden="true"
          className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500"
        />
        Fictional SaaS demo data — Payments Core and Cloud Infrastructure
      </div>
  );
}