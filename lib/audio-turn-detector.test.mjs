import assert from "node:assert/strict";
import test from "node:test";

import { AudioTurnDetector } from "./audio-turn-detector.ts";

test("a pause inside caller speech does not create duplicate turns", () => {
  const detector = new AudioTurnDetector();
  for (const time of [0, 100, 200]) assert.equal(detector.update(time, true, false), null);
  assert.equal(detector.update(500, false, false), null);
  for (const time of [520, 620, 720]) assert.equal(detector.update(time, true, false), null);
  assert.equal(detector.update(1400, false, false), null);
  assert.equal(detector.update(1800, false, true), null);
  assert.equal(detector.update(1880, false, true), 1.08);
  assert.equal(detector.update(1960, false, true), null);
});

test("overlapping caller and agent audio is not attributed as a response", () => {
  const detector = new AudioTurnDetector();
  detector.update(0, true, false);
  detector.update(200, true, false);
  detector.update(250, true, true);
  detector.update(330, true, true);
  detector.update(500, false, true);
  assert.equal(detector.update(700, false, true), null);
});

test("brief noise and responses that never arrive are not recorded", () => {
  const detector = new AudioTurnDetector();
  detector.update(0, true, false);
  detector.update(40, true, false);
  detector.update(700, false, false);
  detector.update(1000, false, true);
  assert.equal(detector.update(1080, false, true), null);
});

test("a caller who resumes before the reply replaces the pending speech end", () => {
  const detector = new AudioTurnDetector();
  detector.update(0, true, false);
  detector.update(200, true, false);
  detector.update(850, false, false);
  detector.update(900, true, false);
  detector.update(1100, true, false);
  detector.update(1750, false, false);
  detector.update(2100, false, true);
  assert.equal(detector.update(2180, false, true), 1);
});
