const apiInput = document.getElementById("apiUrl");
const jwtInput = document.getElementById("jwt");
const enabledInput = document.getElementById("enabled");
const outcomesEnabledInput = document.getElementById("outcomesEnabled");
const outcomesIntervalInput = document.getElementById("outcomesInterval");
const status = document.getElementById("status");

async function load() {
  const {
    apiUrl,
    enabled,
    jwt,
    outcomesEnabled,
    outcomesIntervalMinutes,
  } = await chrome.storage.local.get([
    "apiUrl",
    "enabled",
    "jwt",
    "outcomesEnabled",
    "outcomesIntervalMinutes",
  ]);
  apiInput.value = apiUrl || "http://localhost:8000";
  jwtInput.value = jwt || "";
  enabledInput.checked = enabled !== false;
  outcomesEnabledInput.checked = outcomesEnabled === true;
  outcomesIntervalInput.value = Number(outcomesIntervalMinutes) > 0 ? outcomesIntervalMinutes : 60;
}

document.getElementById("save").addEventListener("click", async () => {
  // Clamp interval — Chrome alarms can't fire faster than every minute,
  // and the engagement metrics we're scraping barely move in under five.
  const raw = parseInt(outcomesIntervalInput.value, 10);
  const interval = Number.isFinite(raw) && raw >= 5 ? raw : 60;
  await chrome.storage.local.set({
    apiUrl: apiInput.value.trim(),
    jwt: jwtInput.value.trim(),
    enabled: enabledInput.checked,
    outcomesEnabled: outcomesEnabledInput.checked,
    outcomesIntervalMinutes: interval,
  });
  // Re-arm the outcomes alarm so the new interval takes effect immediately
  // instead of waiting for the next browser restart.
  await chrome.runtime.sendMessage({ type: "fanout:reschedule-outcomes" });
  status.textContent = "Saved.";
});

document.getElementById("pollNow").addEventListener("click", async () => {
  status.textContent = "Polling queue...";
  await chrome.runtime.sendMessage({ type: "fanout:poll-now" });
  status.textContent = "Done.";
});

document.getElementById("outcomesNow").addEventListener("click", async () => {
  status.textContent = "Pulling outcomes...";
  const out = await chrome.runtime.sendMessage({ type: "fanout:outcomes-now" });
  if (!out?.ran) {
    status.textContent = `Skipped: ${out?.reason ?? "unknown"}`;
    return;
  }
  const processed = Array.isArray(out.processed) ? out.processed : [];
  const reported = processed.filter((p) => p.reported && Object.keys(p.reported).length > 0);
  status.textContent = `Scraped ${processed.length} of ${out.total_posted} posted; ${reported.length} produced metrics.`;
});

load();
