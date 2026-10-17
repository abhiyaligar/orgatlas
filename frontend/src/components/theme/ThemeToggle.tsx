import { Moon, Sun } from "lucide-react";

import { useTheme } from "@/components/theme/themeContext";

/**
 * The icon states the theme you are switching *to*, not the one you are in,
 * so the control reads as "go dark" while the page is light.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const { theme, toggleTheme } = useTheme();
  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={`Switch to ${nextTheme} theme`}
      title={`Switch to ${nextTheme} theme`}
      className={[
        "inline-flex h-9 w-9 items-center justify-center rounded-md border border-border",
        "bg-background text-foreground transition-colors",
        "hover:bg-accent hover:text-accent-foreground",
        "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
        className,
      ].join(" ")}
    >
      {theme === "dark" ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}