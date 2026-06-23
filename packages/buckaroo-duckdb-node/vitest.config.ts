import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
    // The spike test reaches a real DuckDB instance and writes temp parquet;
    // give it room beyond the 5s default.
    testTimeout: 30_000,
  },
});
