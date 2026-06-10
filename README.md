# Entertainment Graph Explorer

An interactive entertainment graph explorer that lets you search for any movie or TV show and visualizes its connections (cast, directors, writers and production companies) as an explorable force-directed graph. Data comes from the TMDB API.

The primary experience is the **web client**: an interactive D3.js graph where you can click nodes to expand connections and explore the network. The project also includes a CLI, a TUI, and a Tkinter GUI to demonstrate a multi-client architecture backed by a single Flask REST server.

---

## Prerequisites

- Python 3.10 or higher
- A free TMDB API key

---

## Setup

### 1. Get a TMDB API key

Create a free account at [themoviedb.org](https://www.themoviedb.org/) and generate a v3 API key under **Settings → API**.

### 2. Configure environment

```
copy .env.example .env
```

Open with notepad `.env` and paste your API key:

```
TMDB_API_KEY=your_key_here
```

### 3. Install dependencies

```
py -m pip install -r requirements.txt
```

---

## Run the server

```
py -m flask --app server.app:create_app run --debug
```

The server starts on `http://localhost:5000`. Keep it running while using any of the clients.

---

## Clients

### Web client (intended use)

Open `clients/web/index.html` directly in a browser. Search for a title, select a result, and click any person or company node to expand its connections.

### CLI

```
py clients/cli.py search "Breaking Bad"
py clients/cli.py graph tv 1396
py clients/cli.py expand person 17419
```

### TUI

```
py clients/tui.py
```

### GUI

```
py clients/gui.py
```
