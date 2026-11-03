import { defineConfig } from 'vite';
import path from 'node:path';

export default defineConfig({
  resolve: { alias: {
    '@framework': path.resolve(__dirname, '../.local/sdk/CubismSdkForWeb-5-r.5/Framework/src'),
  } },
  build: { target: 'es2022' },
});
