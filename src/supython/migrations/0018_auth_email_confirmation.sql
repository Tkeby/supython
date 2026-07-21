-- Email verification (GHSA pre-hijack fix, part 1).
--
-- `auth.users.email_confirmed_at` changes meaning with this release: it is now
-- stamped only by events that prove inbox ownership (signup-confirmation,
-- magic-link / OTP / recovery verification, or an OAuth sign-in whose provider
-- vouches the email is verified). Signup no longer stamps it unconditionally.
--
-- Rows created before this migration may carry an unproven timestamp from the
-- old auto-stamping signup. They are left untouched — nulling them would lock
-- out legitimate users when AUTH_REQUIRE_EMAIL_CONFIRMATION is enabled.
-- Operators who want the strict interpretation can run manually:
--
--     update auth.users set email_confirmed_at = null
--     where encrypted_password is not null
--       and not exists (select 1 from auth.identities i where i.user_id = users.id);

alter table auth.one_time_tokens
    drop constraint if exists one_time_tokens_type_check;
alter table auth.one_time_tokens
    add constraint one_time_tokens_type_check
        check (type in ('recover', 'magic_link', 'otp', 'signup_confirm'));

insert into admin.email_templates (name, subject, text_body) values
    ('signup_confirm', 'Confirm your email', 'Click the link to confirm your email: {{ url }}')
on conflict (name) do nothing;
