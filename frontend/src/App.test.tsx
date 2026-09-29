import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("affiche le nom du projet et le statut des fondations", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "GuitarRiff" })).toBeInTheDocument();
    expect(screen.getByText(/fondations du projet en place/i)).toBeInTheDocument();
  });
});
