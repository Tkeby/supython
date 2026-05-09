import { parseBlobResponse, parseSupythonResponse, wrapNetworkError } from './errors';
import type {
  Bucket,
  CreateBucketOptions,
  CreateSignedUrlOptions,
  FileBody,
  SignedUrl,
  StorageObject,
  UploadOptions,
} from './types/storage';
import type { GetHeaders, SupythonResponse } from './errors';

/**
 * StorageClient manages buckets and produces {@link StorageBucket} handles
 * for object operations. It delegates all HTTP to `fetch` and reads headers
 * from the supplied `getHeaders` callback per-request.
 */
export class StorageClient {
  /** @internal — exposed for StorageBucket only; not part of the public API. */
  readonly _url: string;
  /** @internal */
  readonly _getHeaders: GetHeaders;

  constructor(url: string, getHeaders: GetHeaders) {
    this._url = url.replace(/\/$/, '');
    this._getHeaders = getHeaders;
  }

  /** Return a {@link StorageBucket} handle for the named bucket. */
  from(bucketName: string): StorageBucket {
    return new StorageBucket(this, bucketName);
  }

  /** Create a new bucket. */
  async createBucket(name: string, options?: CreateBucketOptions): Promise<SupythonResponse<Bucket>> {
    const body: Record<string, unknown> = { name, public: options?.public ?? false };
    if (options?.file_size_limit !== undefined) body.file_size_limit = options.file_size_limit;
    if (options?.allowed_mime_types !== undefined) body.allowed_mime_types = options.allowed_mime_types;
    return this._request<Bucket>('/bucket', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  }

  /** List all buckets. */
  async listBuckets(): Promise<SupythonResponse<Bucket[]>> {
    return this._request<Bucket[]>('/bucket', { method: 'GET' });
  }

  /** Get metadata for a single bucket by name. */
  async getBucket(name: string): Promise<SupythonResponse<Bucket>> {
    return this._request<Bucket>(`/bucket/${name}`, { method: 'GET' });
  }

  /** Delete a bucket. */
  async deleteBucket(name: string): Promise<SupythonResponse<null>> {
    return this._request<null>(`/bucket/${name}`, { method: 'DELETE' }, true);
  }

  private async _request<T>(
    path: string,
    init: RequestInit,
    expectStatus204 = false,
  ): Promise<SupythonResponse<T>> {
    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._url}${path}`, {
        ...init,
        headers: { ...this._getHeaders(), ...(init.headers as Record<string, string> | undefined) },
      });
      if (expectStatus204 && resp.status === 204) {
        return { data: null as unknown as T, error: null };
      }
      return parseSupythonResponse<T>(resp, 'storage');
    }, 'storage');
  }
}

/**
 * StorageBucket performs object-level operations inside a single bucket.
 *
 * Object keys (`path`) are passed through verbatim — callers are responsible
 * for sanitisation. Keys must not start with a leading `/`.
 */
export class StorageBucket {
  private readonly _client: StorageClient;
  private readonly _bucket: string;

  constructor(client: StorageClient, bucket: string) {
    this._client = client;
    this._bucket = bucket;
  }

  /**
   * Upload an object to `path` inside this bucket.
   *
   * The body is sent as `multipart/form-data` under field name `file`.
   * `Blob`/`File` bodies are appended directly; other values are wrapped
   * in a `Blob` with `options.contentType` (default `application/octet-stream`).
   */
  async upload(path: string, body: FileBody, options?: UploadOptions): Promise<SupythonResponse<StorageObject>> {
    return wrapNetworkError(async () => {
      const form = new FormData();
      if (body instanceof Blob) {
        form.append('file', body);
      } else {
        const blob = new Blob([body as BlobPart], { type: options?.contentType ?? 'application/octet-stream' });
        form.append('file', blob, path.split('/').pop() ?? 'file');
      }
      const resp = await fetch(`${this._client._url}/object/${this._bucket}/${path}`, {
        method: 'POST',
        headers: this._client._getHeaders(),
        body: form,
      });
      return parseSupythonResponse<StorageObject>(resp, 'storage');
    }, 'storage');
  }

  /** Download the object at `path` as a {@link Blob}. */
  async download(path: string): Promise<SupythonResponse<Blob>> {
    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._client._url}/object/${this._bucket}/${path}`, {
        headers: this._client._getHeaders(),
      });
      return parseBlobResponse(resp);
    }, 'storage');
  }

  /** Remove a single object at `path`. Batch removal is not yet supported. */
  async remove(path: string): Promise<SupythonResponse<null>> {
    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._client._url}/object/${this._bucket}/${path}`, {
        method: 'DELETE',
        headers: this._client._getHeaders(),
      });
      if (resp.status === 204) return { data: null, error: null };
      return parseSupythonResponse<null>(resp, 'storage');
    }, 'storage');
  }

  /**
   * Create a time-limited signed URL for the object at `path`.
   *
   * @param expiresIn — lifetime in seconds; omit to use the server default.
   */
  async createSignedUrl(path: string, options?: CreateSignedUrlOptions): Promise<SupythonResponse<SignedUrl>> {
    const body = options?.expiresIn !== undefined
      ? JSON.stringify({ expires_in: options.expiresIn })
      : JSON.stringify({});
    return wrapNetworkError(async () => {
      const resp = await fetch(`${this._client._url}/object/sign/${this._bucket}/${path}`, {
        method: 'POST',
        headers: { ...this._client._getHeaders(), 'Content-Type': 'application/json' },
        body,
      });
      return parseSupythonResponse<SignedUrl>(resp, 'storage');
    }, 'storage');
  }

  /**
   * Return the public URL for an object. No HTTP call is made.
   *
   * Note: this does not verify that the bucket is actually public —
   * callers must ensure the bucket settings match their use-case.
   */
  getPublicUrl(path: string): string {
    return `${this._client._url}/object/public/${this._bucket}/${path}`;
  }
}
