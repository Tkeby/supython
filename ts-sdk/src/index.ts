// ts-sdk/src/index.ts
//
// Public entry point for @supython/sdk. Anything not re-exported here is
// SDK-internal and may break between minor versions.

// ---- Composition ----
export { SupythonClient, createClient } from './client';
export type {
  SupythonClientOptions,
  AuthOptions,
  TableName,
} from './client';

// ---- Auth ----
export { AuthClient } from './auth';
export type {
  Session,
  User,
  TokenResponse,
  AuthChangeEvent,
  AuthChangeCallback,
} from './types/auth';

// ---- Storage ----
export { StorageClient, StorageBucket } from './storage';
export type {
  Bucket,
  StorageObject,
  SignedUrl,
  CreateBucketOptions,
  UploadOptions,
  CreateSignedUrlOptions,
  FileBody,
} from './types/storage';

// ---- Functions ----
export { FunctionsClient } from './functions';
export type { InvokeOptions } from './functions';

// ---- Errors ----
export type {
  AuthError,
  StorageError,
  FunctionsError,
  SupythonError,
  SupythonResponse,
} from './errors';

// ---- Auth-storage backends ----
export {
  MemoryAuthStorage,
  LocalStorageAuthStorage,
  CookieAuthStorage,
  isBrowserStorage,
} from './storage-backends';
export type {
  AuthStorageBackend,
  CookieAuthStorageOptions,
} from './storage-backends';
