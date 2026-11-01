import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { PLATFORMS, PLATFORM_BY_ID, PLATFORM_GROUPS, capabilityBadge } from "../platforms";

// Parse the backend's PLATFORMS tuple so the web picker can't silently drift
// from what /generate actually accepts.
function backendPlatforms(): string[] {
  const src = readFileSync(
    fileURLToPath(new URL("../../../backend/app/agent.py", import.meta.url)),
    "utf8",
  );
  const block = src.match(/^PLATFORMS = \(([\s\S]*?)^\)/m);
  if (!block) throw new Error("PLATFORMS tuple not found in backend/app/agent.py");
  return [...block[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
}

describe("platform metadata", () => {
  it("matches the backend's supported platforms exactly", () => {
    const backend = backendPlatforms();
    expect(backend).toHaveLength(15);
    expect(PLATFORMS.map((p) => p.id).sort()).toEqual([...backend].sort());
  });

  it("has unique ids and a lookup entry for each", () => {
    const ids = PLATFORMS.map((p) => p.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const p of PLATFORMS) expect(PLATFORM_BY_ID[p.id]).toBe(p);
  });

  it("every platform belongs to a declared group with a hex accent", () => {
    const groups = new Set(PLATFORM_GROUPS.map((g) => g.id));
    for (const p of PLATFORMS) {
      expect(groups.has(p.group)).toBe(true);
      expect(p.accent).toMatch(/^#[0-9A-F]{6}$/i);
      expect(p.Icon).toBeTypeOf("function");
    }
    // No empty groups in the picker.
    for (const g of groups) expect(PLATFORMS.some((p) => p.group === g)).toBe(true);
  });

  it("capability badges exist for every capability in use", () => {
    for (const p of PLATFORMS) {
      const badge = capabilityBadge(p.capability);
      expect(badge.label).toBeTruthy();
      expect(badge.tone).toContain("bg-");
    }
  });

  it("only email uses mailto", () => {
    expect(PLATFORMS.filter((p) => p.capability === "mailto").map((p) => p.id)).toEqual(["email"]);
  });
});
