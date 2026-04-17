# Security policy

## Supported versions

Fanout is pre-1.0. Security fixes are applied to the `main` branch only — please
use the latest commit until a tagged release is published.

| Version | Supported |
|---------|-----------|
| `main`  | ✅        |
| anything else | ❌  |

## Trust model

Fanout is designed so the **server never holds platform credentials**. By design:

- The backend stores generated drafts and their delivery status, scoped per `user_id`.
  It does **not** store passwords, OAuth refresh tokens, or session cookies for any
  third-party platform (LinkedIn, X, Reddit, etc.).
- The browser extension is the only component that interacts with social platforms.
  It uses the user's existing logged-in browser session — no credentials cross our
  boundary.
- The Groq API key lives in `backend/.env` server-side. It is never sent to the
  browser, the extension, or any platform.
- If Supabase auth is enabled, the Supabase JWT is the only secret a client holds;
  it is verified with the JWT secret server-side and scopes all writes to a `user_id`.

If a vulnerability would let an attacker:

- Read or post on behalf of another user's social accounts
- Read another user's drafts
- Exfiltrate the Groq API key from the running backend
- Cause RCE in the backend or the extension

…we treat it as a **high** severity issue and want to know about it.

Out of scope (won't generally be treated as security issues):

- DOM-selector breakage on a third-party platform (these rot continuously and are
  bug reports, not security reports)
- Posts from the extension being detected as automation by a platform — the extension
  acts in your browser; if a platform's terms forbid that, the user accepts the risk
- Rate limiting / DOS of the local dev server

## Reporting a vulnerability

Please **do not open a public GitHub issue** for security reports.

Two reporting channels:

1. **Preferred** — open a private security advisory on this repository:
   <https://github.com/MukundaKatta/fanout/security/advisories/new>
2. **Email** — `mukunda.vjcs6@gmail.com` with the subject line beginning `[SECURITY]`.

Please include:

- A clear description of the issue and its impact
- Steps to reproduce (or a proof of concept)
- Any suggestions for remediation
- Your contact info if you'd like to be credited

We aim to acknowledge reports within **3 business days** and to ship a fix or
mitigation within **14 days** for high-severity issues. Researchers acting in good
faith will not be pursued legally.

## Disclosure

Once a fix is shipped, we'll publish a GitHub Security Advisory crediting the
reporter (unless they request anonymity), including the affected commits and
the upgrade path.
