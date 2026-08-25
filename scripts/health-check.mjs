import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_BASE_URL = "https://pradell360.cat";
const REQUEST_TIMEOUT_MS = 20_000;

export function classifyHttpStatus(status, expected = 200) {
  if (status === expected) return "ok";
  if (status === 404 || status === 410 || status >= 500) return "error";
  return "warning";
}

export function duplicateValues(values) {
  const seen = new Set();
  const duplicates = new Set();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
}

export function isFreshTimestamp(value, now = Date.now(), maximumAgeHours = 48) {
  const timestamp = Date.parse(value ?? "");
  return Number.isFinite(timestamp) && now - timestamp <= maximumAgeHours * 60 * 60 * 1000;
}

function normalizeUrl(value) {
  try {
    const url = new URL(value);
    url.hash = "";
    return url.href;
  } catch {
    return "";
  }
}

async function request(url, expectedStatus = 200) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const startedAt = Date.now();
  try {
    const response = await fetch(url, {
      redirect: "follow",
      signal: controller.signal,
      headers: { "user-agent": "Pradell360-health-check/1.0" },
    });
    const contentType = response.headers.get("content-type") ?? "";
    const body = /json|text|xml|html/i.test(contentType) ? await response.text() : "";
    if (response.body && !body) await response.body.cancel();
    return { url, finalUrl: response.url, status: response.status, state: classifyHttpStatus(response.status, expectedStatus), durationMs: Date.now() - startedAt, contentType, body };
  } catch (error) {
    return { url, status: 0, state: "warning", durationMs: Date.now() - startedAt, error: error instanceof Error ? error.message : String(error), body: "" };
  } finally {
    clearTimeout(timer);
  }
}

async function mapLimit(values, limit, mapper) {
  const results = new Array(values.length);
  let cursor = 0;
  async function worker() {
    while (cursor < values.length) {
      const index = cursor++;
      results[index] = await mapper(values[index], index);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, values.length) }, worker));
  return results;
}

function parseJson(check, label) {
  try {
    return JSON.parse(check.body);
  } catch {
    check.state = "error";
    check.error = `${label} no retorna JSON vàlid.`;
    return {};
  }
}

function markdown(report) {
  const icon = (state) => state === "ok" ? "✅" : state === "warning" ? "⚠️" : "❌";
  const lines = [
    "# Salut setmanal de Pradell360", "", `Data: ${report.generatedAt}`, `Resultat: **${report.summary.result.toUpperCase()}**`, "",
    "## Resum", "", `- ${report.summary.ok} comprovacions correctes`, `- ${report.summary.warnings} ${report.summary.warnings === 1 ? "advertiment" : "advertiments"}`, `- ${report.summary.errors} errors`,
    `- ${report.coverage.successfulSources}/${report.coverage.sourceCount} fonts PRADATA disponibles`, `- ${report.links.checked} enllaços oficials comprovats`, "",
    "## Comprovacions", "", "| Estat | Comprovació | HTTP | Detall |", "|---|---|---:|---|",
    ...report.checks.map((check) => `| ${icon(check.state)} | ${check.name} | ${check.status || "—"} | ${check.error || check.detail || check.finalUrl || "Correcte"} |`),
  ];
  if (report.links.problems.length) {
    lines.push("", "## Enllaços amb incidències", "");
    for (const problem of report.links.problems) lines.push(`- ${icon(problem.state)} ${problem.status || "sense resposta"} · ${problem.url}${problem.error ? ` · ${problem.error}` : ""}`);
  }
  return `${lines.join("\n")}\n`;
}

