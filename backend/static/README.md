# SugarBuddy - Local JSON data integration

This build removes mock data and loads data from local JSON files via backend endpoints.

## Backend endpoints required
- GET /api/local/profile/{user_id}
  - reads: data/profiles/{user_id}.json
- GET /api/local/schedule/{user_id}
  - reads: data/schedules/{user_id}*.json (handles filenames with full-width parentheses)

## Frontend
- user id is read from URL query: ?user_id=u_demo_young_male (default is u_demo_young_male)
- The app loads profile + schedule before rendering Profile/Timeline.

## Run
Use your FastAPI server (recommended) or any static server + correct API base.
