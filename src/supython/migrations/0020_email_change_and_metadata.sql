-- Email change with dual confirmation + user/app metadata wire-up.
--
-- raw_user_meta_data (0002) is user-controlled: the account holder can
-- rewrite it via PUT /auth/v1/user. NEVER reference it in RLS policies or
-- authorization decisions. raw_app_meta_data is the server-controlled
-- counterpart (set only by supython itself: provider info, operator flags);
-- policies may read it.
--
-- email_change holds the pending new address during a change;
-- email_change_confirm_status is a bitmask (1 = current inbox confirmed,
-- 2 = new inbox confirmed); the change applies at 3.

alter table auth.users
    add column if not exists raw_app_meta_data jsonb not null default '{}'::jsonb;
alter table auth.users
    add column if not exists email_change citext;
alter table auth.users
    add column if not exists email_change_confirm_status smallint not null default 0;

alter table auth.one_time_tokens
    drop constraint if exists one_time_tokens_type_check;
alter table auth.one_time_tokens
    add constraint one_time_tokens_type_check
        check (type in (
            'recover', 'magic_link', 'otp', 'signup_confirm',
            'email_change_current', 'email_change_new'
        ));

insert into admin.email_templates (name, subject, text_body) values
    ('email_change_current', 'Confirm your email change',
     'A change of your account email to {{ new_email }} was requested. Confirm from this (current) address: {{ url }}'),
    ('email_change_new', 'Confirm your new email',
     'Confirm this address as the new email for your account: {{ url }}')
on conflict (name) do nothing;
