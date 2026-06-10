"""Unit tests for server/graph.py — node/edge building logic."""

from unittest.mock import patch

import pytest

from server.graph import (
    _GraphBuilder,
    _eid,
    _nid,
    build_movie_graph,
    build_tv_graph,
    expand_company,
    expand_person,
)

# ── shared fixture data ───────────────────────────────────────────────────────

MOVIE_DETAILS = {
    'title': 'Fight Club',
    'overview': 'A man meets Tyler Durden.',
    'release_date': '1999-10-15',
    'poster_path': '/abc.jpg',
    'vote_average': 8.4,
    'genres': [{'name': 'Drama'}, {'name': 'Thriller'}],
    'production_companies': [
        {'id': 508, 'name': 'Regency Enterprises', 'logo_path': None, 'origin_country': 'US'}
    ],
}

MOVIE_CREDITS = {
    'cast': [
        {'id': 819, 'name': 'Edward Norton', 'character': 'The Narrator',
         'profile_path': None, 'order': 0},
        {'id': 287, 'name': 'Brad Pitt', 'character': 'Tyler Durden',
         'profile_path': None, 'order': 1},
    ],
    'crew': [
        {'id': 7467, 'name': 'David Fincher', 'job': 'Director',
         'department': 'Directing', 'profile_path': None},
        {'id': 1111, 'name': 'Jim Uhls', 'job': 'Screenplay',
         'department': 'Writing', 'profile_path': None},
    ],
}

TV_DETAILS = {
    'name': 'Breaking Bad',
    'overview': 'A chemistry teacher turns drug lord.',
    'first_air_date': '2008-01-20',
    'poster_path': '/bb.jpg',
    'vote_average': 8.9,
    'genres': [{'name': 'Crime'}, {'name': 'Drama'}],
    'number_of_seasons': 5,
    'created_by': [
        {'id': 66633, 'name': 'Vince Gilligan', 'profile_path': None}
    ],
    'production_companies': [
        {'id': 2575, 'name': 'Gran Via Productions', 'logo_path': None, 'origin_country': 'US'}
    ],
}

TV_CREDITS = {
    'cast': [
        {'id': 17419, 'name': 'Bryan Cranston', 'character': 'Walter White',
         'profile_path': None, 'order': 0},
    ],
    'crew': [
        {'id': 22222, 'name': 'Michelle MacLaren', 'job': 'Executive Producer',
         'department': 'Production', 'profile_path': None},
    ],
}

PERSON_DETAILS = {
    'name': 'Bryan Cranston',
    'profile_path': '/bc.jpg',
    'biography': 'An acclaimed actor.',
    'birthday': '1956-03-07',
    'known_for_department': 'Acting',
}

PERSON_CREDITS = {
    'cast': [
        {'id': 1396, 'name': 'Breaking Bad', 'media_type': 'tv',
         'character': 'Walter White', 'popularity': 100.0,
         'poster_path': None, 'vote_average': 8.9},
        {'id': 550, 'title': 'Fight Club', 'media_type': 'movie',
         'character': 'Bob', 'popularity': 50.0,
         'poster_path': None, 'vote_average': 8.4},
    ],
}

COMPANY_MOVIES = {
    'results': [
        {'id': 550, 'title': 'Fight Club', 'poster_path': None,
         'vote_average': 8.4, 'release_date': '1999-10-15'},
        {'id': 807, 'title': 'Se7en', 'poster_path': None,
         'vote_average': 8.6, 'release_date': '1995-09-22'},
    ]
}


# ── helper functions ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_nid_combines_type_and_id(self):
        assert _nid('movie', 550) == 'movie_550'
        assert _nid('person', 819) == 'person_819'
        assert _nid('company', 508) == 'company_508'

    def test_eid_combines_src_dst_relation(self):
        assert _eid('person_1', 'movie_1', 'acted_in') == 'person_1__movie_1__acted_in'

    def test_eid_different_relations_produce_different_ids(self):
        e1 = _eid('a', 'b', 'directed')
        e2 = _eid('a', 'b', 'wrote')
        assert e1 != e2


# ── _GraphBuilder ─────────────────────────────────────────────────────────────

