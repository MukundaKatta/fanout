// Content script for reddit.com.
//
// Reddit posting requires a target subreddit. The extension navigates to the submit page
// and pre-fills title + body. The user MUST manually pick subreddit and click Submit
// (Reddit aggressively detects automated submissions and bans accounts).

(function () {
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  function splitTitleBody(text) {
    const lines = text.split("\n");
    const title = lines[0].replace(/^TITLE:\s*/i, "").trim();
    const body = lines.slice(1).join("\n").trim();
    return { title, body };
  }

  async function waitFor(predicate, { timeout = 8000 } = {}) {
    const start = Date.now();
    while (Date.now() - start < timeout) {
      const r = predicate();
      if (r) return r;
      await sleep(100);
    }
    return null;
  }

  async function fillSubmitForm(title, body) {
    // Modern Reddit (sh.reddit.com / new.reddit.com) uses shadow DOM and varies a lot.
    // Best-effort: paste title + body, surface to user, do NOT auto-submit.
    const titleInput = await waitFor(
      () =>
        document.querySelector('textarea[placeholder*="Title" i]') ||
        document.querySelector('input[name="title"]') ||
        document.querySelector('faceplate-textarea-input[name="title"]')
    );
    if (titleInput) {
      titleInput.focus();
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      )?.set;
      if (setter && titleInput.tagName === "TEXTAREA") {
        setter.call(titleInput, title);
        titleInput.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        document.execCommand("insertText", false, title);
      }
    }

    const bodyEditor = await waitFor(
      () =>
        document.querySelector('div[contenteditable="true"][data-text-element-key]') ||
        document.querySelector('div[contenteditable="true"]') ||
        document.querySelector('textarea[name="text"]')
    );
    if (bodyEditor) {
      bodyEditor.focus();
      if (bodyEditor.tagName === "TEXTAREA") {
        bodyEditor.value = body;
        bodyEditor.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        const dt = new DataTransfer();
        dt.setData("text/plain", body);
        bodyEditor.dispatchEvent(
          new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true })
        );
      }
    }
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (msg?.type !== "fanout:post") return;
    (async () => {
      try {
        const { title, body } = splitTitleBody(msg.content);

        // If we're not already on a submit page, navigate.
        if (!/\/submit/.test(location.pathname)) {
          // Send back a redirect hint — the background worker will navigate the tab.
          sendResponse({
            ok: false,
            error: "needs_user_action: navigate to https://www.reddit.com/submit and try again",
          });
          return;
        }

        await fillSubmitForm(title, body);
        sendResponse({
          ok: false,
          error:
            "needs_user_action: title + body filled, choose a subreddit and click Submit yourself (Reddit blocks auto-submit)",
        });
      } catch (e) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
    })();
    return true;
  });
})();
