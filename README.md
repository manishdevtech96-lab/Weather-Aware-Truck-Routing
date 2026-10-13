# Weather-Aware-Truck-Routing# Weather-Aware Truck Routing

React + Django REST Framework starter for the assignment.

## Setup
1. Install Python 3.10+ and Node.js 18+.
2. Backend:
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env
   # Set MAPBOX_ACCESS_TOKEN in .env
   python manage.py migrate
   python manage.py runserver
   ```
3. Frontend, in another terminal:
   ```bash
   cd frontend
   npm install
   cp .env.example .env
   npm run dev
   ```

Backend: http://127.0.0.1:8000; frontend: Vite URL, usually http://localhost:5173.

## Deploy
Host the Django API and the React app separately. The browser calls the API using `VITE_API_BASE_URL`.

### 1. Put the code on GitHub
From the project root, commit the project and push it to a GitHub repository. Do not commit `backend/.env` or `frontend/.env`. Those files hold the Mapbox token.

### 2. Deploy the API on Render
1. Create a free [Render](https://render.com) account and choose **New Web Service**. Connect the GitHub repository.
2. Set the root directory to `backend`.
3. Build command: `pip install -r requirements.txt && python manage.py migrate`
4. Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --timeout 120`
5. Add these environment variables:
   - `DJANGO_SECRET_KEY`: a long random string
   - `DEBUG`: `False`
   - `MAPBOX_ACCESS_TOKEN`: your Mapbox public token
   - `ALLOWED_HOSTS`: `.onrender.com`
   - `CORS_ALLOWED_ORIGINS`: leave this until the frontend URL exists, then set it to that exact origin, for example `https://your-app.vercel.app`
6. Deploy. The API base URL looks like `https://your-service.onrender.com/api`. Open `https://your-service.onrender.com/api/health/` and confirm it returns `{"status":"ok"}`.

### 3. Deploy the website on Vercel
1. Create a [Vercel](https://vercel.com) project from the same GitHub repository.
2. Set the root directory to `frontend`. Framework preset: Vite.
3. Add the environment variable `VITE_API_BASE_URL` with the API URL from Render, including `/api`. Example: `https://your-service.onrender.com/api`
4. Deploy. Copy the site URL, such as `https://your-app.vercel.app`.
5. Back on Render, set `CORS_ALLOWED_ORIGINS` to that site URL and redeploy the API. The browser will otherwise block requests from the website to the API.

The first request after Render has been idle can take about a minute while the free service wakes up.

## Provider notes
- Mapbox is used for geocoding and routing.
- The Directions API often returns only one or two alternatives. The backend then requests additional distinct corridors (avoid highways, avoid tolls, or a waypoint off the direct line) until it has three routes, and it drops corridors that follow the same roads.
- Open-Meteo is used for hourly forecasts. Checkpoint risk uses the hour nearest the estimated arrival. The map slider recolors the corridor for each hour from departure through 48 hours.
- Open-Meteo precipitation and snowfall fields are hourly accumulations, used here as approximate hourly rates for assignment thresholds. This is a documented prototype limitation.
- ETA is estimated proportionally along route distance; production implementation should use segment durations.
- This is an assignment prototype, not a certified truck safety tool.