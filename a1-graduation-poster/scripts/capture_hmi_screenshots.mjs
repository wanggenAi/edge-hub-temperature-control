#!/usr/bin/env node
/**
 * HMI screenshot workflow for poster assets.
 *
 * The script prepares demo data, starts the local HMI stack when needed, picks a
 * real device with metrics, then captures focused viewport screenshots. If a
 * live capture cannot run, it writes clear placeholders with TODO labels.
 */

import fs from "node:fs/promises";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const POSTER_ROOT = path.resolve(__dirname, "..");
const REPO_ROOT = path.resolve(POSTER_ROOT, "..");
const ASSET_DIR = path.join(POSTER_ROOT, "assets");
const BACKEND_DIR = path.join(REPO_ROOT, "hmi", "backend");
const FRONTEND_DIR = path.join(REPO_ROOT, "hmi", "frontend");

const BACKEND_PORT = Number(process.env.HMI_POSTER_BACKEND_PORT ?? 18080);
const FRONTEND_PORT = Number(process.env.HMI_POSTER_FRONTEND_PORT ?? 15173);
const BACKEND_URL = process.env.HMI_API_BASE_URL ?? `http://127.0.0.1:${BACKEND_PORT}`;
const FRONTEND_URL = process.env.HMI_BASE_URL ?? `http://127.0.0.1:${FRONTEND_PORT}`;
const VIEWPORT = { width: 1600, height: 980 };
const DEVICE_CODE_PRIORITY = ["TC-PREVIEW-OSC-OVS", "TC-PREVIEW-SAT-SLOW", "TC-PREVIEW-SLOW-01"];

const TARGETS = [
  { file: "hmi-device-detail.png", label: "Device Detail" },
  { file: "hmi-ai-validation.png", label: "AI Validation" },
  { file: "hmi-ops-console.png", label: "Ops Console" },
];

const CHROME_CANDIDATES = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
  "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
];

const BACKEND_ENV = {
  ...process.env,
  DATA_SOURCE_MODE: "postgresql",
  TDENGINE_ENABLED: "false",
  MQTT_PUBLISH_ENABLED: "false",
  OPS_ENABLE_EXTERNAL_METRICS: "false",
  AI_RUNTIME_ENABLED: "false",
  AI_RUNTIME_FAIL_OPEN: "true",
  CORS_ORIGINS: `["http://127.0.0.1:${FRONTEND_PORT}","http://localhost:${FRONTEND_PORT}"]`,
  HMI_LOG_LEVEL: "WARNING",
  HMI_CONSOLE_LOG_LEVEL: "WARNING",
  HMI_ACCESS_LOG_LEVEL: "WARNING",
};

const FRONTEND_ENV = {
  ...process.env,
  VITE_API_BASE_URL: BACKEND_URL,
  VITE_WS_BASE_URL: BACKEND_URL.replace(/^http:/, "ws:").replace(/^https:/, "wss:"),
};

const managedProcesses = [];

async function ensureDir(dir) {
  await fs.mkdir(dir, { recursive: true });
}

function runCommand(cmd, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, {
      cwd: options.cwd ?? REPO_ROOT,
      env: options.env ?? process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let out = "";
    let err = "";
    child.stdout.on("data", (chunk) => {
      out += chunk.toString();
    });
    child.stderr.on("data", (chunk) => {
      err += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve({ out, err });
      else reject(new Error(`${cmd} ${args.join(" ")} failed with ${code}\n${out}\n${err}`));
    });
  });
}

async function fetchOk(url, opts = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), opts.timeoutMs ?? 1500);
  try {
    const res = await fetch(url, { signal: controller.signal, headers: opts.headers });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function waitForHttp(url, timeoutMs = 45000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await fetchOk(url, { timeoutMs: 1800 })) return true;
    await new Promise((resolve) => setTimeout(resolve, 900));
  }
  return false;
}

