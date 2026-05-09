-- Store editable email templates so operators can customise the auth emails
-- without touching source files. The auth module looks up templates by name;
-- if a row exists, its subject + text_body are used instead of the built-in
-- default.

create table if not exists admin.email_templates (
    name       text primary key,
    subject    text not null,
    text_body  text not null,
    updated_at timestamptz not null default now()
);

-- Seed the three templates the auth module currently ships as hard-coded
-- strings, so the operator sees the current defaults on first open.
insert into admin.email_templates (name, subject, text_body) values
    ('recover',    'Reset your password',                     'Use this token to reset your password: {{ token }}'),
    ('magic_link', 'Sign in to your account',                 'Click the link to sign in: {{ url }}'),
    ('otp',        'Your one-time password',                  'Your OTP is: {{ token }}')
on conflict (name) do nothing;
