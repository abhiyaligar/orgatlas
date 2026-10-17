import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceTrail } from "./EvidenceTrail";

const PATH = "Checkout [Service] ──USES──> Kafka [Technology] ──OWNED_BY──> Dana [Person]";

describe("EvidenceTrail", () => {
  it("renders nothing when there is no path", () => {
    const { container } = render(<EvidenceTrail paths={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("shows every node the walk touched", () => {
    render(<EvidenceTrail paths={[PATH]} />);

    expect(screen.getByText("Checkout")).toBeInTheDocument();
    expect(screen.getByText("Kafka")).toBeInTheDocument();
    expect(screen.getByText("Dana")).toBeInTheDocument();
  });

  it("numbers the steps so the order is unambiguous", () => {
    render(<EvidenceTrail paths={[PATH]} />);

    const steps = screen.getAllByRole("listitem");
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveTextContent("1");
    expect(steps[1]).toHaveTextContent("2");
    expect(steps[2]).toHaveTextContent("3");
  });

  it("labels which edge led into each step", () => {
    render(<EvidenceTrail paths={[PATH]} />);

    expect(screen.getByText("USES")).toBeInTheDocument();
    expect(screen.getByText("OWNED_BY")).toBeInTheDocument();
  });

  it("shows the graph label of each node", () => {
    render(<EvidenceTrail paths={[PATH]} />);

    expect(screen.getByText("Service")).toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(screen.getByText("Person")).toBeInTheDocument();
  });

  it("marks the focused node so the trail agrees with the graph", () => {
    render(<EvidenceTrail paths={[PATH]} focusedNodeName="Kafka" />);

    const focused = document.querySelector('[data-focused="true"]');
    expect(focused).toHaveTextContent("Kafka");
    expect(document.querySelectorAll('[data-focused="true"]')).toHaveLength(1);
  });

  it("leaves every step unmarked when nothing is focused", () => {
    render(<EvidenceTrail paths={[PATH]} />);

    expect(document.querySelector('[data-focused="true"]')).toBeNull();
  });

  it("counts multiple paths separately", () => {
    render(
      <EvidenceTrail
        paths={[PATH, "Kafka [Technology] ──USED_BY──> Checkout [Service]"]}
      />,
    );

    expect(screen.getByText("Path 1")).toBeInTheDocument();
    expect(screen.getByText("Path 2")).toBeInTheDocument();
  });

  it("falls back to the raw text for a single node", () => {
    render(<EvidenceTrail paths={["Kafka [Technology]"]} />);

    expect(screen.getByText("Kafka [Technology]")).toBeInTheDocument();
  });
});