class TestGraphBuilder:
    def test_add_node_appends_to_nodes(self):
        g = _GraphBuilder()
        g.add_node('movie_1', 'movie', 'Test Movie', {'tmdb_id': 1})
        assert len(g.nodes) == 1
        n = g.nodes[0]
        assert n['id'] == 'movie_1'
        assert n['type'] == 'movie'
        assert n['label'] == 'Test Movie'
        assert n['data'] == {'tmdb_id': 1}

    def test_add_node_deduplicates_by_id(self):
        g = _GraphBuilder()
        g.add_node('movie_1', 'movie', 'A', {})
        g.add_node('movie_1', 'movie', 'A', {})
        assert len(g.nodes) == 1

    def test_different_node_ids_both_added(self):
        g = _GraphBuilder()
        g.add_node('movie_1', 'movie', 'A', {})
        g.add_node('movie_2', 'movie', 'B', {})
        assert len(g.nodes) == 2

    def test_add_edge_appends_to_edges(self):
        g = _GraphBuilder()
        g.add_edge('person_1', 'movie_1', 'acted_in', {'character': 'Hero'})
        assert len(g.edges) == 1
        e = g.edges[0]
        assert e['source'] == 'person_1'
        assert e['target'] == 'movie_1'
        assert e['relation'] == 'acted_in'
        assert e['data'] == {'character': 'Hero'}

    def test_add_edge_default_data_is_empty_dict(self):
        g = _GraphBuilder()
        g.add_edge('a', 'b', 'directed')
        assert g.edges[0]['data'] == {}

    def test_add_edge_deduplicates_same_src_dst_relation(self):
        g = _GraphBuilder()
        g.add_edge('person_1', 'movie_1', 'acted_in')
        g.add_edge('person_1', 'movie_1', 'acted_in')
        assert len(g.edges) == 1

    def test_same_src_dst_different_relations_not_deduplicated(self):
        g = _GraphBuilder()
        g.add_edge('person_1', 'movie_1', 'directed')
        g.add_edge('person_1', 'movie_1', 'wrote')
        assert len(g.edges) == 2

    def test_to_dict_returns_correct_structure(self):
        g = _GraphBuilder()
        g.add_node('movie_1', 'movie', 'Test', {})
        g.add_edge('person_1', 'movie_1', 'acted_in')
        result = g.to_dict('movie_1')
        assert result['center'] == 'movie_1'
        assert result['nodes'] is g.nodes
        assert result['edges'] is g.edges


# ── build_movie_graph ─────────────────────────────────────────────────────────

class TestBuildMovieGraph:
    def _build(self, tmdb_id=550):
        with patch('server.tmdb.get_movie_details', return_value=MOVIE_DETAILS), \
             patch('server.tmdb.get_movie_credits', return_value=MOVIE_CREDITS):
            return build_movie_graph(tmdb_id)

    def test_center_node_id(self):
        result = self._build(550)
        assert result['center'] == 'movie_550'

    def test_movie_node_present_with_correct_type(self):
        result = self._build()
        movie = next(n for n in result['nodes'] if n['id'] == 'movie_550')
        assert movie['type'] == 'movie'
        assert movie['label'] == 'Fight Club'

    def test_cast_nodes_and_acted_in_edges(self):
        result = self._build()
        ids = {n['id'] for n in result['nodes']}
        assert 'person_819' in ids   # Edward Norton
        assert 'person_287' in ids   # Brad Pitt
        assert any(e['relation'] == 'acted_in' for e in result['edges'])

    def test_director_node_and_directed_edge(self):
        result = self._build()
        assert 'person_7467' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'directed' for e in result['edges'])

    def test_writer_node_and_wrote_edge(self):
        result = self._build()
        assert 'person_1111' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'wrote' for e in result['edges'])

    def test_company_node_and_produced_by_edge(self):
        result = self._build()
        assert 'company_508' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'produced_by' for e in result['edges'])

    def test_no_duplicate_nodes(self):
        result = self._build()
        ids = [n['id'] for n in result['nodes']]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_edges(self):
        result = self._build()
        eids = [e['id'] for e in result['edges']]
        assert len(eids) == len(set(eids))

    def test_character_stored_in_edge_data(self):
        result = self._build()
        acted_edges = [e for e in result['edges'] if e['relation'] == 'acted_in'
                       and e['source'] == 'person_819']
        assert len(acted_edges) == 1
        assert acted_edges[0]['data']['character'] == 'The Narrator'


# ── build_tv_graph ────────────────────────────────────────────────────────────

