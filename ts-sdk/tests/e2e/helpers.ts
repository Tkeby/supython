import { randomBytes } from 'node:crypto';

export const SUPYTHON_URL = 'http://127.0.0.1:8001';

const RUN_TAG = randomBytes(4).toString('hex');

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${RUN_TAG}-${Date.now()}@example.com`;
}

export function uniqueBucket(prefix: string): string {
  return `${prefix}-${RUN_TAG}-${Date.now().toString(36)}`;
}

export const TEST_PASSWORD = 'password1234';
