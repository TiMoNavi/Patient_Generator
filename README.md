# PatientGenerator

FastAPI backend with a static chat UI that streams replies from Coze.

## Prerequisites
- Python 3.10+
- pip
- Internet access to reach the configured Coze endpoint

## Setup
1) Create and activate a virtual environment
```
python -m venv .venv
.\.venv\Scripts\activate
```
2) Install backend dependencies
```
pip install -r backend/requirements.txt
```

## Configuration
- Copy `backend/.env.example` to `backend/.env` and set values
- Required variables:
  - `COZE_ENDPOINT`
  - `COZE_TOKEN`
  - `COZE_PROJECT_ID`
- Keep tokens private; do not commit `.env`

## Run
- Activate the virtual environment
- Start the API server
```
uvicorn backend.app:app --reload --port 8000
```
- Open `http://127.0.0.1:8000/` for the chat UI

### API quick test
- Plain reply
```
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"text\":\"hello\"}"
```
- Streaming (Server-Sent Events)
```
curl -N -X POST http://127.0.0.1:8000/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d "{\"text\":\"hello\"}"
```

## Notes
- If `.env` is missing or incomplete, the server returns a mock echo response instead of calling Coze.
- Static client lives at `backend/static/index.html` and is served at `/`.
