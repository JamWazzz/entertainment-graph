# Entertainment Graph Explorer

Interactive movie and TV show graph explorer powered by the TMDB API. Search for a title and explore its cast, directors, writers, and production companies as a navigable graph.

## Setup

### 1. Get a TMDB API key

Create a free account at [themoviedb.org](https://www.themoviedb.org/) and generate a v3 API key under **Settings → API**.

### 2. Install dependencies

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env and paste your TMDB API key
```

### 4. Run the server

```bash
flask --app server.app:create_app run --debug
```

The server starts on `http://localhost:5000`.

---

## API Reference

### `GET /health`
Returns `{"status": "ok"}`.

### `GET /api/search`
Search for movies and TV shows.

| Param | Values | Default |
|-------|--------|---------|
| `q`   | search string | *(required)* |
| `type` | `movie` \| `tv` \| `multi` | `multi` |

**Response**
```json
{
  "results": [
    {
      "tmdb_id": 550,
      "media_type": "movie",
      "title": "Fight Club",
      "overview": "...",
      "poster_path": "/path.jpg",
      "vote_average": 8.4,
      "release_date": "1999-10-15"
    }
  ],
  "total": 1
}
```

### `GET /api/graph/<media_type>/<tmdb_id>`
Build the connection graph for a title.

- `media_type`: `movie` or `tv`
- `tmdb_id`: TMDB numeric ID

**Response** — nodes and edges:
```json
{
  "center": "movie_550",
  "nodes": [
    { "id": "movie_550", "type": "movie", "label": "Fight Club", "data": { ... } },
    { "id": "person_819", "type": "person", "label": "Edward Norton", "data": { ... } },
    { "id": "company_508", "type": "company", "label": "Regency Enterprises", "data": { ... } }
  ],
  "edges": [
    { "id": "...", "source": "person_819", "target": "movie_550", "relation": "acted_in", "data": { "character": "The Narrator" } }
  ]
}
```

**Node types:** `movie`, `tv`, `person`, `company`  
**Edge relations:** `acted_in`, `directed`, `wrote`, `created`, `produced_by`

### `GET /api/expand/<node_type>/<node_id>`
Expand a node to reveal its own connections.

- `node_type`: `person` or `company`
- `node_id`: TMDB numeric ID

Returns the same `{ center, nodes, edges }` shape, with new nodes/edges to merge into the existing graph.

---

## Project Structure

```
server/
  app.py        Flask app factory and route definitions
  tmdb.py       TMDB API calls (all HTTP requests live here)
  graph.py      Node/edge builders for movies, TV shows, and expansions
  database.py   SQLite connection and schema initialization
  cache.py      Read/write cache backed by SQLite
```

SQLite database (`entertainment.db`) is created automatically at the project root on first run. All TMDB responses are cached for 24 hours; computed graphs are cached for 1 hour.
