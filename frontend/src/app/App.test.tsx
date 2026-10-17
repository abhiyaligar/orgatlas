import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "@/app/App";
import { ThemeProvider } from "@/components/theme/ThemeProvider";
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

function renderApp() {
  return render(
    <ThemeProvider>
      <App />
    </ThemeProvider>,
  );
}

describe("App", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.location.hash = "";
  });

  it("opens on the landing page", () => {
    renderApp();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      /Ask why something was built/i,
    );
  });

  it("explains what the product does", () => {
    renderApp();

    expect(screen.getByText("The decision is gone")).toBeInTheDocument();
    expect(screen.getByText("The context is scattered")).toBeInTheDocument();
    expect(screen.getByText("Ask in plain language")).toBeInTheDocument();
    expect(screen.getByText("Honest about limits")).toBeInTheDocument();
  });

  it("offers a dashboard button that opens the workspace", async () => {
    const user = userEvent.setup();
    renderApp();

    await user.click(screen.getAllByRole("button", { name: /dashboard/i })[0]);

    expect(screen.getByText(/Fictional SaaS demo data/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Graph Explorer" })).toBeInTheDocument();
  });

  it("renders the shell with navigation and the demo-data banner", () => {
    window.location.hash = "#/app";
    renderApp();

    expect(screen.getByText("ORGATLAS")).toBeInTheDocument();
    expect(screen.getByText(/Fictional SaaS demo data/i)).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });

  it("offers the three primary views", () => {
    window.location.hash = "#/app";
    renderApp();

    expect(screen.getByRole("button", { name: "Onboarding Map" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ask & Archaeology" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Graph Explorer" })).toBeInTheDocument();
  });

  it("starts on the ask workspace and can switch views", async () => {
    window.location.hash = "#/app";
    const user = userEvent.setup();
    renderApp();

    expect(screen.getByText("No question asked yet")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Graph Explorer" }));
    expect(screen.getByText("No graph to display")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Onboarding Map" }));
    expect(await screen.findByLabelText("Team")).toBeInTheDocument();
  });
});