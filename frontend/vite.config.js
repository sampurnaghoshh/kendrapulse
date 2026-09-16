import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// No dev-server proxy yet: the backend has no HTTP surface until Phase 5.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
})