function startProcess(cmd, args, options) {
  const child = spawn(cmd, args, {
    cwd: options.cwd,
    env: options.env ?? process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  managedProcesses.push(child);
  child.stdout.on("data", (chunk) => process.stdout.write(`[${options.name}] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[${options.name}] ${chunk}`));
  return child;
}

async function ensureBackend() {
  startProcess(
    path.join(BACKEND_DIR, ".venv", "bin", "python"),
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    { cwd: BACKEND_DIR, env: BACKEND_ENV, name: "hmi-backend" }
  );
  const ok = await waitForHttp(`${BACKEND_URL}/health`, 60000);
  if (!ok) throw new Error(`HMI backend did not become ready on 127.0.0.1:${BACKEND_PORT}.`);
  return true;
}

async function ensureFrontend() {
  startProcess("npm", ["run", "dev", "--", "--host", "127.0.0.1", "--port", String(FRONTEND_PORT)], {
    cwd: FRONTEND_DIR,
    env: FRONTEND_ENV,
    name: "hmi-frontend",
  });
  const ok = await waitForHttp(FRONTEND_URL, 60000);
  if (!ok) throw new Error(`HMI frontend did not become ready on 127.0.0.1:${FRONTEND_PORT}.`);
  return true;
}

async function prepareData() {
  await runCommand("python3", [path.join(POSTER_ROOT, "scripts", "ensure_datahub_log.py"), "--force"], { cwd: REPO_ROOT });
  await runCommand(
    path.join(BACKEND_DIR, ".venv", "bin", "python"),
    ["scripts/db_migrate.py"],
    { cwd: BACKEND_DIR, env: BACKEND_ENV }
  );
  await runCommand("python3", [path.join(POSTER_ROOT, "scripts", "prepare_hmi_demo_data.py")], {
    cwd: REPO_ROOT,
    env: BACKEND_ENV,
  });
}

async function writePlaceholder(name, label, reason) {
  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="980" viewBox="0 0 1600 980">
  <rect width="1600" height="980" rx="28" fill="#06131f"/>
  <rect x="64" y="64" width="1472" height="852" rx="26" fill="#0d1f31" stroke="#42d9ff" stroke-width="3"/>
  <text x="120" y="150" font-family="Inter, Arial, sans-serif" font-size="42" font-weight="700" fill="#effcff">${label}</text>
  <text x="120" y="210" font-family="Inter, Arial, sans-serif" font-size="23" fill="#bcd2e2">TODO: replace with a live HMI screenshot.</text>
  <text x="120" y="256" font-family="Inter, Arial, sans-serif" font-size="18" fill="#9dc8dd">${escapeXml(reason)}</text>
  <rect x="120" y="330" width="420" height="220" rx="18" fill="#102a3f" stroke="#5ef2ff" stroke-width="2"/>
  <rect x="590" y="330" width="420" height="220" rx="18" fill="#102a3f" stroke="#70f0bf" stroke-width="2"/>
  <rect x="1060" y="330" width="360" height="220" rx="18" fill="#102a3f" stroke="#ffc766" stroke-width="2"/>
  <text x="330" y="450" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="26" font-weight="700" fill="#effcff">Cards</text>
  <text x="800" y="450" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="26" font-weight="700" fill="#effcff">Charts</text>
  <text x="1240" y="450" text-anchor="middle" font-family="Inter, Arial, sans-serif" font-size="26" font-weight="700" fill="#effcff">Controls</text>
</svg>`;
  await fs.writeFile(path.join(ASSET_DIR, name.replace(/\.png$/, ".svg")), svg, "utf-8");
}

function escapeXml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function loginAndGetToken(page) {
  await page.goto(`${FRONTEND_URL}/login`, { waitUntil: "domcontentloaded" });
  await page.locator('input[placeholder="admin"]').fill("admin");
  await page.locator('input[type="password"]').fill("admin123");
  await page.getByRole("button", { name: "Login" }).click();
  await page.waitForURL((url) => !url.pathname.includes("/login"), { timeout: 30000 });
  return page.evaluate(() => localStorage.getItem("token"));
}

async function apiGet(pathname, token) {
  const res = await fetch(`${BACKEND_URL}${pathname}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`GET ${pathname} -> HTTP ${res.status}`);
  return res.json();
}

async function pickDeviceWithMetrics(token) {
  const devices = await apiGet("/devices", token);
  const ranked = [...devices].sort((a, b) => {
    const ai = DEVICE_CODE_PRIORITY.indexOf(a.code);
    const bi = DEVICE_CODE_PRIORITY.indexOf(b.code);
    return (ai < 0 ? 999 : ai) - (bi < 0 ? 999 : bi);
  });
  for (const device of ranked) {
    const metrics = await apiGet(`/devices/${device.id}/metrics?limit=1000`, token).catch(() => []);
    const params = await apiGet(`/devices/${device.id}/parameters`, token).catch(() => null);
    if (params && Array.isArray(metrics) && metrics.length >= 10) {
      return { device, metricCount: metrics.length };
    }
  }
  throw new Error("No accessible HMI device with metrics was found after demo seed.");
}

async function ensureRecommendationReady(token, deviceId) {
  const history = await apiGet(`/devices/ai/recommendations/history?device_id=${deviceId}&limit=10`, token);
  const applied = Array.isArray(history.items)
    ? history.items.find((item) => item.history_state === "applied") ?? history.items[0]
    : null;
  if (!applied) throw new Error(`No AI recommendation history was found for device ${deviceId}.`);

  const comparison = await apiGet(
    `/devices/${deviceId}/ai-recommendation/${applied.recommendation_id}/telemetry-comparison?observation_window_minutes=60&baseline_window_minutes=60&max_points=360`,
    token
  );
  const baselineCount = Array.isArray(comparison.baseline_curve) ? comparison.baseline_curve.length : 0;
  const previewCount = Array.isArray(comparison.preview_curve) ? comparison.preview_curve.length : 0;
  const actualCount = Array.isArray(comparison.actual_curve) ? comparison.actual_curve.length : 0;
  if (baselineCount < 3 || previewCount < 3 || actualCount < 3) {
    throw new Error(
      `AI telemetry comparison is incomplete (baseline=${baselineCount}, preview=${previewCount}, actual=${actualCount}).`
    );
  }
  return { recommendationId: applied.recommendation_id, appliedAt: applied.applied_at, baselineCount, previewCount, actualCount };
}

function parseNaiveLocalDate(value) {
  const date = value instanceof Date ? value : new Date(String(value).replace(" ", "T"));
  if (Number.isNaN(date.getTime())) throw new Error(`Invalid datetime value: ${value}`);
  return date;
}

function toDatetimeLocalInput(value) {
  const date = parseNaiveLocalDate(value);
  const pad = (num) => String(num).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  );
}

