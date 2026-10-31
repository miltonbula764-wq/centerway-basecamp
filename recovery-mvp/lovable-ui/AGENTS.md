<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

## Architecture rules — Mission 68 live synthetic demonstration
- Active pages import `api` from `src/data/live-runtime.ts`, over the existing `HttpTransport` and `SessionController`. No mock or fixture fallback in the active application.
- `/app` disables SSR. Opaque bearer tokens stay only in browser memory; refreshing requires explicit login. Never persist tokens or credentials in browser storage, URLs, logs, source or server-rendered data.
- Raw contracts mirror L01/F06. Missing metadata is not invented; names come from the authorized API directory.
- Tenant/client scope comes only from the authenticated session and authorized directory. Clear view/cache immediately on logout, expiry or scope change and discard late responses.
- Writes require explicit frozen drafts plus user confirmation. No automatic retries; uncertain responses may be resent explicitly with the identical request ID and content. Server permissions and intervention policies always decide.
- Preserve existing design, status accessibility and synthetic-only labels. Do not claim causal recovery.
- Fixtures and mock adapters are offline test support only, never imported by live routes/runtime.
