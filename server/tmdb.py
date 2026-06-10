import hashlib
import os

import requests
from dotenv import load_dotenv

from . import cache

load_dotenv()

_API_KEY = os.getenv('TMDB_API_KEY', '')
_BASE = 'https://api.themoviedb.org/3'
IMAGE_BASE = 'https://image.tmdb.org/t/p/w200'


def _fetch(endpoint: str, params: dict | None = None) -> dict:
    if not _API_KEY:
        raise RuntimeError('TMDB_API_KEY is not set. Copy .env.example to .env and add your key.')

    params = dict(params or {})
    params['api_key'] = _API_KEY

    # Cache key excludes the api_key value itself
    raw_key = endpoint + str(sorted((k, v) for k, v in params.items() if k != 'api_key'))
    cache_key = hashlib.sha1(raw_key.encode()).hexdigest()

    hit = cache.get_api(cache_key)
    if hit is not None:
        return hit

    resp = requests.get(f'{_BASE}{endpoint}', params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    cache.set_api(cache_key, data)
    return data


def search_multi(query: str) -> dict:
    return _fetch('/search/multi', {'query': query, 'include_adult': False})


def search_movie(query: str) -> dict:
    return _fetch('/search/movie', {'query': query, 'include_adult': False})


def search_tv(query: str) -> dict:
    return _fetch('/search/tv', {'query': query, 'include_adult': False})


def get_movie_details(tmdb_id: int) -> dict:
    return _fetch(f'/movie/{tmdb_id}')


def get_movie_credits(tmdb_id: int) -> dict:
    return _fetch(f'/movie/{tmdb_id}/credits')


def get_tv_details(tmdb_id: int) -> dict:
    return _fetch(f'/tv/{tmdb_id}')


def get_tv_credits(tmdb_id: int) -> dict:
    return _fetch(f'/tv/{tmdb_id}/credits')


def get_person_details(person_id: int) -> dict:
    return _fetch(f'/person/{person_id}')


def get_person_combined_credits(person_id: int) -> dict:
    return _fetch(f'/person/{person_id}/combined_credits')


def get_company_movies(company_id: int) -> dict:
    return _fetch('/discover/movie', {
        'with_companies': company_id,
        'sort_by': 'popularity.desc',
        'page': 1,
    })
