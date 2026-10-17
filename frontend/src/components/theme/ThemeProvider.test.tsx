import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeProvider } from "./ThemeProvider";
import { useTheme } from "./themeContext";
import { ThemeToggle } from "./ThemeToggle";

/**
 * jsdom ships no useful matchMedia, and replacing it globally leaks into every
 * later test in the file. Restoring the original is what keeps the "system
 * prefers dark" cases from silently deciding the ones that follow.
 */
const originalMatchMedia = window.matchMedia;

function setPrefersDark(prefersDark: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: prefersDark && query.includes("dark"),
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    onchange: null,
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

function Harness() {
  const { theme } = useTheme();
  return (
    <div>
      <ThemeToggle />
      <span data-testid="theme">{theme}</span>
    </div>
  );
}

function renderHarness() {
  return render(
    <ThemeProvider>
      <Harness />
    </ThemeProvider>,
  );
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    setPrefersDark(false);
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("defaults to light and marks the document as light", () => {
    renderHarness();

    expect(screen.getByTestId("theme")).toHaveTextContent("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("switches to dark and records it on the document element", async () => {
    const user = userEvent.setup();
    renderHarness();

    await user.click(screen.getByRole("button"));

    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("remembers the choice across a reload", async () => {
    const user = userEvent.setup();
    const first = renderHarness();
    await user.click(screen.getByRole("button"));
    first.unmount();

    renderHarness();

    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
  });

  it("offers dark when the system asks for it and nothing is stored", () => {
    setPrefersDark(true);

    renderHarness();

    expect(screen.getByTestId("theme")).toHaveTextContent("dark");
  });

  it("lets a stored choice win over the system preference", () => {
    window.localStorage.setItem("orgatlas.theme", "light");
    setPrefersDark(true);

    renderHarness();

    expect(screen.getByTestId("theme")).toHaveTextContent("light");
  });

  it("falls back to light when storage is unavailable", () => {
    const original = window.localStorage.getItem;
    window.localStorage.getItem = () => {
      throw new Error("blocked");
    };

    try {
      renderHarness();
      expect(screen.getByTestId("theme")).toHaveTextContent("light");
    } finally {
      window.localStorage.getItem = original;
    }
  });
});

describe("ThemeToggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark");
    setPrefersDark(false);
  });

  it("advertises the theme it will switch to", async () => {
    const user = userEvent.setup();
    renderHarness();

    expect(screen.getByRole("button")).toHaveAccessibleName("Switch to dark theme");

    await user.click(screen.getByRole("button"));

    expect(screen.getByRole("button")).toHaveAccessibleName("Switch to light theme");
  });
});