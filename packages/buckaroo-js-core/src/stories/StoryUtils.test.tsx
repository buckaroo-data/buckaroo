import React from "react";
import { render, waitFor } from "@testing-library/react";

jest.mock("react", () => {
  const actual = jest.requireActual("react");
  return {
    __esModule: true,
    ...actual,
    default: actual,
  };
});

jest.mock("react-dom/client", () => {
  const actual = jest.requireActual("react-dom/client");
  return {
    __esModule: true,
    ...actual,
    default: actual,
  };
});

jest.mock(
  "../style/dcf-npm.css?raw",
  () => ({
    __esModule: true,
    default: ".ag-icon-asc { display: block; }",
  }),
  { virtual: true },
);

import { ShadowDomWrapper } from "./StoryUtils";

describe("ShadowDomWrapper", () => {
  it("renders children inside a ShadowRoot and injects style text", async () => {
    const { container } = render(
      <ShadowDomWrapper>
        <div data-testid="inside">hello</div>
      </ShadowDomWrapper>,
    );

    await waitFor(() => {
      const host = container.firstElementChild as HTMLDivElement | null;
      expect(host).not.toBeNull();
      expect(host?.shadowRoot).not.toBeNull();
      const inner = host?.shadowRoot?.querySelector("[data-testid='inside']");
      expect(inner).not.toBeNull();
    });

    const host = container.firstElementChild as HTMLDivElement;
    const shadowRoot = host.shadowRoot as ShadowRoot;
    const styleTag = shadowRoot.querySelector("style") as HTMLStyleElement | null;

    expect(styleTag).not.toBeNull();
    expect((styleTag?.textContent || "").includes(".ag-icon-asc")).toBe(true);
  });

  it("keeps a single injected style tag across rerenders", async () => {
    const { container, rerender } = render(
      <ShadowDomWrapper>
        <div data-testid="one">one</div>
      </ShadowDomWrapper>,
    );

    await waitFor(() => {
      const host = container.firstElementChild as HTMLDivElement | null;
      const one = host?.shadowRoot?.querySelector("[data-testid='one']");
      expect(one).not.toBeNull();
    });

    rerender(
      <ShadowDomWrapper>
        <div data-testid="two">two</div>
      </ShadowDomWrapper>,
    );

    await waitFor(() => {
      const host = container.firstElementChild as HTMLDivElement | null;
      const two = host?.shadowRoot?.querySelector("[data-testid='two']");
      expect(two).not.toBeNull();
    });

    const host = container.firstElementChild as HTMLDivElement;
    const styleCount = host.shadowRoot?.querySelectorAll("style").length || 0;
    expect(styleCount).toBe(1);
  });
});
