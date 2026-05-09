/** Metadata for a storage bucket. */
export interface Bucket {
  id: string;
  name: string;
  owner: string | null;
  public: boolean;
  file_size_limit: number | null;
  allowed_mime_types: string[] | null;
  created_at: string;   // ISO-8601 UTC
  updated_at: string;   // ISO-8601 UTC
}

/** Metadata for a stored object. */
export interface StorageObject {
  id: string;
  bucket_id: string;
  bucket: string;
  name: string;
  owner: string;
  size: number;
  mime_type: string | null;
  etag: string | null;
  created_at: string;
  updated_at: string;
}

/** Time-limited signed URL returned by {@link StorageBucket.createSignedUrl}. */
export interface SignedUrl {
  signed_url: string;
  token: string;
  expires_at: string;   // ISO-8601 UTC
  expires_in: number;   // seconds
}

/** Options passed to {@link StorageClient.createBucket}. */
export interface CreateBucketOptions {
  public?: boolean;                  // default: false
  file_size_limit?: number;          // bytes, server-validated >= 1
  allowed_mime_types?: string[];
}

/** Options passed to {@link StorageBucket.upload}. */
export interface UploadOptions {
  contentType?: string;              // default: 'application/octet-stream'
}

/** Options passed to {@link StorageBucket.createSignedUrl}. */
export interface CreateSignedUrlOptions {
  expiresIn?: number;                // seconds; omit → server default
}

/**
 * Permissive body type for uploads — anything `FormData.append` accepts.
 * Strings are treated as text payloads.
 */
export type FileBody = Blob | ArrayBuffer | ArrayBufferView | string;
