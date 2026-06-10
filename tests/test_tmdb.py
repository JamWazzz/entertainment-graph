"""Unit tests for server/tmdb.py — TMDB API calls and caching."""

from unittest.mock import MagicMock, call, patch

import pytest

import server.tmdb as tmdb


def _mock_response(data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ── _fetch ────────────────────────────────────────────────────────────────────

class TestFetch:
    def test_raises_when_api_key_missing(self):
        with patch.object(tmdb, '_API_KEY', ''):
            with pytest.raises(RuntimeError, match='TMDB_API_KEY'):
                tmdb._fetch('/movie/1')

    def test_cache_hit_returns_cached_data_without_http(self):
        cached = {'id': 1, 'title': 'Cached Result'}
        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=cached), \
             patch('server.tmdb.requests.get') as mock_get:
            result = tmdb._fetch('/movie/1')
        mock_get.assert_not_called()
        assert result == cached

    def test_cache_miss_calls_http(self):
        data = {'id': 1, 'title': 'Fresh'}
        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api'), \
             patch('server.tmdb.requests.get', return_value=_mock_response(data)) as mock_get:
            result = tmdb._fetch('/movie/1')
        mock_get.assert_called_once()
        assert result == data

    def test_cache_miss_stores_result(self):
        data = {'id': 1}
        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api') as mock_set, \
             patch('server.tmdb.requests.get', return_value=_mock_response(data)):
            tmdb._fetch('/movie/1')
        mock_set.assert_called_once()
        stored_data = mock_set.call_args[0][1]
        assert stored_data == data

    def test_correct_base_url_used(self):
        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api'), \
             patch('server.tmdb.requests.get', return_value=_mock_response({})) as mock_get:
            tmdb._fetch('/movie/550')
        url = mock_get.call_args[0][0]
        assert url == 'https://api.themoviedb.org/3/movie/550'

    def test_api_key_sent_in_request_params(self):
        with patch.object(tmdb, '_API_KEY', 'secret123'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api'), \
             patch('server.tmdb.requests.get', return_value=_mock_response({})) as mock_get:
            tmdb._fetch('/movie/1')
        params = mock_get.call_args[1]['params']
        assert params['api_key'] == 'secret123'

    def test_api_key_excluded_from_cache_key(self):
        """Same endpoint with different API keys must produce the same cache key."""
        keys_stored = []

        def capture(key, data):
            keys_stored.append(key)

        data = {}
        for api_key in ('key_a', 'key_b'):
            with patch.object(tmdb, '_API_KEY', api_key), \
                 patch('server.tmdb.cache.get_api', return_value=None), \
                 patch('server.tmdb.cache.set_api', side_effect=capture), \
                 patch('server.tmdb.requests.get', return_value=_mock_response(data)):
                tmdb._fetch('/movie/1')

        assert keys_stored[0] == keys_stored[1]

    def test_extra_params_included_in_cache_key(self):
        """Different query params must produce different cache keys."""
        keys_stored = []

        def capture(key, data):
            keys_stored.append(key)

        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api', side_effect=capture), \
             patch('server.tmdb.requests.get', return_value=_mock_response({})):
            tmdb._fetch('/search/movie', {'query': 'Inception'})

        with patch.object(tmdb, '_API_KEY', 'key'), \
             patch('server.tmdb.cache.get_api', return_value=None), \
             patch('server.tmdb.cache.set_api', side_effect=capture), \
             patch('server.tmdb.requests.get', return_value=_mock_response({})):
            tmdb._fetch('/search/movie', {'query': 'Fight Club'})

        assert keys_stored[0] != keys_stored[1]


# ── search functions ──────────────────────────────────────────────────────────

class TestSearchFunctions:
    """Each public search function should delegate to _fetch with the right args."""

    def _patch_fetch(self, return_value=None):
        return patch.object(tmdb, '_fetch', return_value=return_value or {})

    def test_search_multi_endpoint_and_params(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.search_multi('Inception')
        mock_fetch.assert_called_once_with(
            '/search/multi', {'query': 'Inception', 'include_adult': False}
        )

    def test_search_multi_returns_fetch_result(self):
        data = {'results': [{'id': 27205}]}
        with self._patch_fetch(data):
            result = tmdb.search_multi('Inception')
        assert result == data

    def test_search_movie_endpoint(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.search_movie('Fight Club')
        mock_fetch.assert_called_once_with(
            '/search/movie', {'query': 'Fight Club', 'include_adult': False}
        )

    def test_search_tv_endpoint(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.search_tv('Breaking Bad')
        mock_fetch.assert_called_once_with(
            '/search/tv', {'query': 'Breaking Bad', 'include_adult': False}
        )


# ── detail / credit functions ─────────────────────────────────────────────────

class TestDetailFunctions:
    def _patch_fetch(self):
        return patch.object(tmdb, '_fetch', return_value={})

    def test_get_movie_details(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_movie_details(550)
        mock_fetch.assert_called_once_with('/movie/550')

    def test_get_movie_credits(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_movie_credits(550)
        mock_fetch.assert_called_once_with('/movie/550/credits')

    def test_get_tv_details(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_tv_details(1396)
        mock_fetch.assert_called_once_with('/tv/1396')

    def test_get_tv_credits(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_tv_credits(1396)
        mock_fetch.assert_called_once_with('/tv/1396/credits')

    def test_get_person_details(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_person_details(819)
        mock_fetch.assert_called_once_with('/person/819')

    def test_get_person_combined_credits(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_person_combined_credits(819)
        mock_fetch.assert_called_once_with('/person/819/combined_credits')

    def test_get_company_movies(self):
        with self._patch_fetch() as mock_fetch:
            tmdb.get_company_movies(508)
        mock_fetch.assert_called_once_with(
            '/discover/movie',
            {'with_companies': 508, 'sort_by': 'popularity.desc', 'page': 1},
        )

    def test_detail_functions_return_fetch_result(self):
        fake = {'id': 550, 'title': 'Fight Club'}
        with patch.object(tmdb, '_fetch', return_value=fake):
            assert tmdb.get_movie_details(550) == fake
            assert tmdb.get_movie_credits(550) == fake
            assert tmdb.get_tv_details(1396) == fake
            assert tmdb.get_tv_credits(1396) == fake
            assert tmdb.get_person_details(819) == fake
            assert tmdb.get_person_combined_credits(819) == fake
            assert tmdb.get_company_movies(508) == fake
