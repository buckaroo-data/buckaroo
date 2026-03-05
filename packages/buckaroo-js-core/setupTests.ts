import "@testing-library/jest-dom";
import { vi } from "vitest";

// jest compat: tests use jest.fn() — map to vi.fn()
(globalThis as Record<string, unknown>).jest = vi;
