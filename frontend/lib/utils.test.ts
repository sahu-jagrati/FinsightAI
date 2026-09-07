import { describe, expect, it } from "vitest";
import { cn, formatDuration, formatPercent, titleCase } from "./utils";

describe("cn", () => {
  it("merges class names and resolves tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
    expect(cn("text-sm", undefined, "font-medium")).toBe("text-sm font-medium");
  });
});

describe("formatPercent", () => {
  it("formats a fraction as a percentage with one decimal by default", () => {
    expect(formatPercent(0.1447)).toBe("14.5%");
  });

  it("respects the digits argument", () => {
    expect(formatPercent(0.5, 0)).toBe("50%");
  });

  it("handles negative values", () => {
    expect(formatPercent(-0.2)).toBe("-20.0%");
  });
});

describe("formatDuration", () => {
  it("renders an em dash for null/undefined", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });

  it("renders sub-second durations in ms", () => {
    expect(formatDuration(340)).toBe("340ms");
  });

  it("renders durations >= 1s in seconds", () => {
    expect(formatDuration(1500)).toBe("1.50s");
  });
});

describe("titleCase", () => {
  it("converts snake_case metric names to Title Case", () => {
    expect(titleCase("net_income")).toBe("Net Income");
    expect(titleCase("revenue")).toBe("Revenue");
  });
});
