import { cn } from "@/lib/utils";

interface DemoModeBannerProps {
  className?: string;
}

export function DemoModeBanner({ className }: DemoModeBannerProps) {
  return (
    <div
      role="note"
      className={cn(
        "flex items-center justify-center gap-2 border-b border-amber-500/30 bg-amber-500/10 px-4 py-1.5 text-xs text-amber-200",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400"
      />
      Fictional SaaS demo data — Payments Core and Cloud Infrastructure
    </div>
  );
}