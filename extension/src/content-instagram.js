// Content script for instagram.com.
//
// Instagram has no text-only post — every feed post needs an image or video.
// So this script CANNOT autopost end-to-end. Instead it:
//   1. Copies the caption to the user's clipboard.
//   2. Opens the Create dialog, prompting the user to drop in media.
//   3. Reports back as "needs_user_action" so the dashboard reflects reality.

(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function copyToClipboard(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Fallback: hidden textarea + execCommand.
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    }
  }

  function openCreateDialog() {
    // Instagram's nav has a "Create" button.
    const candidates = Array.from(document.querySelectorAll('a[role="link"], div[role="button"]'));
    const createBtn = candidates.find((el) => {
      const label = (el.getAttribute("aria-label") || el.textContent || "").trim().toLowerCase();
      return label === "create" || label === "new post";
    });
    if (createBtn) createBtn.click();
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        const copied = await copyToClipboard(msg.content);
        openCreateDialog();
        await sleep(1500);
        sendResponse({
          ok: false,
          error: copied
            ? "needs_user_action: caption copied to clipboard, attach media to publish"
            : "instagram requires media; couldn't copy caption either",
        });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
