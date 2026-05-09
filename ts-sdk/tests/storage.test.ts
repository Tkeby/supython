import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { StorageClient, StorageBucket } from '../src/storage';
import type { Bucket, StorageObject, SignedUrl } from '../src/types/storage';
import { jsonResponse } from './helpers';

function bucketFixture(overrides: Partial<Bucket> = {}): Bucket {
  return {
    id: 'b-1',
    name: 'avatars',
    owner: 'u-1',
    public: false,
    file_size_limit: null,
    allowed_mime_types: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function objectFixture(overrides: Partial<StorageObject> = {}): StorageObject {
  return {
    id: 'o-1',
    bucket_id: 'b-1',
    bucket: 'avatars',
    name: 'pic.png',
    owner: 'u-1',
    size: 1234,
    mime_type: 'image/png',
    etag: 'abc',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function signedUrlFixture(overrides: Partial<SignedUrl> = {}): SignedUrl {
  return {
    signed_url: 'http://localhost:8000/storage/v1/object/signed/avatars/pic.png?token=abc',
    token: 'abc',
    expires_at: '2026-01-01T01:00:00Z',
    expires_in: 3600,
    ...overrides,
  };
}

function blobResponse(body: BodyInit, status = 200): Response {
  return new Response(body, { status, headers: { 'Content-Type': 'application/octet-stream' } });
}

function noContentResponse(status = 204): Response {
  return new Response(null, { status });
}

function fixedHeaders(token?: string): () => Record<string, string> {
  return () => {
    const h: Record<string, string> = { apikey: 'anon-key' };
    if (token) h.Authorization = `Bearer ${token}`;
    return h;
  };
}

const BASE = 'http://localhost:8000/storage/v1';

describe('StorageClient', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  let client: StorageClient;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    client = new StorageClient(BASE, fixedHeaders());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('from()', () => {
    it('returns a StorageBucket that targets the correct URL prefix', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(objectFixture()));
      const bucket = client.from('avatars');
      await bucket.upload('pic.png', new Blob([new Uint8Array([1, 2, 3])]));
      const url = fetchSpy.mock.calls[0]![0] as string;
      expect(url).toBe(`${BASE}/object/avatars/pic.png`);
    });
  });

  describe('createBucket', () => {
    it('sends minimal payload when no options', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(bucketFixture({ public: false }), 201));
      const { data } = await client.createBucket('avatars');
      expect(data!.name).toBe('avatars');
      const [, init] = fetchSpy.mock.calls[0]!;
      expect(JSON.parse(init.body as string)).toEqual({ name: 'avatars', public: false });
    });

    it('includes optional fields only when defined', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(bucketFixture({
        public: true, file_size_limit: 1048576, allowed_mime_types: ['image/png'],
      }), 201));
      await client.createBucket('images', {
        public: true, file_size_limit: 1048576, allowed_mime_types: ['image/png'],
      });
      const body = JSON.parse((fetchSpy.mock.calls[0]![1] as RequestInit).body as string);
      expect(body).toEqual({
        name: 'images', public: true, file_size_limit: 1048576, allowed_mime_types: ['image/png'],
      });
    });

    it('propagates 409 bucket_exists error', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'bucket_exists', message: 'already exists' } }, 409,
      ));
      const { data, error } = await client.createBucket('avatars');
      expect(data).toBeNull();
      expect(error!.status).toBe(409);
      expect(error!.code).toBe('bucket_exists');
    });

    it('returns normalized network error on fetch failure', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      const { data, error } = await client.createBucket('avatars');
      expect(data).toBeNull();
      expect(error!.code).toBe('network_error');
      expect(error!.status).toBe(0);
    });
  });

  describe('listBuckets', () => {
    it('returns Bucket[] on success', async () => {
      const buckets = [bucketFixture(), bucketFixture({ id: 'b-2', name: 'docs' })];
      fetchSpy.mockResolvedValueOnce(jsonResponse(buckets));
      const { data, error } = await client.listBuckets();
      expect(error).toBeNull();
      expect(data!.length).toBe(2);
    });

    it('returns empty array', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse([]));
      const { data, error } = await client.listBuckets();
      expect(error).toBeNull();
      expect(data).toEqual([]);
    });
  });

  describe('getBucket', () => {
    it('returns bucket on success', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(bucketFixture()));
      const { data, error } = await client.getBucket('avatars');
      expect(error).toBeNull();
      expect(data!.name).toBe('avatars');
    });

    it('propagates 404 bucket_not_found', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'bucket_not_found', message: 'not found' } }, 404,
      ));
      const { data, error } = await client.getBucket('nope');
      expect(data).toBeNull();
      expect(error!.code).toBe('bucket_not_found');
    });
  });

  describe('deleteBucket', () => {
    it('returns { data: null, error: null } on 204', async () => {
      fetchSpy.mockResolvedValueOnce(noContentResponse());
      const { data, error } = await client.deleteBucket('avatars');
      expect(data).toBeNull();
      expect(error).toBeNull();
      expect((fetchSpy.mock.calls[0]![1] as RequestInit).method).toBe('DELETE');
    });

    it('propagates 409 bucket_not_empty', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'bucket_not_empty', message: 'not empty' } }, 409,
      ));
      const { data, error } = await client.deleteBucket('avatars');
      expect(data).toBeNull();
      expect(error!.code).toBe('bucket_not_empty');
    });

    it('returns normalized network error', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      const { error } = await client.deleteBucket('avatars');
      expect(error!.code).toBe('network_error');
    });
  });
});

