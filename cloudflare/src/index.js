// Cloudflare Worker: check PlayStation Direct NL for PS5 Pro stock and push an ntfy alert.
// A cron trigger runs every minute; each run checks CHECKS_PER_RUN times, spread across the minute.

const PRODUCT_CODE = "1000050720-BX"; // PS5 Pro Console - 2TB (NL)
const STORE_URL = "https://direct.playstation.com/nl-nl/buy-consoles/playstation5-pro-console-2-tb";
const API_URL =
  "https://api.direct.playstation.com/commercewebservices/ps-direct-nl/users/anonymous/" +
  `products/productList?fields=BASIC&lang=nl_NL&productCodes=${PRODUCT_CODE}`;
const HEADERS = {
  "User-Agent":
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/129.0 Safari/537.36",
  Accept: "application/json",
  "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
  Origin: "https://direct.playstation.com",
  Referer: STORE_URL,
};
const CHECKS_PER_RUN = 2; // every ~30s
const CHECK_SPACING_MS = 30_000;
// Re-send the in-stock alert at this interval while stock remains available.
const REMIND_EVERY_MS = 15 * 60 * 1000;
// Send one "checker is failing" alert after this many consecutive failed checks (~5 min).
const ERROR_ALERT_THRESHOLD = 10;
const STATE_KEY = "state";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function nlTime() {
  return new Date().toLocaleString("nl-NL", { timeZone: "Europe/Amsterdam", timeZoneName: "short" });
}

async function fetchStock() {
  const resp = await fetch(API_URL, { headers: HEADERS, cf: { cacheTtl: 0 } });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const product = (await resp.json()).products[0];
  const status = product.stock?.stockLevelStatus ?? "unknown";
  const price = product.price?.value;
  const inStock =
    (product.purchasable && (status === "inStock" || status === "lowStock")) ||
    (product.maxOrderQuantity ?? 0) > 0;
  return { inStock, status, price };
}

async function sendNtfy(env, title, body, urgent) {
  const server = env.NTFY_SERVER || "https://ntfy.sh";
  const resp = await fetch(`${server.replace(/\/$/, "")}/${env.NTFY_TOPIC}`, {
    method: "POST",
    body,
    headers: {
      Title: title,
      Priority: urgent ? "urgent" : "default",
      Tags: urgent ? "rotating_light" : "warning",
      Click: STORE_URL,
    },
  });
  if (!resp.ok) throw new Error(`ntfy HTTP ${resp.status}`);
  console.log(`ntfy push sent: ${title}`);
}

async function loadState(env) {
  return (
    (await env.STATE.get(STATE_KEY, "json")) ?? {
      inStock: false,
      lastAlert: 0,
      failures: 0,
      errorAlerted: false,
    }
  );
}

async function checkOnce(env, state) {
  let result;
  try {
    result = await fetchStock();
  } catch (err) {
    // Capped so a long outage doesn't rewrite KV state every minute.
    state.failures = Math.min(state.failures + 1, ERROR_ALERT_THRESHOLD);
    console.log(`Check failed (${state.failures}+ in a row): ${err}`);
    if (state.failures >= ERROR_ALERT_THRESHOLD && !state.errorAlerted) {
      try {
        await sendNtfy(
          env,
          "PS5 Pro stock checker (Cloudflare) is failing",
          `The last ${state.failures} checks failed.\nLatest error: ${err}\n\nCheck the store manually: ${STORE_URL}`,
          false,
        );
        state.errorAlerted = true;
      } catch (notifyErr) {
        console.log(`Could not send error alert: ${notifyErr}`);
      }
    }
    return;
  }

  const { inStock, status, price } = result;
  state.failures = 0;
  state.errorAlerted = false;
  console.log(`Status: ${status} | in stock: ${inStock} | price: €${price}`);

  const now = Date.now();
  if (inStock && (!state.inStock || now - state.lastAlert >= REMIND_EVERY_MS)) {
    try {
      await sendNtfy(
        env,
        "PS5 Pro IN STOCK at PlayStation Direct NL!",
        `The PS5 Pro (2TB) is available now (status: ${status}, price: €${price}).\n\n` +
          `Buy it here: ${STORE_URL}\n\nChecked at ${nlTime()}.`,
        true,
      );
      state.lastAlert = now;
    } catch (err) {
      console.log(`Could not send stock alert: ${err}`);
      return; // leave inStock false so the next check retries
    }
  }
  state.inStock = inStock;
}

export default {
  async scheduled(controller, env, ctx) {
    const state = await loadState(env);
    const before = JSON.stringify(state);
    for (let i = 0; i < CHECKS_PER_RUN; i++) {
      if (i > 0) await sleep(CHECK_SPACING_MS);
      await checkOnce(env, state);
    }
    // KV's free tier allows 1,000 writes/day, so only write when something changed.
    if (JSON.stringify(state) !== before) await env.STATE.put(STATE_KEY, JSON.stringify(state));
  },
};
