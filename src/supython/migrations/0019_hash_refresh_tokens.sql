-- Refresh tokens at rest are now sha256 hashes (like auth.one_time_tokens),
-- so a DB dump or backup leak no longer yields live sessions. The service
-- hashes the presented raw token before lookup; only the client ever holds
-- the raw value.
--
-- In-place transform of pre-existing rows. Guard: raw tokens are 64-char
-- base64url (secrets.token_urlsafe(48)) and contain characters outside
-- [0-9a-f]; an already-hashed value is exactly 64 lowercase hex chars, so
-- the regex makes this idempotent. (A raw token that is coincidentally all
-- lowercase hex would be skipped and its session die at next refresh —
-- probability ~2^-128, accepted.)

update auth.refresh_tokens
set token = encode(sha256(convert_to(token, 'utf8')), 'hex')
where token !~ '^[0-9a-f]{64}$';

update auth.refresh_tokens
set parent = encode(sha256(convert_to(parent, 'utf8')), 'hex')
where parent is not null and parent !~ '^[0-9a-f]{64}$';
