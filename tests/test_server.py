"""Integration tests for the Flask server routes.

Uses a real Flask test client backed by a temporary SQLite database.
TMDB calls are avoided by mocking at the graph/search function level.
"""

from unittest.mock import patch

import pytest

# ── shared mock payloads ──────────────────────────────────────────────────────

FAKE_MOVIE_GRAPH = {
    'center': 'movie_550',
    'nodes': [
        {'id': 'movie_550',  'type': 'movie',  'label': 'Fight Club',    'data': {}},
        {'id': 'person_819', 'type': 'person', 'label': 'Edward Norton', 'data': {'tmdb_id': 819}},
        {'id': 'company_508','type': 'company','label': 'Regency',        'data': {'tmdb_id': 508}},
    ],
    'edges': [
        {'id': 'person_819__movie_550__acted_in',
         'source': 'person_819', 'target': 'movie_550',
         'relation': 'acted_in', 'data': {'character': 'The Narrator'}},
        {'id': 'movie_550__company_508__produced_by',
         'source': 'movie_550', 'target': 'company_508',
         'relation': 'produced_by', 'data': {}},
    ],
}

FAKE_TV_GRAPH = {
    'center': 'tv_1396',
    'nodes': [
        {'id': 'tv_1396',     'type': 'tv',     'label': 'Breaking Bad',  'data': {}},
        {'id': 'person_66633','type': 'person', 'label': 'Vince Gilligan','data': {'tmdb_id': 66633}},
    ],
    'edges': [
        {'id': 'person_66633__tv_1396__created',
         'source': 'person_66633', 'target': 'tv_1396',
         'relation': 'created', 'data': {}},
    ],
}

FAKE_PERSON_EXPAND = {
    'center': 'person_819',
    'nodes': [
        {'id': 'person_819', 'type': 'person', 'label': 'Edward Norton', 'data': {'tmdb_id': 819}},
        {'id': 'movie_550',  'type': 'movie',  'label': 'Fight Club',    'data': {}},
    ],
    'edges': [
        {'id': 'person_819__movie_550__acted_in',
         'source': 'person_819', 'target': 'movie_550',
         'relation': 'acted_in', 'data': {}},
    ],
}

FAKE_COMPANY_EXPAND = {
    'center': 'company_508',
    'nodes': [
        {'id': 'company_508', 'type': 'company', 'label': 'Regency', 'data': {'tmdb_id': 508}},
        {'id': 'movie_550',   'type': 'movie',   'label': 'Fight Club', 'data': {}},
    ],
    'edges': [
        {'id': 'movie_550__company_508__produced_by',
         'source': 'movie_550', 'target': 'company_508',
         'relation': 'produced_by', 'data': {}},
    ],
}

FAKE_SEARCH_RESPONSE = {
    'results': [
        {'id': 550, 'media_type': 'movie', 'title': 'Fight Club',
         'overview': 'Underground fighting.', 'poster_path': '/abc.jpg',
         'vote_average': 8.4, 'release_date': '1999-10-15'},
        {'id': 1396, 'media_type': 'tv', 'name': 'Breaking Bad',
         'overview': 'Chemistry teacher.', 'poster_path': '/bb.jpg',
         'vote_average': 8.9, 'first_air_date': '2008-01-20'},
    ]
}


# ── fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client wired to a fresh temporary SQLite database."""
    db_file = str(tmp_path / 'test_entertainment.db')
    monkeypatch.setattr('server.database.DB_PATH', db_file)

    from server.app import create_app
    app = create_app()
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


# ── /health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_status_200(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200

    def test_body_is_ok(self, client):
        resp = client.get('/health')
        assert resp.get_json() == {'status': 'ok'}

    def test_content_type_json(self, client):
        resp = client.get('/health')
        assert 'application/json' in resp.content_type


# ── /api/search ───────────────────────────────────────────────────────────────

class TestSearch:
    def test_missing_q_returns_400(self, client):
        resp = client.get('/api/search')
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_invalid_type_returns_400(self, client):
        resp = client.get('/api/search?q=test&type=cartoon')
        assert resp.status_code == 400

    def test_multi_search_returns_results(self, client):
        with patch('server.app.search_multi', return_value=FAKE_SEARCH_RESPONSE):
            resp = client.get('/api/search?q=Fight+Club')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'results' in data
        assert 'total' in data

    def test_multi_search_calls_search_multi(self, client):
        with patch('server.app.search_multi', return_value={'results': []}) as mock_fn:
            client.get('/api/search?q=Inception')
        mock_fn.assert_called_once_with('Inception')

    def test_movie_type_calls_search_movie(self, client):
        with patch('server.app.search_movie', return_value={'results': []}) as mock_fn:
            client.get('/api/search?q=Fight+Club&type=movie')
        mock_fn.assert_called_once_with('Fight Club')

    def test_tv_type_calls_search_tv(self, client):
        with patch('server.app.search_tv', return_value={'results': []}) as mock_fn:
            client.get('/api/search?q=Breaking+Bad&type=tv')
        mock_fn.assert_called_once_with('Breaking Bad')

    def test_person_media_type_excluded_from_results(self, client):
        """Items with media_type 'person' must be filtered out of the response."""
        raw = {
            'results': [
                {'id': 1, 'media_type': 'person', 'name': 'An Actor'},
                {'id': 2, 'media_type': 'movie', 'title': 'A Film',
                 'overview': '', 'poster_path': None,
                 'vote_average': 7.0, 'release_date': '2020-01-01'},
            ]
        }
        with patch('server.app.search_multi', return_value=raw):
            resp = client.get('/api/search?q=test')
        data = resp.get_json()
        assert all(r['media_type'] in ('movie', 'tv') for r in data['results'])
        assert len(data['results']) == 1

    def test_result_fields_present(self, client):
        with patch('server.app.search_multi', return_value=FAKE_SEARCH_RESPONSE):
            resp = client.get('/api/search?q=test')
        result = resp.get_json()['results'][0]
        for field in ('tmdb_id', 'media_type', 'title', 'overview', 'poster_path',
                      'vote_average', 'release_date'):
            assert field in result


