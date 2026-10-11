import { describe, expect, it } from "vitest";
import demoDayJson from "../../fixtures/demo-day.json";
import type { NormalizedGameState } from "../../shared_ts/models";
import { deriveBindings } from "../../shared_ts/renderer";
import { withBroadcastPreviewMoment } from "./broadcastPreview";

const sourceGame = (demoDayJson as NormalizedGameState[]).find((game) => game.status === "in_progress")!;

describe("broadcast event previews", () => {
  it("leaves the actual game untouched", () => {
    const before = structuredClone(sourceGame);
    const preview = withBroadcastPreviewMoment(sourceGame, "single")!;

    expect(preview).not.toBe(sourceGame);
    expect(sourceGame).toEqual(before);
    expect(withBroadcastPreviewMoment(sourceGame, "live")).toBe(sourceGame);
  });

  it("shows deterministic hit results and bases", () => {
    const single = withBroadcastPreviewMoment(sourceGame, "single")!;
    const double = withBroadcastPreviewMoment(sourceGame, "double")!;
    const triple = withBroadcastPreviewMoment(sourceGame, "triple")!;

    expect(deriveBindings(single).broadcastContextDisplay).toBe("SINGLE  96 MPH");
    expect(single.bases).toEqual({ first: true, second: false, third: false });
    expect(deriveBindings(double).broadcastContextDisplay).toBe("DOUBLE  101 MPH");
    expect(double.bases).toEqual({ first: false, second: true, third: false });
    expect(deriveBindings(triple).broadcastContextDisplay).toBe("TRIPLE  103 MPH");
    expect(triple.bases).toEqual({ first: false, second: false, third: true });
  });

  it("shows home run measurements and scores the batting team", () => {
    const preview = withBroadcastPreviewMoment(sourceGame, "homeRun")!;

    expect(deriveBindings(preview).broadcastContextDisplay).toBe("HOME RUN  394 FT  109 MPH");
    expect(preview.away.score).toBe((sourceGame.away.score ?? 0) + 1);
    expect(preview.home.score).toBe(sourceGame.home.score);
  });

  it("shows a distinct grand slam and four-run score change", () => {
    const preview = withBroadcastPreviewMoment(sourceGame, "grandSlam")!;

    expect(deriveBindings(preview).broadcastContextDisplay).toBe("GRAND SLAM  421 FT  110 MPH");
    expect(preview.away.score).toBe((sourceGame.away.score ?? 0) + 4);
  });
});
