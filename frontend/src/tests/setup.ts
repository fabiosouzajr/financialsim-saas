import "@testing-library/jest-dom";

// jsdom doesn't implement ResizeObserver (used by Recharts/Radix)
(globalThis as unknown as Record<string, unknown>).ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};
