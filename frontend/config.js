/* LedgerLens Runtime Config
   Set VITE_API_BASE_URL or BSP_API_URL before build,
   or update this file manually to point to your backend URL.
   
   When deployed:
   - Frontend on Vercel: update API_BASE_URL below to your Render URL
   - Backend on Render: leave as-is (same origin)
*/
window.LEDGERLENS_CONFIG = {
  // If the backend is on a different domain (e.g. Render), set the full URL:
  // API_BASE_URL: "https://your-app.onrender.com"
  // If frontend and backend are on the same host, leave this empty:
  API_BASE_URL: ""
};
