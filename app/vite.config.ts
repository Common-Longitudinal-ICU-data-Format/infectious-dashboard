import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Data JSON is written by `python export/export.py` into app/public/data and
// is served as static files, so there is no backend at runtime.
export default defineConfig({
  plugins: [react()],
  base: './',
  server: { port: 5173, open: false },
});
