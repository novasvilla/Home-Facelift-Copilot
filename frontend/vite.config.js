import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'fs';
import path from 'path';

// Plugin: serve /static and /uploads from project root so images load by URL
function serveLocalFiles() {
  const rootDir = path.resolve(import.meta.dirname, '..');
  const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif' };
  function handler(baseDir) {
    return (req, res, next) => {
      const safePath = path.normalize(req.url).replace(/^\.\.\//, '');
      const filePath = path.join(rootDir, baseDir, safePath);
      if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
        const ext = path.extname(filePath).toLowerCase();
        res.setHeader('Content-Type', MIME[ext] || 'application/octet-stream');
        res.setHeader('Cache-Control', 'public, max-age=3600');
        fs.createReadStream(filePath).pipe(res);
      } else {
        next();
      }
    };
  }
  return {
    name: 'serve-local-files',
    configureServer(server) {
      server.middlewares.use('/static', handler('static'));
      server.middlewares.use('/uploads', handler('uploads'));
    },
  };
}

export default defineConfig({
  plugins: [react(), serveLocalFiles()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('error', (err, _req, res) => {
            console.warn('[proxy] Backend not ready:', err.code || err.message);
            if (res && !res.headersSent) {
              res.writeHead(502, { 'Content-Type': 'application/json' });
              res.end(JSON.stringify({ error: 'Backend not ready. Start it with: make backend' }));
            }
          });
        },
      },
    },
  },
});
