/// <reference types="vitest" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  base: '/ClearSky-weather-PWA/',
  plugins: [
    react(),
    VitePWA({
      strategies: 'generateSW',
      injectRegister: 'auto',
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'clearsky-icon.svg', 'screenshot-wide.png', 'screenshot-narrow.png'],
      manifest: {
        name: 'ClearSky Weather',
        short_name: 'ClearSky',
        description: 'A calm, privacy-first weather forecast. Free, with no tracking.',
        theme_color: '#0ea5e9',
        background_color: '#0f172a',
        display: 'standalone',
        orientation: 'portrait',
        icons: [
          {
            src: 'pwa-192x192.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'pwa-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ],
        screenshots: [
          {
            src: 'screenshot-wide.png',
            sizes: '1280x720',
            type: 'image/png',
            form_factor: 'wide'
          },
          {
            src: 'screenshot-narrow.png',
            sizes: '720x1280',
            type: 'image/png',
            form_factor: 'narrow'
          }
        ]
      }
    })
  ],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
  }
});