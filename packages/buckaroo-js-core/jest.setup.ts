declare global {
  namespace jest {
    interface Matchers<R> {
      toBeInTheDocument(): R;
      toHaveClass(...classNames: string[]): R;
    }
  }
}

expect.extend({
  toBeInTheDocument(received: unknown) {
    const element = received as Element | null | undefined;
    const pass =
      !!element && !!element.ownerDocument && element.ownerDocument.contains(element);
    return {
      pass,
      message: () =>
        pass
          ? "expected element not to be in the document"
          : "expected element to be in the document",
    };
  },
  toHaveClass(received: unknown, ...classNames: string[]) {
    const element = received as Element | null | undefined;
    const classList = element?.classList;
    const pass = !!classList && classNames.every((className) => classList.contains(className));
    return {
      pass,
      message: () =>
        pass
          ? `expected element not to include classes: ${classNames.join(", ")}`
          : `expected element to include classes: ${classNames.join(", ")}`,
    };
  },
});

(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