describe('StorageBucket', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;
  let client: StorageClient;
  let bucket: StorageBucket;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    client = new StorageClient(BASE, fixedHeaders());
    bucket = client.from('avatars');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('upload', () => {
    it('sends multipart with file field and returns StorageObject', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(objectFixture(), 201));
      const body = new Blob([new Uint8Array([1, 2, 3])]);
      const { data, error } = await bucket.upload('pic.png', body);
      expect(error).toBeNull();
      expect(data!.name).toBe('pic.png');
      const [, init] = fetchSpy.mock.calls[0]!;
      expect(init.headers).not.toHaveProperty('Content-Type');
      const fd = init.body as FormData;
      expect(fd.get('file')).toBeInstanceOf(Blob);
    });

    it('accepts Blob body directly', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(objectFixture(), 201));
      const blob = new Blob([new Uint8Array([4, 5, 6])], { type: 'image/png' });
      await bucket.upload('pic.png', blob);
      const fd = (fetchSpy.mock.calls[0]![1] as RequestInit).body as FormData;
      const file = fd.get('file') as Blob;
      expect(file.type).toBe('image/png');
      expect(file.size).toBe(3);
    });

    it('wraps ArrayBuffer/string with contentType', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(objectFixture(), 201));
      await bucket.upload('data.bin', new Uint8Array([7, 8, 9]).buffer, { contentType: 'text/plain' });
      const fd = (fetchSpy.mock.calls[0]![1] as RequestInit).body as FormData;
      const file = fd.get('file') as Blob;
      expect(file.type).toBe('text/plain');
    });

    it('propagates 413 file_too_large error', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'file_too_large', message: 'too large' } }, 413,
      ));
      const { data, error } = await bucket.upload('big.bin', new Blob([new ArrayBuffer(1)]));
      expect(data).toBeNull();
      expect(error!.status).toBe(413);
      expect(error!.code).toBe('file_too_large');
    });

    it('returns normalized network error', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      const { error } = await bucket.upload('pic.png', new Blob([]));
      expect(error!.code).toBe('network_error');
      expect(error!.status).toBe(0);
    });
  });

  describe('download', () => {
    it('returns Blob on 200', async () => {
      const bytes = new Uint8Array([10, 20, 30]);
      fetchSpy.mockResolvedValueOnce(blobResponse(bytes));
      const { data, error } = await bucket.download('pic.png');
      expect(error).toBeNull();
      expect(data).toBeInstanceOf(Blob);
      const buf = new Uint8Array(await data!.arrayBuffer());
      expect(buf).toEqual(bytes);
    });

    it('propagates 404 error', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'object_not_found', message: 'not found' } }, 404,
      ));
      const { data, error } = await bucket.download('nope.png');
      expect(data).toBeNull();
      expect(error!.status).toBe(404);
      expect(error!.code).toBe('object_not_found');
    });

    it('returns normalized network error', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      const { error } = await bucket.download('pic.png');
      expect(error!.code).toBe('network_error');
    });
  });

  describe('remove', () => {
    it('returns { data: null, error: null } on 204', async () => {
      fetchSpy.mockResolvedValueOnce(noContentResponse());
      const { data, error } = await bucket.remove('pic.png');
      expect(data).toBeNull();
      expect(error).toBeNull();
      expect((fetchSpy.mock.calls[0]![1] as RequestInit).method).toBe('DELETE');
    });

    it('propagates 404 error', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'object_not_found', message: 'not found' } }, 404,
      ));
      const { error } = await bucket.remove('nope.png');
      expect(error!.status).toBe(404);
    });

    it('returns normalized network error', async () => {
      fetchSpy.mockRejectedValueOnce(new TypeError('Failed to fetch'));
      const { error } = await bucket.remove('pic.png');
      expect(error!.code).toBe('network_error');
    });
  });

  describe('createSignedUrl', () => {
    it('sends empty JSON body when no expiresIn', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(signedUrlFixture()));
      const { data, error } = await bucket.createSignedUrl('pic.png');
      expect(error).toBeNull();
      expect(data!.token).toBe('abc');
      const body = (fetchSpy.mock.calls[0]![1] as RequestInit).body as string;
      expect(body).toBe('{}');
    });

    it('sends expires_in when provided', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(signedUrlFixture()));
      await bucket.createSignedUrl('pic.png', { expiresIn: 600 });
      const body = (fetchSpy.mock.calls[0]![1] as RequestInit).body as string;
      expect(JSON.parse(body)).toEqual({ expires_in: 600 });
    });

    it('propagates 404 error', async () => {
      fetchSpy.mockResolvedValueOnce(jsonResponse(
        { detail: { code: 'object_not_found', message: 'not found' } }, 404,
      ));
      const { error } = await bucket.createSignedUrl('nope.png');
      expect(error!.code).toBe('object_not_found');
    });
  });

  describe('getPublicUrl', () => {
    it('returns correct URL without fetching', () => {
      const url = bucket.getPublicUrl('pic.png');
      expect(url).toBe(`${BASE}/object/public/avatars/pic.png`);
      expect(fetchSpy).not.toHaveBeenCalled();
    });
  });
});

