import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/services/apiClient";
import { AskWorkspace } from "@/features/ask/AskWorkspace";
import type * as ApiClientModule from "@/services/apiClient";
import type { AskQuestionResponse } from "@/types";

const mockedAskQuestion = vi.fn();

vi.mock("@/services/apiClient", async () => {
  const actual = await vi.importActual<typeof ApiClientModule>("@/services/apiClient");
  return {
    ...actual,
    askQuestion: (body: unknown) => mockedAskQuestion(body),
    fetchDemoPrompts: () =>
      Promise.resolve([
        {
          id: "prompt_kafka_decision",
          prompt: "Why does Checkout use Kafka instead of synchronous calls?",
          intent: "decision_trace",
          expected_entities: ["dec_kafka_async"],
        },
      ]),
  };
});

const supportedResponse: AskQuestionResponse = {
  answer: "**Decision:** Adopt Kafka for payment processing.",
  evidence_summary: "Traced from the FalkorDB decision graph. 2 source(s) found.",
  citations: [
    { source_id: "doc_rfp_kafka", title: "RFC-042", type: "design_doc" },
    { source_id: "doc_postmortem_2024_03", title: "SEV-1 Postmortem", type: "postmortem" },
  ],
  graph: {
    nodes: [
      { id: "dec_kafka_async", label: "Decision", name: "Adopt Kafka", properties: {} },
      { id: "doc_rfp_kafka", label: "Document", name: "RFC-042", properties: {} },
    ],
    edges: [
      { id: "e1", source: "dec_kafka_async", target: "doc_rfp_kafka", type: "SUPPORTED_BY", properties: {} },
    ],
    paths: ["Adopt Kafka [Decision] ──SUPPORTED_BY──> RFC-042 [Document]"],
  },
  confidence: "supported",
  suggested_questions: ["Who owns Token Service and which services depend on it?"],
};

beforeEach(() => {
  mockedAskQuestion.mockReset();
});

describe("AskWorkspace", () => {
  it("shows an empty state before any question is asked", async () => {
    render(<AskWorkspace />);
    expect(await screen.findByText("No question asked yet")).toBeInTheDocument();
  });

  it("renders the demo prompts returned by the API", async () => {
    render(<AskWorkspace />);
    expect(
      await screen.findByRole("button", {
        name: "Why does Checkout use Kafka instead of synchronous calls?",
      }),
    ).toBeInTheDocument();
  });

  it("submits a typed question", async () => {
    mockedAskQuestion.mockResolvedValue(supportedResponse);
    const user = userEvent.setup();
    render(<AskWorkspace />);

    const input = await screen.findByLabelText(/Ask about a system/i);
    await user.type(input, "Who owns Token Service?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await waitFor(() =>
      expect(mockedAskQuestion).toHaveBeenCalledWith({ question: "Who owns Token Service?" }),
    );
  });

  it("renders an answer with its citations and confidence", async () => {
    mockedAskQuestion.mockResolvedValue(supportedResponse);
    const user = userEvent.setup();
    render(<AskWorkspace />);

    await user.click(
      await screen.findByRole("button", {
        name: "Why does Checkout use Kafka instead of synchronous calls?",
      }),
    );

    expect(await screen.findByText("Supported")).toBeInTheDocument();
    expect(await screen.findByText("RFC-042")).toBeInTheDocument();
    expect(await screen.findByText("SEV-1 Postmortem")).toBeInTheDocument();
  });

  it("opens the source drawer when a citation is selected", async () => {
    mockedAskQuestion.mockResolvedValue(supportedResponse);
    const user = userEvent.setup();
    render(<AskWorkspace />);

    await user.click(
      await screen.findByRole("button", {
        name: "Why does Checkout use Kafka instead of synchronous calls?",
      }),
    );

    await user.click(await screen.findByText("RFC-042"));
    expect(await screen.findByText("Source detail")).toBeInTheDocument();
    expect(screen.getAllByText("doc_rfp_kafka").length).toBeGreaterThan(0);
  });

  it("surfaces an API failure instead of rendering an answer", async () => {
    mockedAskQuestion.mockRejectedValue(new ApiError("Knowledge graph query failed", 503));
    const user = userEvent.setup();
    render(<AskWorkspace />);

    await user.click(
      await screen.findByRole("button", {
        name: "Why does Checkout use Kafka instead of synchronous calls?",
      }),
    );

    expect(await screen.findByText(/Request failed \(503\)/)).toBeInTheDocument();
    expect(screen.queryByText("Supported")).not.toBeInTheDocument();
  });

  it("reports insufficient evidence without inventing sources", async () => {
    mockedAskQuestion.mockResolvedValue({
      answer: "Insufficient evidence was found in the knowledge graph.",
      evidence_summary: "No supporting graph paths were found.",
      citations: [],
      graph: { nodes: [], edges: [], paths: [] },
      confidence: "insufficient",
      suggested_questions: [],
    });
    const user = userEvent.setup();
    render(<AskWorkspace />);

    await user.click(
      await screen.findByRole("button", {
        name: "Why does Checkout use Kafka instead of synchronous calls?",
      }),
    );

    expect(await screen.findByText("Insufficient evidence")).toBeInTheDocument();
    expect(screen.getByText(/backed by graph relationships only/i)).toBeInTheDocument();
  });
});