class TestBuildTvGraph:
    def _build(self, tmdb_id=1396):
        with patch('server.tmdb.get_tv_details', return_value=TV_DETAILS), \
             patch('server.tmdb.get_tv_credits', return_value=TV_CREDITS):
            return build_tv_graph(tmdb_id)

    def test_center_node_id(self):
        result = self._build(1396)
        assert result['center'] == 'tv_1396'

    def test_tv_node_correct_label(self):
        result = self._build()
        tv = next(n for n in result['nodes'] if n['id'] == 'tv_1396')
        assert tv['label'] == 'Breaking Bad'

    def test_creator_gets_created_edge(self):
        result = self._build()
        assert 'person_66633' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'created' for e in result['edges'])

    def test_cast_node_and_acted_in_edge(self):
        result = self._build()
        assert 'person_17419' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'acted_in' for e in result['edges'])

    def test_company_node_and_produced_by_edge(self):
        result = self._build()
        assert 'company_2575' in {n['id'] for n in result['nodes']}
        assert any(e['relation'] == 'produced_by' for e in result['edges'])

    def test_creator_not_duplicated_if_also_in_crew(self):
        """A creator who also appears in crew should produce exactly one node and one edge."""
        tv = dict(TV_DETAILS)
        credits = {
            'cast': [],
            'crew': [
                {'id': 66633, 'name': 'Vince Gilligan', 'job': 'Executive Producer',
                 'department': 'Production', 'profile_path': None},
            ],
        }
        with patch('server.tmdb.get_tv_details', return_value=tv), \
             patch('server.tmdb.get_tv_credits', return_value=credits):
            result = build_tv_graph(1396)
        vince_nodes = [n for n in result['nodes'] if n['id'] == 'person_66633']
        assert len(vince_nodes) == 1

    def test_no_duplicate_nodes(self):
        result = self._build()
        ids = [n['id'] for n in result['nodes']]
        assert len(ids) == len(set(ids))

    def test_no_duplicate_edges(self):
        result = self._build()
        eids = [e['id'] for e in result['edges']]
        assert len(eids) == len(set(eids))


# ── expand_person ─────────────────────────────────────────────────────────────

class TestExpandPerson:
    def _expand(self, person_id=17419):
        with patch('server.tmdb.get_person_details', return_value=PERSON_DETAILS), \
             patch('server.tmdb.get_person_combined_credits', return_value=PERSON_CREDITS):
            return expand_person(person_id)

    def test_center_node_id(self):
        result = self._expand(17419)
        assert result['center'] == 'person_17419'

    def test_center_node_label(self):
        result = self._expand()
        center = next(n for n in result['nodes'] if n['id'] == 'person_17419')
        assert center['label'] == 'Bryan Cranston'

    def test_credit_nodes_added(self):
        result = self._expand()
        ids = {n['id'] for n in result['nodes']}
        assert 'tv_1396' in ids    # Breaking Bad
        assert 'movie_550' in ids  # Fight Club

    def test_acted_in_edges_present(self):
        result = self._expand()
        assert all(e['relation'] == 'acted_in' for e in result['edges'])

    def test_edges_go_from_person_to_title(self):
        result = self._expand(17419)
        for edge in result['edges']:
            assert edge['source'] == 'person_17419'

    def test_no_duplicate_nodes(self):
        result = self._expand()
        ids = [n['id'] for n in result['nodes']]
        assert len(ids) == len(set(ids))

    def test_unknown_media_type_excluded(self):
        """Credits with unrecognised media_type should be dropped."""
        credits = {
            'cast': [
                {'id': 999, 'name': 'Unknown Show', 'media_type': 'unknown',
                 'character': 'X', 'popularity': 10.0, 'poster_path': None, 'vote_average': 5.0},
            ]
        }
        with patch('server.tmdb.get_person_details', return_value=PERSON_DETAILS), \
             patch('server.tmdb.get_person_combined_credits', return_value=credits):
            result = expand_person(17419)
        assert len(result['nodes']) == 1  # only the person center node


# ── expand_company ────────────────────────────────────────────────────────────

class TestExpandCompany:
    def _expand(self, company_id=508):
        with patch('server.tmdb.get_company_movies', return_value=COMPANY_MOVIES):
            return expand_company(company_id)

    def test_center_node_id(self):
        result = self._expand(508)
        assert result['center'] == 'company_508'

    def test_movie_nodes_added(self):
        result = self._expand()
        ids = {n['id'] for n in result['nodes']}
        assert 'movie_550' in ids
        assert 'movie_807' in ids

    def test_produced_by_edges_present(self):
        result = self._expand()
        assert all(e['relation'] == 'produced_by' for e in result['edges'])

    def test_all_edges_target_company(self):
        result = self._expand(508)
        for edge in result['edges']:
            assert edge['target'] == 'company_508'

    def test_no_duplicate_nodes(self):
        result = self._expand()
        ids = [n['id'] for n in result['nodes']]
        assert len(ids) == len(set(ids))
