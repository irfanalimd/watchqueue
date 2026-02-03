# WatchQueue - Agent Context Guide

## Application Concept
A collaborative movie/show selection system for groups. Core flow:
1. **Create/Join Room** with a short join code
2. **Shared Queue** where members add movies/shows
3. **Voting** with up/down votes and real-time updates
4. **Selection** via weighted random, highest votes, or round robin
5. **History** of watched items with ratings/notes

## Tech Stack
- **Language**: Python 3.11+
- **Framework**: FastAPI (async)
- **Database**: MongoDB replica set via Motor
- **Real-time**: WebSocket + SSE (MongoDB change streams)
- **External API**: TMDB metadata via httpx
- **Validation**: Pydantic v2 + pydantic-settings
- **Tests**: pytest + pytest-asyncio + respx

## Code Structure

### `/app/main.py`
App entry point, lifespan startup/shutdown, router registration, static mount.

### `/app/models/`
Pydantic models: `room.py`, `queue_item.py`, `vote.py`, `watch_history.py`.

### `/app/services/`
Business logic: rooms, queue, voting, selection, history, external_api.

### `/app/routers/`
API endpoints: rooms, queue, voting, websocket, sse.

### `/static/`
Single-page UI (HTML/CSS/JS).

### `/tests/`
Async pytest suite with fixtures in `conftest.py`.

## Key Behaviors
- **Voting**: unique `(item_id, user_id)` index with upsert; vote counts denormalized on queue items.
- **Selection**: `weighted_random` uses `1 + max(0, vote_score) * 2`; `highest_votes` sorts by vote_score desc then added_at asc; `round_robin` favors users not picked recently
- **Queue duplicates**: prevented by case-insensitive title match and TMDB ID match.
- **Real-time**: WebSocket for presence/events, SSE for change streams.
- **History**: mark watched, store notes, per-user ratings (1-5).

## Data Model Highlights
- Rooms: name, code, members, settings, created_at.
- Members: user_id, name, avatar.
- Room settings: voting_duration_seconds, selection_mode, allow_revotes.
- Queue items: title, added_by, status, added_at, vote_score, upvotes, downvotes, metadata fields.
- Votes: item_id, user_id, vote, voted_at.
- Watch history: room_id, item_id, watched_at, ratings map, notes.

## Database and Indexes
- Collections: rooms, queue_items, votes, watch_history.
- Unique room code index on `rooms.code`.
- Compound queue index on `(room_id, status, vote_score)` plus `(room_id, title)`.
- Unique vote index on `(item_id, user_id)` to prevent duplicate votes.
- History indexes on `(room_id, watched_at)` and unique `item_id`.

## Real-time Events
- WebSocket endpoint: `/ws/{room_id}/{user_id}`.
- Server emits: `user_joined`, `user_left`, `presence`, `vote_update`, `queue_update`, `selection`, `voting_round_start`.
- Client messages handled: `vote`, `queue_add`, `selection`, `voting_round_start`, `get_presence`, `pong`.
- SSE endpoints: `/api/events/room/{room_id}`, `/api/events/votes/{room_id}`, `/api/events/queue/{room_id}`.

## Frontend Flow (static app)
- Landing screen with create/join modals in `static/index.html`.
- API calls and UI state live in `static/app.js`.
- WebSocket reconnects after disconnect with a 3 second delay.
- Queue rendering sorts by vote_score and attaches vote/remove handlers.
- History sidebar loads from `/api/votes/history/room/{room_id}`.

## Development Workflow
- Start MongoDB replica set via `docker-compose` (needed for change streams).
- Run API: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
- Tests: `pytest tests/ -v`.

## Testing Pointers
- Fixtures in `tests/conftest.py` set `watchqueue_test` database.
- Concurrency tests use `asyncio.gather` in `test_voting.py`.
- Selection fairness tests run many iterations in `test_selection.py`.
- TMDB client tests are mocked with `respx` in `test_external_api.py`.

## Config + Env
- Settings live in `app/config.py` and load from `.env`.
- Common env vars: `MONGODB_URL`, `MONGODB_DATABASE`, `TMDB_API_KEY`, `WS_HEARTBEAT_INTERVAL`.

## Docker Notes
- `docker-compose.yml` runs a 3-node MongoDB replica set plus optional mongo-express.
- The API container uses `Dockerfile` and exposes port 8000.
- `Dockerfile` copies only `app/`, so static assets are not included in the image.

## Runtime Notes
- Lifespan startup connects to MongoDB and creates indexes.
- Lifespan shutdown disconnects the MongoDB client.
- CORS is enabled with permissive defaults in `app/main.py`.
- Health check at `/health` pings the database.
- Queue enrichment runs in a FastAPI background task after adding items.

## Selection + History Extras
- `start_voting_round` returns a start_time and duration for client timers.
- Selection stats compute pick rates by user based on history entries.
- Marking watched sets queue status to `WATCHED` and creates a history document.

## API Surface (high level)
- Rooms: `/api/rooms` (create/update/join by code)
- Queue: `/api/queue` (add/remove/select/search)
- Votes: `/api/votes` (cast/remove/counts)
- Real-time: `/ws/{room_id}/{user_id}`, `/api/events/*` (SSE)

## Where to Find What
- Room codes: `app/services/rooms.py`
- Voting logic: `app/services/voting.py`
- Selection algorithms: `app/services/selection.py`
- Real-time: `app/routers/websocket.py`, `app/routers/sse.py`
- TMDB integration: `app/services/external_api.py`
- Frontend: `static/index.html`, `static/app.js`
