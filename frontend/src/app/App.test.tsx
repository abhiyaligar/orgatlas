import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "@/app/App";

describe("App", () => {
  it("renders the OrgAtlas baseline", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: /engineering context, connected/i }),
    ).toBeInTheDocument();
  });
});
