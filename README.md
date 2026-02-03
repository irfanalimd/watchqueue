# WatchQueue - Decide What to Watch with Friends

A collaborative movie/show selection system built with FastAPI, MongoDB, and real-time updates. Stop arguing about what to watch and let the system decide fairly!

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Running Tests](#running-tests)
- [API Documentation](#api-documentation)
- [Configuration](#configuration)
- [Project Structure](#project-structure)

---

## Features

- **Room Management**: Create rooms with unique join codes for your friend group
- **Shared Queue**: Everyone can add movies/shows to a shared queue
- **Voting System**: Upvote or downvote items with atomic, concurrent-safe operations
- **Fair Selection**: Three algorithms to pick what to watch:
  - **Weighted Random**: Higher voted items have better odds
  - **Highest Votes**: Simple majority wins
  - **Round Robin**: Rotates through who added items
- **Real-time Updates**: WebSocket and SSE for live voting updates
- **Watch History**: Track what you've watched with ratings and notes
- **TMDB Integration**: Automatic movie metadata (posters, runtime, genres)
- **Web Interface**: Beautiful dark-themed UI that works on any device

---

## Sharing with Friends

Once the app is running, you have several options to share it with friends:

### Option 1: Same WiFi Network (Easiest)

If everyone is on the same WiFi network (e.g., at your house):

```bash
# Find your local IP address
# On Linux/WSL:
hostname -I | awk '{print $1}'

# On macOS:
ipconfig getifaddr en0
```

Then share: `http://YOUR_IP:8000` (e.g., `http://192.168.1.100:8000`)

### Option 2: Using ngrok (Over the Internet)

For friends not on your network, use [ngrok](https://ngrok.com) to create a public URL:

```bash
# Install ngrok (one-time)
# Download from https://ngrok.com/download or:
# snap install ngrok  # Linux
# brew install ngrok  # macOS

# Start the tunnel (while your app is running)
ngrok http 8000
```

ngrok will give you a URL like `https://abc123.ngrok.io` - share this with friends!

### Option 3: Using Tailscale (Secure VPN)

For a more permanent solution, use [Tailscale](https://tailscale.com):

1. Install Tailscale on your machine and your friends' devices
2. Everyone joins the same Tailscale network
3. Share your Tailscale IP: `http://YOUR_TAILSCALE_IP:8000`

### How Friends Join

1. Open the shared URL in a browser
2. Click "Join Room"
3. Enter the room code (shown to the room creator)
4. Pick a name and avatar
5. Start adding movies and voting!

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENTS                                     │
│   [Web App]              [Mobile PWA]           [TV App]           │
└──────────────────────────┬──────────────────────────────────────────┘
                           │ HTTP + WebSocket + SSE
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      API SERVER (FastAPI)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Rooms      │  │   Queue      │  │   Voting     │              │
│  │   Service    │  │   Service    │  │   Service    │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │  Selection   │  │   History    │  │   TMDB       │              │
│  │  Algorithm   │  │   Tracker    │  │   Client     │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MONGODB REPLICA SET                              │
│   [rooms]    [queue_items]    [votes]    [watch_history]           │
│         Change Streams → Live voting updates to all clients         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose** (for MongoDB replica set)
- **TMDB API Key** (optional, for movie metadata)

---

## Quick Start

### 1. Clone and Navigate

```bash
cd /home/irfan/projects/distributed_systems_project
```

### 2. Start MongoDB Replica Set

```bash
# Start the 3-node MongoDB replica set
docker-compose up -d mongo1 mongo2 mongo3

# Wait for replica set initialization (~10-15 seconds)
sleep 15

# Verify replica set is ready
docker exec watchqueue-mongo1 mongosh --eval "rs.status().ok"
# Should output: 1
```

### 3. Install Python Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env to add your TMDB API key (optional)
# Get one at: https://www.themoviedb.org/settings/api
```

### 5. Run the API

```bash
# Development mode with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or production mode
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 6. Access the API

- **API Base URL**: http://localhost:8000
- **Interactive Docs (Swagger)**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health

---

## Development Setup

### Using Docker Compose (Full Stack)

```bash
# Start everything (MongoDB + API)
docker-compose up -d

# View logs
docker-compose logs -f api

# Stop everything
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v
```

### MongoDB Admin Interface

```bash
# Start MongoDB Express (optional web admin)
docker-compose up -d mongo-express

# Access at http://localhost:8081
# Username: admin
# Password: admin123
```

### Manual MongoDB Setup (Without Docker)

If you prefer to run MongoDB locally:

```bash
# Start 3 MongoDB instances
mongod --replSet rs0 --port 27017 --dbpath ./data/mongo1 --bind_ip_all &
mongod --replSet rs0 --port 27018 --dbpath ./data/mongo2 --bind_ip_all &
mongod --replSet rs0 --port 27019 --dbpath ./data/mongo3 --bind_ip_all &

# Initialize replica set
mongosh --port 27017 --eval '
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "localhost:27017" },
    { _id: 1, host: "localhost:27018" },
    { _id: 2, host: "localhost:27019" }
  ]
})
'
```

---

## Running Tests

### Prerequisites for Testing

```bash
# Ensure MongoDB replica set is running
docker-compose up -d mongo1 mongo2 mongo3

# Install test dependencies
pip install -r requirements.txt
```

### Run All Tests

```bash
# Run all tests with verbose output
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=app --cov-report=html

# Open coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### Run Specific Test Files

```bash
# Room tests
pytest tests/test_rooms.py -v

# Queue tests (including concurrent duplicate prevention)
pytest tests/test_queue.py -v

# Voting tests (atomic operations, concurrent voting)
pytest tests/test_voting.py -v

# Selection algorithm tests (fairness verification)
pytest tests/test_selection.py -v

# Watch history tests
pytest tests/test_history.py -v

# External API (TMDB) tests
pytest tests/test_external_api.py -v
```

### Run Specific Test

```bash
# Run a single test by name
pytest tests/test_voting.py::TestVotingService::test_concurrent_votes_atomic -v
```

### Test Environment Variables

```bash
# Use a different MongoDB for testing
TEST_MONGODB_URL="mongodb://localhost:27017/?replicaSet=rs0" pytest tests/ -v
```

---

## API Documentation

### Core Endpoints

#### Rooms

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/rooms` | Create a new room |
| GET | `/api/rooms/{room_id}` | Get room by ID |
| GET | `/api/rooms/code/{code}` | Get room by join code |
| PATCH | `/api/rooms/{room_id}` | Update room settings |
| DELETE | `/api/rooms/{room_id}` | Delete room |
| POST | `/api/rooms/{code}/join` | Join room with code |
| POST | `/api/rooms/{room_id}/members` | Add member |
| DELETE | `/api/rooms/{room_id}/members/{user_id}` | Remove member |

#### Queue

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/queue` | Add item to queue |
| GET | `/api/queue/{item_id}` | Get queue item |
| GET | `/api/queue/room/{room_id}` | Get room's queue |
| PATCH | `/api/queue/{item_id}` | Update item |
| DELETE | `/api/queue/{item_id}` | Remove from queue |
| POST | `/api/queue/{item_id}/enrich` | Fetch TMDB metadata |
| POST | `/api/queue/room/{room_id}/select` | Select next to watch |
| POST | `/api/queue/{item_id}/watch` | Mark as watching |

#### Voting

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/votes` | Cast or update vote |
| GET | `/api/votes/{item_id}/{user_id}` | Get user's vote |
| DELETE | `/api/votes/{item_id}/{user_id}` | Remove vote |
| GET | `/api/votes/item/{item_id}` | Get all votes for item |
| GET | `/api/votes/item/{item_id}/counts` | Get vote counts |

#### Real-time

| Method | Endpoint | Description |
|--------|----------|-------------|
| WebSocket | `/ws/{room_id}/{user_id}` | Real-time room updates |
| GET | `/api/events/room/{room_id}` | SSE stream for all changes |
| GET | `/api/events/votes/{room_id}` | SSE stream for vote changes |
| GET | `/api/events/queue/{room_id}` | SSE stream for queue changes |

### Example Usage

#### Create a Room

```bash
curl -X POST http://localhost:8000/api/rooms \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Friday Night Movies",
    "members": [
      {"user_id": "alice", "name": "Alice", "avatar": "🦊"},
      {"user_id": "bob", "name": "Bob", "avatar": "🐻"}
    ],
    "settings": {
      "voting_duration_seconds": 60,
      "selection_mode": "weighted_random",
      "allow_revotes": true
    }
  }'
```

#### Add Movie to Queue

```bash
curl -X POST http://localhost:8000/api/queue \
  -H "Content-Type: application/json" \
  -d '{
    "room_id": "YOUR_ROOM_ID",
    "title": "Inception",
    "added_by": "alice"
  }'
```

#### Cast a Vote

```bash
curl -X POST http://localhost:8000/api/votes \
  -H "Content-Type: application/json" \
  -d '{
    "item_id": "YOUR_ITEM_ID",
    "user_id": "bob",
    "vote": "up"
  }'
```

#### Select Next Movie

```bash
curl -X POST "http://localhost:8000/api/queue/room/YOUR_ROOM_ID/select?mode=weighted_random"
```

#### WebSocket Connection (JavaScript)

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/ROOM_ID/USER_ID');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);

  switch(data.type) {
    case 'vote_update':
      // Handle vote update
      break;
    case 'queue_update':
      // Handle queue change
      break;
    case 'selection':
      // Movie was selected!
      break;
    case 'presence':
      // User list updated
      break;
  }
};

// Send a vote notification
ws.send(JSON.stringify({
  type: 'vote',
  item_id: 'ITEM_ID',
  vote: 'up'
}));
```

#### SSE Connection (JavaScript)

```javascript
const eventSource = new EventSource('http://localhost:8000/api/events/room/ROOM_ID');

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
};
```

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URL` | MongoDB connection string | `mongodb://localhost:27017,.../?replicaSet=rs0` |
| `MONGODB_DATABASE` | Database name | `watchqueue` |
| `TMDB_API_KEY` | TMDB API key for metadata | `` (optional) |
| `DEBUG` | Enable debug mode | `false` |
| `WS_HEARTBEAT_INTERVAL` | WebSocket heartbeat (seconds) | `30` |

### Selection Modes

| Mode | Description |
|------|-------------|
| `weighted_random` | Higher voted items have better odds, but all items have a chance |
| `highest_votes` | Simply picks the item with the most votes |
| `round_robin` | Rotates through users who added items to ensure fairness |

---

## Project Structure

```
distributed_systems_project/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Pydantic settings configuration
│   ├── database.py          # MongoDB connection and indexes
│   ├── models/              # Pydantic data models
│   │   ├── __init__.py
│   │   ├── room.py          # Room, Member, RoomSettings
│   │   ├── queue_item.py    # QueueItem, QueueItemStatus
│   │   ├── vote.py          # Vote, VoteType
│   │   └── watch_history.py # WatchHistory, RatingUpdate
│   ├── services/            # Business logic layer
│   │   ├── __init__.py
│   │   ├── rooms.py         # Room CRUD operations
│   │   ├── queue.py         # Queue management
│   │   ├── voting.py        # Atomic voting operations
│   │   ├── selection.py     # Fair selection algorithms
│   │   ├── history.py       # Watch history tracking
│   │   └── external_api.py  # TMDB client
│   ├── routers/             # API route handlers
│   │   ├── __init__.py
│   │   ├── rooms.py         # /api/rooms endpoints
│   │   ├── queue.py         # /api/queue endpoints
│   │   ├── voting.py        # /api/votes endpoints
│   │   ├── websocket.py     # WebSocket endpoint
│   │   └── sse.py           # Server-Sent Events
│   └── utils/
│       ├── __init__.py
│       └── helpers.py       # Utility functions
├── tests/                   # Pytest test suite
│   ├── __init__.py
│   ├── conftest.py          # Test fixtures
│   ├── test_rooms.py
│   ├── test_queue.py
│   ├── test_voting.py
│   ├── test_selection.py
│   ├── test_history.py
│   └── test_external_api.py
├── docker-compose.yml       # Docker services configuration
├── Dockerfile               # API container definition
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Project metadata
├── .env.example             # Example environment variables
├── .gitignore
└── README.md
```

---

## Developer Notes (from code)

### Selection Algorithms
- **weighted_random**: weight = `1 + max(0, vote_score) * 2` per queued item
- **highest_votes**: sorts by `vote_score` desc, then `added_at` asc
- **round_robin**: prioritizes users who have not had recent picks (uses watch history)

### Voting + Counts
- Votes use a **unique (item_id, user_id)** index and `find_one_and_update` with upsert
- Queue items store **denormalized** `upvotes`, `downvotes`, and `vote_score`
- Vote counts are recalculated via aggregation pipeline after vote changes

### Real-time Updates
- **WebSocket** (`/ws/{room_id}/{user_id}`) for presence and in-room events; handles client messages `vote`, `queue_add`, `selection`, `voting_round_start`, `get_presence`, `pong`; broadcasts `user_joined`, `user_left`, `vote_update`, `queue_update`, `selection`, `voting_round_start`, `presence`
- **SSE** streams use MongoDB change streams (requires replica set)

### Queue + TMDB Enrichment
- Duplicate queue items prevented by case-insensitive title match and TMDB ID match
- Background enrichment fetches TMDB metadata and streaming availability placeholders
- TMDB genre map is cached at the class level (`TMDBClient._genre_cache`)

### History + Ratings
- Marking an item as watched creates a history entry and sets queue status to `WATCHED`
- Ratings are stored per user on the history document (`ratings.{user_id}`), range 1-5

---

## Troubleshooting

### MongoDB Replica Set Not Initializing

```bash
# Check replica set status
docker exec watchqueue-mongo1 mongosh --eval "rs.status()"

# Manually initialize if needed
docker exec watchqueue-mongo1 mongosh --eval '
rs.initiate({
  _id: "rs0",
  members: [
    { _id: 0, host: "mongo1:27017" },
    { _id: 1, host: "mongo2:27018" },
    { _id: 2, host: "mongo3:27019" }
  ]
})
'
```

### Connection Refused Errors

```bash
# Ensure MongoDB is running
docker-compose ps

# Check MongoDB logs
docker-compose logs mongo1

# Verify ports are accessible
nc -zv localhost 27017
```

### Tests Failing

```bash
# Ensure test database is clean
docker exec watchqueue-mongo1 mongosh watchqueue_test --eval "db.dropDatabase()"

# Run tests with more verbose output
pytest tests/ -v --tb=long
```

### WebSocket Connection Issues

- Ensure you're using `ws://` not `http://`
- Check that the room_id and user_id are valid
- Verify no firewall is blocking WebSocket connections

---

## License

MIT License - feel free to use this for your movie nights!
