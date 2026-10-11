import single64x32p4 from "../../targets/linux-sbc-hub75/profiles/single-64x32-p4.json";
import single64x32p5 from "../../targets/linux-sbc-hub75/profiles/single-64x32-p5.json";
import square64x64p3 from "../../targets/linux-sbc-hub75/profiles/square-64x64-p3.json";
import ticker128x32p3 from "../../targets/linux-sbc-hub75/profiles/ticker-128x32-p3.json";
import ticker128x32p4 from "../../targets/linux-sbc-hub75/profiles/ticker-128x32-p4.json";
import ticker128x32p5 from "../../targets/linux-sbc-hub75/profiles/ticker-128x32-p5.json";
import wide192x32p4 from "../../targets/linux-sbc-hub75/profiles/wide-192x32-p4.json";
import definitionJson from "../../definition/mlb-classic/display-definition.json";
import demoDayJson from "../../fixtures/demo-day.json";
import emptyDayJson from "../../fixtures/empty-day.json";
import demoStandingsJson from "../../fixtures/demo-standings.json";
import teamStandingsJson from "../../fixtures/team-standings.json";
import font4x6 from "../../definition/mlb-classic/fonts/4x6.bdf?url";
import font5x7 from "../../definition/mlb-classic/fonts/5x7.bdf?url";
import font6x10 from "../../definition/mlb-classic/fonts/6x10.bdf?url";
import type { DeviceProfile, NormalizedGameState, StandingsState } from "../../shared_ts/models";

export const profiles = [
  ticker128x32p3,
  ticker128x32p4,
  ticker128x32p5,
  single64x32p4,
  single64x32p5,
  square64x64p3,
  wide192x32p4
] as DeviceProfile[];

export const definition = definitionJson;
export const demoDay = demoDayJson as NormalizedGameState[];
export const emptyDay = emptyDayJson as NormalizedGameState[];
export const demoStandings = demoStandingsJson as StandingsState[];
export const teamStandings = teamStandingsJson as StandingsState[];
export const fontUrls = { "4x6": font4x6, "5x7": font5x7, "6x10": font6x10 } as const;
