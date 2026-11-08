# Security

- Listens on **127.0.0.1 only**, so other devices cannot connect. Do not change this without approval.
- No API keys are needed or stored. If an OpenF1 token is ever approved, keep it in an environment variable, never in Git.
- Input is validated: numbers are range-checked, driver ids must match `[a-z0-9_]`, and static file paths are locked to `static/`.
- Headers: a strict Content-Security-Policy (self only), `nosniff` and `no-store`. Errors never return stack traces.
- No third-party packages. The browser loads no external scripts or fonts.
- `.cache/` holds only public API responses and is git-ignored.
