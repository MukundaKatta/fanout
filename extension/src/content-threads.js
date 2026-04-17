// Content script for threads.net — opens composer, pastes content, posts.

(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  async function waitFor(predicate, { timeout = 10000, interval = 100, label = "" } = {}) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const result = predicate();
      if (result) return result;
      await sleep(interval);
    }
    throw new Error(`timeout: ${label}`);
  }

  async function openComposer() {
    // The "Start a thread" button on the home/feed page.
    const trigger =
      document.querySelector('div[role="button"][tabindex="0"][aria-label*="thread" i]') ||
      Array.from(document.querySelectorAll('div[role="button"]')).find((el) =>
        /start a thread/i.test(el.textContent || "")
      );
    if (trigger) trigger.click();

    return await waitFor(
      () => document.querySelector('div[contenteditable="true"][role="textbox"]'),
      { timeout: 8000, label: "threads composer" }
    );
  }

  async function paste(el, text) {
    el.focus();
    const dt = new DataTransfer();
    dt.setData("text/plain", text);
    el.dispatchEvent(
      new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })
    );
    await sleep(150);
  }

  async function postNow() {
    const btn = await waitFor(
      () =>
        Array.from(document.querySelectorAll('div[role="button"]')).find(
          (el) => /^post$/i.test((el.textContent || "").trim()) && el.getAttribute("aria-disabled") !== "true"
        ),
      { timeout: 6000, label: "Post button enabled" }
    );
    btn.click();
    await sleep(2500);
  }

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        const editor = await openComposer();
        await paste(editor, msg.content);
        await postNow();
        sendResponse({ ok: true, postUrl: null });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
