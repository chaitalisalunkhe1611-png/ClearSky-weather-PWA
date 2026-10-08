# ClearSky

A free, privacy-first weather PWA: a clear forecast, useful daily notes, and no tracking. ClearSky is pure frontend—no backend, API keys, accounts, analytics, or trackers. The interface is built with React 18, TypeScript, Vite, Tailwind CSS, and Recharts; forecast data comes from Open-Meteo.

## Screenshots

_Add desktop and mobile screenshots here._

## Features

- Search for a city with a debounced, keyboard-navigable results list, or explicitly choose **Use my location**. Location permission is never requested on page load.
- Save multiple places locally and share the active location with a URL hash.
- Current conditions, feels-like temperature, humidity, wind, UV, color-coded US AQI, and local sunrise/sunset.
- Scrollable 48-hour temperature and precipitation-probability chart, plus a 7-day high/low outlook.
- A deterministic daily briefing highlights rain timing and a dry window, high UV, strong wind, frost, or a notable temperature change. On quieter days it suggests a mild, low-rain outdoor window.
- Celsius/Fahrenheit, km/h/mph, and light/dark/system preferences.
- Installable PWA with offline support. The latest successful forecast for each location is saved locally with its timestamp; Open-Meteo API responses are cached for 15 minutes.
- Responsive glass-style interface, condition-aware day/night backgrounds, loading skeletons, retry states, and accessible controls.

## Privacy

There is no ClearSky server. Forecast, air-quality, and city-search requests go directly from your browser to Open-Meteo. Choosing a city sends that search term to Open-Meteo's geocoding service; using device location sends its coordinates to Open-Meteo to get a forecast. ClearSky does not request geolocation until you choose the button. Saved locations, the active location, forecast cache, and preferences are stored in your browser's `localStorage`; nothing is sent to a ClearSky account or analytics service. Data use is subject to [Open-Meteo's terms](https://open-meteo.com/en/terms).

## Local development

Requirements: Node.js 22.12 or later and npm.

```bash
git clone https://github.com/chaitalisalunkhe1611-png/ai_cartoonmaker.git
cd ai_cartoonmaker
npm install
npm run dev
```

Useful checks:

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run preview
```

The production build is written to `dist/`. No API key or `.env` file is needed.

## Deploy to GitHub Pages

1. Push the repository's `main` branch to GitHub.
2. In **Settings → Pages**, choose **GitHub Actions** as the build and deployment source.
3. The workflow in `.github/workflows/ci.yml` runs lint, typecheck, tests, and a production build on pushes and pull requests. A successful push to `main` deploys `dist/` to Pages.
4. Vite uses `/ai_cartoonmaker/` as its production base path in GitHub Actions; local development and preview use `/`.

## Data attribution

Weather forecasts and air-quality data are provided by [Open-Meteo](https://open-meteo.com/) and attributed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/). City lookup uses the Open-Meteo Geocoding API.

## License

ClearSky is licensed under the [MIT License](LICENSE).