export async function runHealthCheck({ baseUrl = DEFAULT_BASE_URL, reportDir = "health-report" } = {}) {
  const base = baseUrl.replace(/\/$/, "");
  const routes = [
    ["Portada", `${base}/`, 200], ["Robots", `${base}/robots.txt`, 200], ["Sitemap", `${base}/sitemap.xml`, 200],
    ["API PRADATA", `${base}/api/pradata-verified`, 200], ["Fitxa recent", `${base}/fitxa/impulsdipta-2026-edificis`, 200],
    ["Dossier TV-3223", `${base}/dossier/tv-3223`, 200], ["Pàgina 404", `${base}/fitxa/no-existeix`, 404],
    ["Cobertura de fonts", "https://d9tj6y8zrf-jpg.github.io/pradata/data/status.json", 200],
    ["Estat de Telegram", "https://raw.githubusercontent.com/d9tj6y8zrf-jpg/pradata/main/data/telegram-state.json", 200],
  ];
  const checks = await mapLimit(routes, 4, async ([name, url, expected]) => ({ name, expected, ...await request(url, expected) }));
  const byName = new Map(checks.map((item) => [item.name, item]));
  const statusDocument = parseJson(byName.get("Cobertura de fonts"), "La cobertura de fonts");
  const apiDocument = parseJson(byName.get("API PRADATA"), "L’API PRADATA");
  const telegramDocument = parseJson(byName.get("Estat de Telegram"), "L’estat de Telegram");

  const sourceCount = Number(statusDocument.meta?.source_count ?? 0);
  const successfulSources = Number(statusDocument.meta?.successful_sources ?? 0);
  const sourceProblems = (statusDocument.sources ?? []).filter((source) => source.state !== "ok");
  const coverageCheck = byName.get("Cobertura de fonts");
  coverageCheck.detail = `${successfulSources}/${sourceCount} fonts disponibles`;
  if (sourceCount !== 13 || successfulSources !== 13 || sourceProblems.length) coverageCheck.state = "warning";
  if (!isFreshTimestamp(statusDocument.meta?.updated_at)) {
    coverageCheck.state = "error";
    coverageCheck.error = "Les dades de cobertura tenen més de 48 hores.";
  }

  const apiCheck = byName.get("API PRADATA");
  const verifiedRecords = apiDocument.records ?? [];
  apiCheck.detail = `${apiDocument.meta?.verified_count ?? verifiedRecords.length} publicacions verificades`;
  if (!isFreshTimestamp(apiDocument.meta?.updated_at)) {
    apiCheck.state = "error";
    apiCheck.error = "L’API publicada té més de 48 hores.";
  }

  const telegramCheck = byName.get("Estat de Telegram");
  const sentIds = (telegramDocument.sent ?? []).flatMap((item) => item.record_ids ?? []);
  const duplicateTelegramIds = duplicateValues(sentIds);
  telegramCheck.detail = `${telegramDocument.sent?.length ?? 0} enviaments registrats; ${duplicateTelegramIds.length} duplicats`;
  if (duplicateTelegramIds.length) {
    telegramCheck.state = "error";
    telegramCheck.error = `Telegram conté identificadors repetits: ${duplicateTelegramIds.join(", ")}`;
  } else if (!isFreshTimestamp(telegramDocument.last_checked_at)) {
    telegramCheck.state = "warning";
    telegramCheck.error = "Telegram no s’ha comprovat durant les darreres 48 hores.";
  }

  const sitemapCheck = byName.get("Sitemap");
  const sitemapUrls = [...sitemapCheck.body.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  sitemapCheck.detail = `${sitemapUrls.length} URL al sitemap`;
  if (sitemapUrls.length < 10) {
    sitemapCheck.state = "error";
    sitemapCheck.error = "El sitemap conté massa poques adreces.";
  }

  const links = [...new Set([
    ...(statusDocument.sources ?? []).map((source) => source.url),
    ...verifiedRecords.map((record) => record.url),
    ...sitemapUrls.slice(0, 10),
  ].map(normalizeUrl).filter(Boolean))].slice(0, 40);
  const linkResults = await mapLimit(links, 5, (url) => request(url));
  const linkProblems = linkResults.filter((item) => item.state !== "ok");
  const hardLinkErrors = linkProblems.filter((item) => item.state === "error");
  checks.push({ name: "Mostra d’enllaços oficials", url: "", status: 0, state: hardLinkErrors.length ? "error" : linkProblems.length ? "warning" : "ok", detail: `${links.length} comprovats; ${hardLinkErrors.length} trencats; ${linkProblems.length - hardLinkErrors.length} no concloents` });

  const errors = checks.filter((item) => item.state === "error").length;
  const warnings = checks.filter((item) => item.state === "warning").length;
  const report = {
    generatedAt: new Date().toISOString(), baseUrl: base,
    summary: { result: errors ? "error" : warnings ? "incomplet" : "correcte", ok: checks.length - errors - warnings, warnings, errors },
    coverage: { sourceCount, successfulSources, problems: sourceProblems },
    telegram: { duplicateRecordIds: duplicateTelegramIds, lastCheckedAt: telegramDocument.last_checked_at ?? null },
    links: { checked: links.length, problems: linkProblems },
    checks: checks.map((item) =>
      Object.fromEntries(Object.entries(item).filter(([key]) => key !== "body")),
    ),
  };
  const output = resolve(reportDir);
  await mkdir(output, { recursive: true });
  await Promise.all([
    writeFile(resolve(output, "health-report.json"), `${JSON.stringify(report, null, 2)}\n`),
    writeFile(resolve(output, "health-report.md"), markdown(report)),
  ]);
  process.stdout.write(markdown(report));
  if (errors) process.exitCode = 1;
  return report;
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) await runHealthCheck({ baseUrl: process.env.PRADELL360_BASE_URL || DEFAULT_BASE_URL, reportDir: process.env.PRADELL360_REPORT_DIR || "health-report" });