describe('Header injection', () => {
  let fetchSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('includes apikey from getHeaders on every request', async () => {
    const client = new StorageClient(BASE, fixedHeaders());
    fetchSpy.mockResolvedValue(jsonResponse([]));
    await client.listBuckets();
    const headers = (fetchSpy.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    expect(headers.apikey).toBe('anon-key');
  });

  it('invokes getHeaders per-request, observing token changes', async () => {
    let currentToken: string | null = 'token-a';
    const getHeaders = () => {
      const h: Record<string, string> = { apikey: 'anon-key' };
      if (currentToken) h.Authorization = `Bearer ${currentToken}`;
      return h;
    };
    const client = new StorageClient(BASE, getHeaders);
    fetchSpy.mockResolvedValue(jsonResponse(bucketFixture()));

    await client.getBucket('avatars');
    let headers = (fetchSpy.mock.calls[0]![1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer token-a');

    currentToken = 'token-b';
    await client.getBucket('avatars');
    headers = (fetchSpy.mock.calls[1]![1] as RequestInit).headers as Record<string, string>;
    expect(headers.Authorization).toBe('Bearer token-b');
  });
});

describe('URL construction', () => {
  it('strips trailing slash from base URL', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(objectFixture(), 201));
    vi.stubGlobal('fetch', fetchSpy);
    const client = new StorageClient(`${BASE}/`, fixedHeaders());
    const bucket = client.from('avatars');
    await bucket.upload('pic.png', new Blob([]));
    const url = fetchSpy.mock.calls[0]![0] as string;
    expect(url).toBe(`${BASE}/object/avatars/pic.png`);
    expect(url).not.toContain('//object');
    vi.restoreAllMocks();
  });
});
