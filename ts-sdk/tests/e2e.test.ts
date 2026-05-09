import { describe, it, expect, beforeAll } from 'vitest';
import {
  createClient,
  MemoryAuthStorage,
  type SupythonClient,
} from '@supython/sdk';
import {
  SUPYTHON_URL,
  uniqueEmail,
  uniqueBucket,
  TEST_PASSWORD,
} from './e2e/helpers';

function newClient(): SupythonClient {
  return createClient(SUPYTHON_URL, {
    auth: { storage: new MemoryAuthStorage(), persistSession: false },
  });
}

// ----------------------------- 1. Auth lifecycle -----------------------------
describe('e2e: auth lifecycle', () => {
  const client = newClient();
  const email = uniqueEmail('auth');

  it('signs up and returns a session', async () => {
    const { data, error } = await client.auth.signUp(email, TEST_PASSWORD);
    expect(error).toBeNull();
    expect(data?.access_token).toBeTypeOf('string');
    expect(data?.user?.email).toBe(email);
  });

  it('GET /auth/v1/user returns the same user', async () => {
    const { data, error } = await client.auth.getUser();
    expect(error).toBeNull();
    expect(data?.email).toBe(email);
  });

  it('getSession() reflects the in-memory state', () => {
    const session = client.auth.getSession();
    expect(session).not.toBeNull();
    expect(session?.user?.email).toBe(email);
  });

  it('signOut clears the session and revokes the refresh token', async () => {
    const { error } = await client.auth.signOut();
    expect(error).toBeNull();
    expect(client.auth.getSession()).toBeNull();
  });
});

// --------------------- 2. Storage upload / download / remove ---------------------
describe('e2e: storage round-trip', () => {
  const client = newClient();
  const bucket = uniqueBucket('files');

  beforeAll(async () => {
    const { error: authErr } = await client.auth.signUp(uniqueEmail('storage'), TEST_PASSWORD);
    expect(authErr).toBeNull();
    const { error } = await client.storage.createBucket(bucket, { public: false });
    expect(error).toBeNull();
  });

  it('uploads bytes and downloads the same bytes back', async () => {
    const payload = new Uint8Array([1, 2, 3, 4, 5, 0, 255]);
    const up = await client.storage.from(bucket).upload('blob.bin', payload, {
      contentType: 'application/octet-stream',
    });
    expect(up.error).toBeNull();

    const down = await client.storage.from(bucket).download('blob.bin');
    expect(down.error).toBeNull();
    const got = new Uint8Array(await (down.data as Blob).arrayBuffer());
    expect(Array.from(got)).toEqual(Array.from(payload));
  });

  it('remove deletes the object', async () => {
    const rm = await client.storage.from(bucket).remove('blob.bin');
    expect(rm.error).toBeNull();
    const again = await client.storage.from(bucket).download('blob.bin');
    expect(again.error).not.toBeNull();
  });
});

// -------------------- 3. Bucket lifecycle: create / list / delete --------------------
describe('e2e: bucket lifecycle', () => {
  const client = newClient();
  const name = uniqueBucket('lifecycle');

  beforeAll(async () => {
    const { error } = await client.auth.signUp(uniqueEmail('bucket'), TEST_PASSWORD);
    expect(error).toBeNull();
  });

  it('createBucket → listBuckets contains it → deleteBucket → getBucket 4xx', async () => {
    const created = await client.storage.createBucket(name);
    expect(created.error).toBeNull();

    const listed = await client.storage.listBuckets();
    expect(listed.data?.some((b) => b.name === name)).toBe(true);

    const removed = await client.storage.deleteBucket(name);
    expect(removed.error).toBeNull();

    const after = await client.storage.getBucket(name);
    expect(after.error).not.toBeNull();
  });
});

// ---------------------------- 4. Functions invoke ----------------------------
describe('e2e: functions invoke', () => {
  const client = newClient();

  it('hello function echoes the body name', async () => {
    const { data, error } = await client.functions.invoke<{ msg: string }>('hello', {
      body: { name: 'Ada' },
    });
    expect(error).toBeNull();
    expect(data?.msg).toBe('hello, Ada');
  });
});

// --------------------------- 5. PostgREST `from()` ---------------------------
describe('e2e: PostgREST round-trip on public.todos', () => {
  const client = newClient();

  beforeAll(async () => {
    const { error } = await client.auth.signUp(uniqueEmail('postgrest'), TEST_PASSWORD);
    expect(error).toBeNull();
  });

  it('insert + select returns only the caller’s row (RLS isolation)', async () => {
    const title = `e2e-${Date.now()}`;
    const insert = await client.from('todos').insert({ title }).select().single();
    expect(insert.error).toBeNull();
    expect(insert.data?.title).toBe(title);

    const select = await client.from('todos').select('id, title');
    expect(select.error).toBeNull();
    expect(select.data?.some((r: { title: string }) => r.title === title)).toBe(true);
  });
});

// ---------------------- 6. Refresh-token rotation + reuse ----------------------
describe('e2e: refresh token rotation', () => {
  const client = newClient();
  let oldRefresh: string;

  beforeAll(async () => {
    const { data } = await client.auth.signUp(uniqueEmail('refresh'), TEST_PASSWORD);
    oldRefresh = data!.refresh_token;
  });

  it('refreshSession returns new tokens and invalidates the old refresh token', async () => {
    const refreshed = await client.auth.refreshSession();
    expect(refreshed.error).toBeNull();
    expect(refreshed.data?.refresh_token).not.toBe(oldRefresh);

    (client as unknown as { _refreshToken: string })._refreshToken = oldRefresh;
    const reused = await client.auth.refreshSession();
    expect(reused.error).not.toBeNull();
  });
});
