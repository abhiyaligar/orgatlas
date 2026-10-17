import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/apiClient";
import { RepoIngestPanel } from "@/features/repos/RepoIngestPanel";
import type * as ApiClientModule from "@/services/apiClient";
import type { IngestJobResponse } from "@/types";

const mockedStartIngest = vi.fn();
const mockedFetchIngestJob = vi.fn();

vi.mock("@/services/apiClient", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/services/apiClient");
  return {
    ...actual,
    startIngest: (body: unknown) => mockedStartIngest(body),
    fetchIngestJob: (jobId: number) => mockedFetchIngestJob(jobId),
  };
});

function job(overrides: Partial<IngestJobResponse> = {}): IngestJobResponse {
  return {
    id: 7,
    repository_url: "https://github.com/FalkorDB/FalkorDB",
    repository_id: "repo_falkordb",
    status: "queued",
    stage_detail: null,
    commits_ingested: 0,
    files_indexed: 0,
    identities_resolved: 0,
    error_message: null,
    created_at: "2026-01-01T00:00:00Z",
    completed_at: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockedStartIngest.mockReset();
  mockedFetchIngestJob.mockReset();
});

/** Poll fast so tests do not wait on the production interval. */
function renderPanel(props: { onIngested?: () => void } = {}) {
  return render(<RepoIngestPanel intervalMs={5} {...props} />);
}

describe("RepoIngestPanel", () => {
  it("starts a job with the entered URL", async () => {
    mockedStartIngest.mockResolvedValue(job());
    const user = userEvent.setup();
    renderPanel();

    const input = await screen.findByLabelText(/Public repository URL/i);
    await user.clear(input);
    await user.type(input, "https://github.com/owner/repo");
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() =>
      expect(mockedStartIngest).toHaveBeenCalledWith({
        repository_url: "https://github.com/owner/repo",
      }),
    );
  });

  it("refuses to start a job without a URL", async () => {
    const user = userEvent.setup();
    renderPanel();

    const input = await screen.findByLabelText(/Public repository URL/i);
    await user.clear(input);
    await user.click(screen.getByRole("button", { name: "Ingest" }));

    expect(await screen.findByText("Enter a repository URL")).toBeInTheDocument();
    expect(mockedStartIngest).not.toHaveBeenCalled();
  });

  it("shows the running stage and the counts once the job reports progress", async () => {
    mockedStartIngest.mockResolvedValue(job({ status: "cloning" }));
    mockedFetchIngestJob.mockResolvedValue(
      job({
        status: "writing",
        stage_detail: "batch 6/13 MERGE",
        commits_ingested: 120,
        files_indexed: 300,
        identities_resolved: 4,
      }),
    );

    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Ingest" }));

    await waitFor(() => expect(screen.getByText("batch 6/13 MERGE")).toBeInTheDocument());
    await waitFor(() => expect(mockedFetchIngestJob).toHaveBeenCalledWith(7));

    expect(await screen.findByText("300")).toBeInTheDocument();
    expect(screen.getByText("120")).toBeInTheDocument();
    expect(screen.getByText("4")).toBeInTheDocument();
  });

  it("reports the failure reason instead of counts when a job fails", async () => {
    mockedStartIngest.mockResolvedValue(job({ status: "cloning" }));
    mockedFetchIngestJob.mockResolvedValue(
      job({ status: "failed", error_message: "Sandbox image build failed" }),
    );

    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Ingest" }));

    expect(
      await screen.findByText("Sandbox image build failed", undefined, { timeout: 6000 }),
    ).toBeInTheDocument();
  });

  it("surfaces a request failure when the job cannot be created", async () => {
    mockedStartIngest.mockRejectedValue(new ApiError("Ingestion queue unavailable", 503));

    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Ingest" }));

    expect(await screen.findByText("Ingestion queue unavailable")).toBeInTheDocument();
  });

  it("marks the job complete once it reports done", async () => {
    mockedStartIngest.mockResolvedValue(job({ status: "cloning" }));
    mockedFetchIngestJob.mockResolvedValue(
      job({ status: "done", commits_ingested: 320, files_indexed: 329, identities_resolved: 5 }),
    );
    const onIngested = vi.fn();

    const user = userEvent.setup();
    renderPanel({ onIngested });

    await user.click(screen.getByRole("button", { name: "Ingest" }));

    const refresh = await screen.findByRole(
      "button",
      { name: "Refresh repository list" },
      { timeout: 6000 },
    );
    await user.click(refresh);
    expect(onIngested).toHaveBeenCalled();
  });
});