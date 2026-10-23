import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'
import { viteStaticCopy } from 'vite-plugin-static-copy'

export default defineConfig({
  plugins: [vue(), tailwindcss(), viteStaticCopy({
    targets: ['cmaps', 'standard_fonts', 'wasm'].map(directory => ({
      src: `node_modules/pdfjs-dist/${directory}/*`, dest: `pdfjs/${directory}`,
      rename: { stripBase: true },
    })),
  })],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    strictPort: true,
    proxy: { '/api': { target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:18400' } },
  },
})
