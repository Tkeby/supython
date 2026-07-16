-- Magic-link redirect target.
--
-- When a POST /auth/v1/magiclink request carries a redirect_url (validated
-- against MAGIC_LINK_REDIRECT_ALLOWLIST at request time), it is stored on the
-- one-time token here. GET /auth/v1/magiclink/verify then 302-redirects the
-- browser to that SPA URL with the token pair in the fragment — mirroring the
-- OAuth callback — instead of returning JSON. Storing the target server-side
-- (rather than echoing it in the emailed link) means an attacker who intercepts
-- the link cannot repoint it at a token-stealing origin.
--
-- Null ⇒ legacy behaviour: verify returns a JSON TokenResponse. Backfill-safe
-- (nullable, no default), so existing rows keep working.

alter table auth.one_time_tokens
    add column if not exists redirect_url text;
