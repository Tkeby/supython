import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { resolve } from 'path';
export default defineConfig({
    plugins: [vue()],
    base: '/admin/',
    resolve: {
        alias: { '@': resolve(__dirname, 'src') },
    },
    server: {
        proxy: { '/admin/api/v1': 'http://localhost:8000' },
    },
    build: {
        outDir: resolve(__dirname, '../src/supython/admin/static'),
        emptyOutDir: true,
        sourcemap: true,
    },
});
