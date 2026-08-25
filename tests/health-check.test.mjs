import assert from "node:assert/strict";
import test from "node:test";
import { classifyHttpStatus, duplicateValues, isFreshTimestamp } from "../scripts/health-check.mjs";

test("classifica HTTP sense confondre bloquejos amb enllaços trencats", () => {
  assert.equal(classifyHttpStatus(200), "ok");
  assert.equal(classifyHttpStatus(404), "error");
  assert.equal(classifyHttpStatus(410), "error");
  assert.equal(classifyHttpStatus(500), "error");
  assert.equal(classifyHttpStatus(403), "warning");
  assert.equal(classifyHttpStatus(429), "warning");
  assert.equal(classifyHttpStatus(404, 404), "ok");
});

test("detecta identificadors de Telegram repetits", () => {
  assert.deepEqual(duplicateValues(["a", "b", "a", "c", "b"]), ["a", "b"]);
  assert.deepEqual(duplicateValues(["a", "b"]), []);
});

test("comprova que les dades publicades siguin recents", () => {
  const now = Date.parse("2026-08-25T12:00:00Z");
  assert.equal(isFreshTimestamp("2026-08-25T08:00:00Z", now), true);
  assert.equal(isFreshTimestamp("2026-08-22T08:00:00Z", now), false);
  assert.equal(isFreshTimestamp("data invàlida", now), false);
});


