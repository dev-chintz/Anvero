// Takes the guide's screenshots (docs/GUIDE.md): drives an installed Chrome through the DevTools
// protocol (nothing to install), logs in with the scratch token, and writes one .webp per screen into
// frontend/public/guide. Run through tools/guide/make.ps1, which starts the sample backend and the
// interface first.
//
//   node tools/guide/capture.mjs [--base http://localhost:5173] [--only dashboard,orders]

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..", "..");
const work = process.env.GUIDE_WORK ? resolve(process.env.GUIDE_WORK) : join(here, ".work");
const outDir = join(root, "frontend", "public", "guide");

const args = process.argv.slice(2);
const option = (name, fallback) => {
  const at = args.indexOf(`--${name}`);
  return at >= 0 ? args[at + 1] : fallback;
};
const base = option("base", "http://localhost:5173");
const only = option("only", "")
  .split(",")
  .filter(Boolean);
const port = Number(option("port", "9333"));

const CHROME = [
  process.env.CHROME_PATH,
  "C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
  "/usr/bin/google-chrome",
  "/usr/bin/chromium",
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
].find((candidate) => candidate && existsSync(candidate));
if (!CHROME) throw new Error("No Chrome or Edge found; set CHROME_PATH");

const token = readFileSync(join(work, "token.txt"), "utf8").trim();

const WIDTH = 1440;
const HEIGHT = 900;

// each screen: its name (the file), the address, how tall the window is, what to do before the picture
// (a script run in the page), and a part of the page to cut out
const click = (selector, index = 0) =>
  `(() => { const el = document.querySelectorAll(${JSON.stringify(selector)})[${index}]; if (el) el.click(); })()`;

const SHOTS = [
  { name: "menu", path: "/dashboard", clip: { x: 0, y: 0, width: 700, height: 640 } },
  { name: "dashboard", path: "/dashboard" },
  { name: "orders", path: "/orders", height: 1000 },
  { name: "order", path: "ORDER", height: 1500 },
  { name: "production", path: "/production" },
  { name: "catalog", path: "/catalog", height: 1150, before: click(".catalog-toggle button", 3) },
  { name: "labels", path: "/labels" },
  { name: "after-sales", path: "/after-sales" },
  { name: "inbox", path: "/inbox" },
  { name: "finance", path: "/finance", height: 1000 },
  { name: "sales-report", path: "/sales-report", height: 1000 },
  { name: "settings", path: "/settings", height: 1250 },
  { name: "integrations", path: "/settings?tab=integrations&integration=allegro", height: 1000 },
  { name: "users", path: "/settings?tab=users", height: 1000 },
  { name: "updates", path: "/settings?tab=updates" },
  { name: "status", path: "/settings?tab=status", height: 1000 },
  { name: "help", path: "/help?tab=gdpr", height: 1000 },
];

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));

async function waitForChrome() {
  for (let attempt = 0; attempt < 100; attempt += 1) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/json/version`);
      if (response.ok) return;
    } catch {
      // not up yet
    }
    await sleep(100);
  }
  throw new Error("Chrome did not open its debugging port");
}

class Page {
  constructor(socket) {
    this.socket = socket;
    this.nextId = 1;
    this.waiting = new Map();
    this.loaded = null;
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.waiting.has(message.id)) {
        const { resolve: done, reject } = this.waiting.get(message.id);
        this.waiting.delete(message.id);
        if (message.error) reject(new Error(`${message.error.message}`));
        else done(message.result);
      } else if (message.method === "Page.loadEventFired" && this.loaded) {
        this.loaded();
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    return new Promise((done, reject) => {
      this.waiting.set(id, { resolve: done, reject });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }

  async goto(url) {
    const loaded = new Promise((done) => {
      this.loaded = done;
    });
    await this.send("Page.navigate", { url });
    await Promise.race([loaded, sleep(15000)]);
  }
}

async function main() {
  mkdirSync(outDir, { recursive: true });
  const profile = mkdtempSync(join(tmpdir(), "anvero-guide-"));
  const chrome = spawn(
    CHROME,
    [
      "--headless=new",
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${profile}`,
      "--hide-scrollbars",
      "--no-first-run",
      "--no-default-browser-check",
      "--disable-gpu",
      `--window-size=${WIDTH},${HEIGHT}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  try {
    await waitForChrome();
    const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
    const target = targets.find((entry) => entry.type === "page");
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((done, reject) => {
      socket.addEventListener("open", done);
      socket.addEventListener("error", reject);
    });
    const page = new Page(socket);
    await page.send("Page.enable");
    await page.send("Runtime.enable");

    // logged in, in Polish, in the classic look and light mode: what the guide shows
    await page.goto(`${base}/login`);
    await page.evaluate(
      `localStorage.setItem("anvero.accessToken", ${JSON.stringify(token)});
       localStorage.setItem("language", "pl");
       localStorage.setItem("theme-look", "classic");
       localStorage.setItem("theme-mode", "light");
       localStorage.setItem("sidebar-open", "true");`,
    );

    // an order with several items, a parcel and notes, for the order page's picture
    const orders = await (
      await fetch(`${base}/api/v1/orders?limit=100`, { headers: { Authorization: `Bearer ${token}` } })
    ).json();
    const list = orders.items ?? orders;
    let chosen = list[0];
    for (const candidate of list.filter((order) => order.source === "ALLEGRO" && ["SHIPPED", "DELIVERED"].includes(order.status))) {
      const detail = await (
        await fetch(`${base}/api/v1/orders/${candidate.id}`, { headers: { Authorization: `Bearer ${token}` } })
      ).json();
      if ((detail.items?.length ?? 0) >= 2 && (detail.shipments?.length ?? 0) > 0) {
        chosen = candidate;
        break;
      }
    }

    let taken = 0;
    for (const shot of SHOTS) {
      if (only.length && !only.includes(shot.name)) continue;
      const path = shot.path === "ORDER" ? `/orders/${chosen.id}` : shot.path;
      await page.send("Emulation.setDeviceMetricsOverride", {
        width: WIDTH,
        height: shot.height ?? HEIGHT,
        deviceScaleFactor: 1,
        mobile: false,
      });
      await page.goto(`${base}${path}`);
      await sleep(1800);
      if (shot.before) {
        await page.evaluate(shot.before);
        await sleep(500);
      }
      const picture = await page.send("Page.captureScreenshot", {
        format: "webp",
        quality: 82,
        ...(shot.clip ? { clip: { ...shot.clip, scale: 1 } } : {}),
      });
      const file = join(outDir, `${shot.name}.webp`);
      writeFileSync(file, Buffer.from(picture.data, "base64"));
      taken += 1;
      console.log(`${shot.name}.webp`);
    }
    // the profile held the token; nothing of it is kept
    socket.close();
    console.log(`${taken} screenshots in ${outDir}`);
  } finally {
    chrome.kill();
    await sleep(300);
    try {
      rmSync(profile, { recursive: true, force: true });
    } catch {
      // Chrome may still hold a file for a moment; the temporary folder is harmless
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
