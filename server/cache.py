import json
import time

from .database import get_db

API_TTL = 86_400      # 24 h for raw TMDB responses
GRAPH_TTL = 3_600     # 1 h for computed graphs


def _get(key: str, ttl: int):
    conn = get_db()
    row = conn.execute('SELECT data, ts FROM cache WHERE key = ?', (key,)).fetchone()
    conn.close()
    if row and (time.time() - row['ts']) < ttl:
        return json.loads(row['data'])
    return None


def _set(key: str, data):
    conn = get_db()
    conn.execute(
        'INSERT OR REPLACE INTO cache (key, data, ts) VALUES (?, ?, ?)',
        (key, json.dumps(data), int(time.time())),
    )
    conn.commit()
    conn.close()


def get_api(key: str):
    return _get(f'api:{key}', API_TTL)


def set_api(key: str, data):
    _set(f'api:{key}', data)


def get_graph(media_type: str, tmdb_id: int):
    return _get(f'graph:{media_type}:{tmdb_id}', GRAPH_TTL)


def set_graph(media_type: str, tmdb_id: int, data):
    _set(f'graph:{media_type}:{tmdb_id}', data)
