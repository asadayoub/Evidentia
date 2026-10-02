import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("Evidentia application shell", () => {
  it("identifies the product and governed bootstrap state", () => {
    render(<App />);

    expect(
      screen.getByRole("heading", { name: "Evidentia" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Governed foundation")).toBeInTheDocument();
  });
});
