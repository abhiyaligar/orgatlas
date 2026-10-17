import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RepositoriesView } from "@/features/repos/RepositoriesView";
import type * as ApiClientModule from "@/services/apiClient";
import type { RepositorySummary } from "@/types";

vi.mock("@/services/apiClient", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/services/apiClient");
  return {
    ...actual,
    fetchRepositories: () => Promise.resolve(repositories),
    fetchRepoBrief: () =>
      Promise.resolve({
        repository_id: "repo_real",
        path_prefix: "",
        hotspots: [],
        contributors: [],
        dependency_blast_radius: [],
        guidance: ["Start with the commit list."],
      }),
    fetchRepoChurn: () => Promise.resolve({ repository_id: "repo_real", path_prefix: "", files: [], hotspots: [] }),
    fetchRepoCommits: () => Promise.resolve([]),
    fetchFileTimeline: () => Promise.reject(new Error("not needed")),
    fetchFileDescription: () => Promise.reject(new Error("not needed")),
    startIngest: () => Promise.reject(new Error("not needed")),
    fetchIngestJob: () => Promise.reject(new Error("not needed")),
  };
});

const repositories: RepositorySummary[] = [
  {
    id: "repo_real",
    name: "real/repo",
    url: "https://github.com/real/repo",
    source: "github",
    commit_count: 320,
    file_count: 329,
    dependencies: [],
  },
  {
    id: "repo_dep",
    name: "real/dependency",
    url: "https://github.com/real/dependency",
    source: "github",
    commit_count: 0,
    file_count: 0,
    dependencies: [],
  },
  {
    id: "repo_checkout",
    name: "acme/checkout-service",
    url: "https://github.com/acme/checkout-service",
    source: null,
    commit_count: 0,
    file_count: 0,
    dependencies: [],
  },
];

beforeEach(() => {
  vi.clearAllMocks();
});

describe("RepositoriesView", () => {
  it("separates ingested repositories from metadata-only and seeded ones", async () => {
    render(<RepositoriesView />);

    const ingested = await screen.findByRole("region", { name: /ingested/i });
    const others = screen.getByRole("region", { name: /declared and seeded/i });

    expect(ingested).toHaveTextContent("real/repo");
    expect(ingested).not.toHaveTextContent("real/dependency");

    expect(others).toHaveTextContent("real/dependency");
    expect(others).toHaveTextContent("acme/checkout-service");
  });

  it("labels a dependency that was recorded but never cloned", async () => {
    render(<RepositoriesView />);

    const others = await screen.findByRole("region", { name: /declared and seeded/i });
    expect(others).toHaveTextContent("declared dependency, not cloned");
    expect(others).toHaveTextContent("no code ingested");
  });

  it("does not offer code panels for a repository with no ingested code", async () => {
    const user = userEvent.setup();
    render(<RepositoriesView />);

    const seededCard = await screen.findByRole("button", { name: /acme\/checkout-service/ });
    await user.click(seededCard);

    await waitFor(() => expect(screen.getByText("Start with the commit list.")).toBeInTheDocument());
    expect(screen.queryByText("Recent commits")).not.toBeInTheDocument();
    expect(screen.queryByText("Declared dependencies")).not.toBeInTheDocument();
    expect(screen.queryByText("Symbol lookup")).not.toBeInTheDocument();
  });

  it("offers the code panels for an ingested repository", async () => {
    const user = userEvent.setup();
    render(<RepositoriesView />);

    const card = await screen.findByRole("button", { name: /real\/repo/ });
    await user.click(card);

    expect(await screen.findByText("Recent commits")).toBeInTheDocument();
    expect(screen.getByText("Declared dependencies")).toBeInTheDocument();
    expect(screen.getByText("Symbol lookup")).toBeInTheDocument();
  });
});