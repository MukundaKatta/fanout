const apiInput = document.getElementById("apiUrl");
const jwtInput = document.getElementById("jwt");
const enabledInput = document.getElementById("enabled");
const status = document.getElementById("status");

async function load() {
  const { apiUrl, enabled, jwt } = await chrome.storage.local.get([
    "apiUrl",
    "enabled",
    "jwt",
  ]);
  apiInput.value = apiUrl || "http://localhost:8000";
  jwtInput.value = jwt || "";
  enabledInput.checked = enabled !== false;
}

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiUrl: apiInput.value.trim(),
    jwt: jwtInput.value.trim(),
    enabled: enabledInput.checked,
  });
  status.textContent = "Saved.";
});

document.getElementById("pollNow").addEventListener("click", async () => {
  status.textContent = "Polling...";
  await chrome.runtime.sendMessage({ type: "fanout:poll-now" });
  status.textContent = "Done.";
});

load();
