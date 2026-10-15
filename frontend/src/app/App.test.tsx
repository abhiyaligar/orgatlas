import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import type * as ApiClientModule from "@/services/apiClient";

vi.mock("@/services/apiClient", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/services/apiClient");
  return {
    ...actual,
    fetchDemoPrompts: () => Promise.resolve([]),
    fetchOnboarding: () => Promise.reject(new Error("not used in this test")),
    askQuestion: () => Promise.reject(new Error("not used in this test")),
  };
});

describe("App", () => {
  it("renders the shell with navigation and the demo-data banner", () => {
    render(<App />);

    expect(screen.getByText("ORGATLAS")).toBeInTheDocument();
    expect(screen.getByText(/Fictional SaaS demo data/i)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("offers the three primary views", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "Onboarding Map" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask & Archaeology" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Graph Explorer" })).toBeInTheDocument();
  });

  it("starts on the ask workspace and can switch views", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByText("No question asked yet")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Graph Explorer" }));
    expect(screen.getByText("No graph to display")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Onboarding Map" }));
    expect(await screen.findByLabelText("Team")).toBeInTheDocument();
  });
});