# ── /api/graph ────────────────────────────────────────────────────────────────

class TestGraph:
    def test_invalid_media_type_returns_400(self, client):
        resp = client.get('/api/graph/series/1396')
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_movie_graph_200(self, client):
        with patch('server.graph.build_movie_graph', return_value=FAKE_MOVIE_GRAPH):
            resp = client.get('/api/graph/movie/550')
        assert resp.status_code == 200

    def test_movie_graph_calls_builder_with_id(self, client):
        with patch('server.graph.build_movie_graph', return_value=FAKE_MOVIE_GRAPH) as mock_fn:
            client.get('/api/graph/movie/550')
        mock_fn.assert_called_once_with(550)

    def test_movie_graph_response_structure(self, client):
        with patch('server.graph.build_movie_graph', return_value=FAKE_MOVIE_GRAPH):
            resp = client.get('/api/graph/movie/550')
        data = resp.get_json()
        assert data['center'] == 'movie_550'
        assert len(data['nodes']) == 3
        assert len(data['edges']) == 2

    def test_tv_graph_200(self, client):
        with patch('server.graph.build_tv_graph', return_value=FAKE_TV_GRAPH):
            resp = client.get('/api/graph/tv/1396')
        assert resp.status_code == 200

    def test_tv_graph_calls_builder_with_id(self, client):
        with patch('server.graph.build_tv_graph', return_value=FAKE_TV_GRAPH) as mock_fn:
            client.get('/api/graph/tv/1396')
        mock_fn.assert_called_once_with(1396)

    def test_graph_result_is_cached_on_second_call(self, client):
        """The graph builder must be called exactly once; subsequent calls use cache."""
        with patch('server.graph.build_movie_graph', return_value=FAKE_MOVIE_GRAPH) as mock_fn:
            client.get('/api/graph/movie/550')
            client.get('/api/graph/movie/550')
        mock_fn.assert_called_once()

    def test_cached_graph_identical_to_original(self, client):
        with patch('server.graph.build_movie_graph', return_value=FAKE_MOVIE_GRAPH):
            r1 = client.get('/api/graph/movie/550').get_json()
            r2 = client.get('/api/graph/movie/550').get_json()
        assert r1 == r2

    def test_different_ids_not_confused_in_cache(self, client):
        with patch('server.graph.build_movie_graph', side_effect=[FAKE_MOVIE_GRAPH, FAKE_TV_GRAPH]):
            r1 = client.get('/api/graph/movie/550').get_json()
            r2 = client.get('/api/graph/movie/999').get_json()
        assert r1['center'] != r2['center']


# ── /api/expand ───────────────────────────────────────────────────────────────

class TestExpand:
    def test_invalid_node_type_returns_400(self, client):
        resp = client.get('/api/expand/movie/550')
        assert resp.status_code == 400
        assert 'error' in resp.get_json()

    def test_expand_person_200(self, client):
        with patch('server.graph.expand_person', return_value=FAKE_PERSON_EXPAND):
            resp = client.get('/api/expand/person/819')
        assert resp.status_code == 200

    def test_expand_person_calls_function_with_id(self, client):
        with patch('server.graph.expand_person', return_value=FAKE_PERSON_EXPAND) as mock_fn:
            client.get('/api/expand/person/819')
        mock_fn.assert_called_once_with(819)

    def test_expand_person_response_structure(self, client):
        with patch('server.graph.expand_person', return_value=FAKE_PERSON_EXPAND):
            resp = client.get('/api/expand/person/819')
        data = resp.get_json()
        assert data['center'] == 'person_819'
        assert 'nodes' in data
        assert 'edges' in data

    def test_expand_company_200(self, client):
        with patch('server.graph.expand_company', return_value=FAKE_COMPANY_EXPAND):
            resp = client.get('/api/expand/company/508')
        assert resp.status_code == 200

    def test_expand_company_calls_function_with_id(self, client):
        with patch('server.graph.expand_company', return_value=FAKE_COMPANY_EXPAND) as mock_fn:
            client.get('/api/expand/company/508')
        mock_fn.assert_called_once_with(508)

    def test_expand_company_response_structure(self, client):
        with patch('server.graph.expand_company', return_value=FAKE_COMPANY_EXPAND):
            resp = client.get('/api/expand/company/508')
        data = resp.get_json()
        assert data['center'] == 'company_508'
        assert len(data['nodes']) == 2
        assert len(data['edges']) == 1
