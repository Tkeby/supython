//
// Not executed at runtime. tsc --noEmit verifies the imports compile.

import type {
  // composition
  SupythonClientOptions, AuthOptions, TableName,
  // auth
  Session, User, TokenResponse, AuthChangeEvent, AuthChangeCallback,
  // storage
  Bucket, StorageObject, SignedUrl,
  CreateBucketOptions, UploadOptions, CreateSignedUrlOptions, FileBody,
  // functions
  InvokeOptions,
  // errors
  AuthError, StorageError, FunctionsError, SupythonError, SupythonResponse,
  // auth-storage
  AuthStorageBackend, CookieAuthStorageOptions,
} from '../src';

// Force usage so unused-import rules don't silently drop the assertion.
type _AssertExported =
  | SupythonClientOptions | AuthOptions | TableName
  | Session | User | TokenResponse | AuthChangeEvent | AuthChangeCallback
  | Bucket | StorageObject | SignedUrl
  | CreateBucketOptions | UploadOptions | CreateSignedUrlOptions | FileBody
  | InvokeOptions
  | AuthError | StorageError | FunctionsError | SupythonError
  | SupythonResponse<unknown>
  | AuthStorageBackend | CookieAuthStorageOptions;
