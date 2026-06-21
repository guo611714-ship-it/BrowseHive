import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './',  // 使用相对路径，打包后才能正确加载
  server: {
    port: 5173
  }
});
