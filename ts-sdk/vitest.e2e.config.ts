import { defineConfig } from 'vitest/config';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      '@supython/sdk': resolve(ROOT, 'src', 'index.ts'),
    },
  },
  test: {
    globals: true,
    environment: 'node',
    include: ['tests/e2e.test.ts'],
    globalSetup: ['tests/e2e/globalSetup.ts'],
    testTimeout: 30_000,
    hookTimeout: 60_000,
    pool: 'forks',
    poolOptions: { forks: { singleFork: true } },
    fileParallelism: false,
    coverage: { enabled: false },
  },
});
