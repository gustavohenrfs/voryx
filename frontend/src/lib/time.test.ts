import { describe, expect, it } from "vitest";
import { dayKey, fromSaoPauloInput, toSaoPaulo } from "./time";

describe("time helpers (America/Sao_Paulo)", () => {
  it("builds an ISO string with the -03:00 offset", () => {
    expect(fromSaoPauloInput("2026-11-10", "20:00")).toBe("2026-11-10T20:00:00-03:00");
  });

  it("formats a UTC instant in São Paulo time", () => {
    expect(toSaoPaulo("2026-11-10T23:00:00Z")).toBe("10/11 20:00");
  });

  it("groups by São Paulo calendar day, not UTC day", () => {
    expect(dayKey("2026-11-11T01:30:00Z")).toBe("2026-11-10");
  });
});