async function fillDatetimeLocal(locator, value) {
  await locator.evaluate(
    (node, nextValue) => {
      node.value = nextValue;
      node.dispatchEvent(new Event("input", { bubbles: true }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    },
    value
  );
}

async function setAiWindowToAppliedRange(page, appliedAt) {
  const applied = parseNaiveLocalDate(appliedAt);
  const end = new Date(applied.getTime() + 60 * 60 * 1000);
  await page.locator('[role="combobox"]').click();
  await page.getByText("Custom Range", { exact: true }).click();
  const inputs = page.locator('input[type="datetime-local"]');
  await fillDatetimeLocal(inputs.nth(0), toDatetimeLocalInput(applied));
  await fillDatetimeLocal(inputs.nth(1), toDatetimeLocalInput(end));
  await page.getByRole("button", { name: "Refresh" }).click().catch(() => null);
  await page.waitForTimeout(2200);
}

async function removePlaceholderSvgs() {
  await Promise.all(
    TARGETS.map((target) => fs.unlink(path.join(ASSET_DIR, target.file.replace(/\.png$/, ".svg"))).catch(() => null))
  );
}

async function scrollTo(page, top) {
  await page.evaluate((value) => window.scrollTo(0, value), top);
  await page.waitForTimeout(650);
}

async function captureMainViewport(page, filename, options = {}) {
  const main = page.locator("main").first();
  const box = await main.boundingBox();
  const viewport = page.viewportSize();
  if (!box || !viewport) throw new Error(`Cannot calculate HMI main area for ${filename}.`);

  const stickyHeaderClearance = options.headerClearance ?? 84;
  const sidePadding = options.sidePadding ?? 0;
  const bottomPadding = options.bottomPadding ?? 24;
  const x = Math.max(0, Math.floor(box.x + sidePadding));
  const y = Math.max(0, Math.floor(Math.max(box.y, stickyHeaderClearance)));
  const maxWidth = viewport.width - x - sidePadding;
  const maxHeight = viewport.height - y - bottomPadding;
  const width = Math.max(320, Math.floor(Math.min(box.width - sidePadding * 2, maxWidth)));
  const height = Math.max(320, Math.floor(Math.min(options.height ?? maxHeight, maxHeight)));

  await page.screenshot({
    path: path.join(ASSET_DIR, filename),
    fullPage: false,
    clip: { x, y, width, height },
  });
}

async function captureWithPlaywright() {
  let playwright;
  try {
    playwright = await import("playwright");
  } catch (error) {
    return { ok: false, reason: `Playwright unavailable: ${error.message}` };
  }

  let executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  if (!executablePath) {
    for (const candidate of CHROME_CANDIDATES) {
      try {
        await fs.access(candidate);
        executablePath = candidate;
        break;
      } catch {
        // Try next candidate.
      }
    }
  }

  const browser = await playwright.chromium.launch({
    headless: true,
    ...(executablePath ? { executablePath } : {}),
  });
  try {
    const context = await browser.newContext({
      viewport: VIEWPORT,
      deviceScaleFactor: 2,
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    const token = await loginAndGetToken(page);
    if (!token) throw new Error("Login succeeded but no auth token was found.");

    const { device, metricCount } = await pickDeviceWithMetrics(token);
    const readiness = await ensureRecommendationReady(token, device.id);
    console.log(
      `Using HMI screenshot device ${device.code} (id=${device.id}, metrics=${metricCount}, ` +
        `recommendation=${readiness.recommendationId}, applied=${readiness.appliedAt}, baseline=${readiness.baselineCount}, ` +
        `preview=${readiness.previewCount}, actual=${readiness.actualCount}).`
    );

    await page.goto(`${FRONTEND_URL}/devices/${device.id}`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await page.getByText("Control Performance Trend (Live)").waitFor({ state: "visible", timeout: 20000 });
    await page.getByRole("button", { name: "Generate Recommendation" }).click();
    await page.waitForTimeout(1200);
    await page.getByRole("button", { name: "Preview Impact" }).click().catch(() => null);
    await page.waitForTimeout(1800);
    await scrollTo(page, 0);
    await captureMainViewport(page, "hmi-device-detail.png");

    await page.goto(`${FRONTEND_URL}/ai`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await page.getByText("AI Post-Apply Validation").waitFor({ state: "visible", timeout: 20000 });
    await setAiWindowToAppliedRange(page, readiness.appliedAt).catch((error) =>
      console.warn(`AI window selection skipped: ${error.message}`)
    );
    await page.getByText("Full Comparison").waitFor({ state: "visible", timeout: 20000 }).catch(() => null);
    await page.getByText("Actual Effect Summary").waitFor({ state: "visible", timeout: 20000 }).catch(() => null);
    await page
      .getByText("Telemetry Comparison")
      .first()
      .evaluate((node) => node.scrollIntoView({ block: "start", inline: "nearest" }))
      .catch(() => null);
    await page.evaluate(() => window.scrollBy(0, -112)).catch(() => null);
    await page.waitForTimeout(700);
    await captureMainViewport(page, "hmi-ai-validation.png", { height: 820 });

    await page.goto(`${FRONTEND_URL}/ops?tab=platform`, { waitUntil: "domcontentloaded" });
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await page.getByText("Data Hub / MQTT / Ingestion").waitFor({ state: "visible", timeout: 20000 });
    await scrollTo(page, 0);
    await captureMainViewport(page, "hmi-ops-console.png");

    await context.close();
    await removePlaceholderSvgs();
    return { ok: true, deviceCode: device.code };
  } catch (error) {
    return { ok: false, reason: `Capture failed: ${error.message}` };
  } finally {
    await browser.close();
  }
}

async function cleanupManagedProcesses() {
  for (const child of managedProcesses.reverse()) {
    if (!child.killed) child.kill("SIGTERM");
  }
  await new Promise((resolve) => setTimeout(resolve, 800));
}

async function main() {
  await ensureDir(ASSET_DIR);
  try {
    await prepareData();
    await ensureBackend();
    await ensureFrontend();
    const result = await captureWithPlaywright();
    if (result.ok) {
      console.log(`HMI screenshots captured from ${result.deviceCode}.`);
      return;
    }
    console.warn(result.reason);
    for (const target of TARGETS) {
      await writePlaceholder(target.file, target.label, result.reason);
    }
    console.warn("Placeholder HMI assets written; real screenshot capture still needs attention.");
  } finally {
    await cleanupManagedProcesses();
  }
}

main().catch(async (error) => {
  console.error(error);
  for (const target of TARGETS) {
    await writePlaceholder(target.file, target.label, error.message).catch(() => null);
  }
  await cleanupManagedProcesses();
  process.exitCode = 1;
});
