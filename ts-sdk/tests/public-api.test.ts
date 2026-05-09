import { describe, it, expect } from 'vitest';
import * as sdk from '../src';

describe('public API surface', () => {
  it('runtime exports match the v0.1.0 contract', () => {
    expect(Object.keys(sdk).sort()).toEqual([
      'AuthClient',
      'CookieAuthStorage',
      'FunctionsClient',
      'LocalStorageAuthStorage',
      'MemoryAuthStorage',
      'StorageBucket',
      'StorageClient',
      'SupythonClient',
      'createClient',
      'isBrowserStorage',
    ]);
  });

  it('createClient produces a SupythonClient instance', () => {
    const client = sdk.createClient('http://localhost:8000', { anonKey: 'a' });
    expect(client).toBeInstanceOf(sdk.SupythonClient);
  });

  it('factory and class are interchangeable', () => {
    const a = sdk.createClient('http://localhost:8000', { anonKey: 'a' });
    const b = new sdk.SupythonClient('http://localhost:8000', { anonKey: 'a' });
    expect(Object.keys(a).sort()).toEqual(Object.keys(b).sort());
  });
});
