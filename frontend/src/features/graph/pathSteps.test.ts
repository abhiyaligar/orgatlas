import { describe, expect, it } from "vitest";

import { parsePath, parsePaths } from "./pathSteps";

describe("parsePath", () => {
  it("returns nothing for an empty path", () => {
    expect(parsePath("").steps).toEqual([]);
    expect(parsePath("   ").steps).toEqual([]);
  });

  it("reads a single node with no hops", () => {
    expect(parsePath("Kafka [Technology]").steps).toEqual([
      { position: 1, name: "Kafka", label: "Technology", edgeIn: null },
    ]);
  });

  it("keeps the traversal order the backend chose", () => {
    const { steps } = parsePath("Checkout [Service] ──USES──> Kafka [Technology]");

    expect(steps.map((step) => step.position)).toEqual([1, 2]);
    expect(steps.map((step) => step.name)).toEqual(["Checkout", "Kafka"]);
    expect(steps[0].edgeIn).toBeNull();
    expect(steps[1].edgeIn).toBe("USES");
  });

  it("records the edge that leads into every step of a longer chain", () => {
    const { steps } = parsePath(
      "Incident [Incident] ──LED_TO──> Kafka [Decision] ──DECIDED_BY──> Dana [Person] ──MEMBER_OF──> Payments [Team]",
    );

    expect(steps).toHaveLength(4);
    expect(steps.map((step) => step.edgeIn)).toEqual([
      null,
      "LED_TO",
      "DECIDED_BY",
      "MEMBER_OF",
    ]);
    expect(steps[3]).toEqual({
      position: 4,
      name: "Payments",
      label: "Team",
      edgeIn: "MEMBER_OF",
    });
  });

  it("keeps a node whose label is absent", () => {
    const { steps } = parsePath("Checkout ──USES──> Kafka");

    expect(steps[0].label).toBeNull();
    expect(steps[1]).toEqual({ position: 2, name: "Kafka", label: null, edgeIn: "USES" });
  });

  it("does not mistake a bracket inside a name for a label", () => {
    const { steps } = parsePath("queue[worker] [Service] ──USES──> Kafka [Technology]");

    expect(steps[0]).toEqual({
      position: 1,
      name: "queue[worker]",
      label: "Service",
      edgeIn: null,
    });
  });

  it("always preserves the original text for the fallback", () => {
    const raw = "Checkout [Service] ──USES──> Kafka [Technology]";
    expect(parsePath(raw).raw).toBe(raw);
  });

  it("survives a format it does not recognise", () => {
    // A future backend format must still show something rather than vanish.
    const { steps, raw } = parsePath("Checkout ===> Kafka");

    expect(raw).toBe("Checkout ===> Kafka");
    expect(steps).toHaveLength(1);
  });

  it("ignores empty hops rather than producing a nameless step", () => {
    const { steps } = parsePath("Checkout [Service] ──────> Kafka [Technology]");

    expect(steps.map((step) => step.name)).toEqual(["Checkout", "Kafka"]);
    expect(steps[1].edgeIn).toBeNull();
  });
});

describe("parsePaths", () => {
  it("drops paths with nothing in them", () => {
    expect(parsePaths(["", "Kafka [Technology]"])).toHaveLength(1);
  });

  it("tolerates a missing list", () => {
    expect(parsePaths(null)).toEqual([]);
    expect(parsePaths(undefined)).toEqual([]);
  });
});