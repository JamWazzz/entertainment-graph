from . import tmdb

MAX_CAST = 10
MAX_CREW_JOBS = {'Director', 'Screenplay', 'Writer', 'Story', 'Creator', 'Executive Producer'}
MAX_EXPAND = 10


# ── helpers ──────────────────────────────────────────────────────────────────

def _nid(kind: str, tmdb_id) -> str:
    return f'{kind}_{tmdb_id}'


def _eid(src: str, dst: str, rel: str) -> str:
    return f'{src}__{dst}__{rel}'


class _GraphBuilder:
    def __init__(self):
        self.nodes: list[dict] = []
        self.edges: list[dict] = []
        self._seen_nodes: set[str] = set()
        self._seen_edges: set[str] = set()

    def add_node(self, node_id: str, kind: str, label: str, data: dict):
        if node_id not in self._seen_nodes:
            self.nodes.append({'id': node_id, 'type': kind, 'label': label, 'data': data})
            self._seen_nodes.add(node_id)

    def add_edge(self, src: str, dst: str, relation: str, data: dict | None = None):
        eid = _eid(src, dst, relation)
        if eid not in self._seen_edges:
            self.edges.append({
                'id': eid, 'source': src, 'target': dst,
                'relation': relation, 'data': data or {},
            })
            self._seen_edges.add(eid)

    def to_dict(self, center: str) -> dict:
        return {'nodes': self.nodes, 'edges': self.edges, 'center': center}


# ── public builders ───────────────────────────────────────────────────────────

def build_movie_graph(tmdb_id: int) -> dict:
    details = tmdb.get_movie_details(tmdb_id)
    credits = tmdb.get_movie_credits(tmdb_id)

    g = _GraphBuilder()
    center = _nid('movie', tmdb_id)

    g.add_node(center, 'movie', details.get('title', 'Unknown'), {
        'tmdb_id': tmdb_id,
        'overview': details.get('overview', ''),
        'release_date': details.get('release_date', ''),
        'poster_path': details.get('poster_path', ''),
        'vote_average': details.get('vote_average', 0),
        'genres': [x['name'] for x in details.get('genres', [])],
    })

    for member in credits.get('cast', [])[:MAX_CAST]:
        pid = _nid('person', member['id'])
        g.add_node(pid, 'person', member['name'], {
            'tmdb_id': member['id'],
            'profile_path': member.get('profile_path', ''),
        })
        g.add_edge(pid, center, 'acted_in', {'character': member.get('character', '')})

    for member in credits.get('crew', []):
        job = member.get('job', '')
        if job not in MAX_CREW_JOBS:
            continue
        pid = _nid('person', member['id'])
        g.add_node(pid, 'person', member['name'], {
            'tmdb_id': member['id'],
            'profile_path': member.get('profile_path', ''),
        })
        relation = 'directed' if job == 'Director' else 'wrote'
        g.add_edge(pid, center, relation, {'job': job})

    for company in details.get('production_companies', []):
        cid = _nid('company', company['id'])
        g.add_node(cid, 'company', company['name'], {
            'tmdb_id': company['id'],
            'logo_path': company.get('logo_path', ''),
            'origin_country': company.get('origin_country', ''),
        })
        g.add_edge(center, cid, 'produced_by')

    return g.to_dict(center)


def build_tv_graph(tmdb_id: int) -> dict:
    details = tmdb.get_tv_details(tmdb_id)
    credits = tmdb.get_tv_credits(tmdb_id)

    g = _GraphBuilder()
    center = _nid('tv', tmdb_id)

    g.add_node(center, 'tv', details.get('name', 'Unknown'), {
        'tmdb_id': tmdb_id,
        'overview': details.get('overview', ''),
        'first_air_date': details.get('first_air_date', ''),
        'poster_path': details.get('poster_path', ''),
        'vote_average': details.get('vote_average', 0),
        'genres': [x['name'] for x in details.get('genres', [])],
        'number_of_seasons': details.get('number_of_seasons', 0),
    })

    # Creators get a dedicated 'created' edge
    creator_ids: set[int] = set()
    for creator in details.get('created_by', []):
        creator_ids.add(creator['id'])
        pid = _nid('person', creator['id'])
        g.add_node(pid, 'person', creator['name'], {
            'tmdb_id': creator['id'],
            'profile_path': creator.get('profile_path', ''),
        })
        g.add_edge(pid, center, 'created')

    for member in credits.get('cast', [])[:MAX_CAST]:
        pid = _nid('person', member['id'])
        g.add_node(pid, 'person', member['name'], {
            'tmdb_id': member['id'],
            'profile_path': member.get('profile_path', ''),
        })
        g.add_edge(pid, center, 'acted_in', {'character': member.get('character', '')})

    for member in credits.get('crew', []):
        job = member.get('job', '')
        if job not in MAX_CREW_JOBS or member['id'] in creator_ids:
            continue
        pid = _nid('person', member['id'])
        g.add_node(pid, 'person', member['name'], {
            'tmdb_id': member['id'],
            'profile_path': member.get('profile_path', ''),
        })
        relation = 'directed' if job == 'Director' else 'wrote'
        g.add_edge(pid, center, relation, {'job': job})

    for company in details.get('production_companies', []):
        cid = _nid('company', company['id'])
        g.add_node(cid, 'company', company['name'], {
            'tmdb_id': company['id'],
            'logo_path': company.get('logo_path', ''),
            'origin_country': company.get('origin_country', ''),
        })
        g.add_edge(center, cid, 'produced_by')

    return g.to_dict(center)


def expand_person(person_id: int) -> dict:
    details = tmdb.get_person_details(person_id)
    credits = tmdb.get_person_combined_credits(person_id)

    g = _GraphBuilder()
    center = _nid('person', person_id)

    g.add_node(center, 'person', details.get('name', 'Unknown'), {
        'tmdb_id': person_id,
        'profile_path': details.get('profile_path', ''),
        'biography': details.get('biography', ''),
        'birthday': details.get('birthday', ''),
        'known_for_department': details.get('known_for_department', ''),
    })

    top_cast = sorted(
        credits.get('cast', []),
        key=lambda x: x.get('popularity', 0),
        reverse=True,
    )[:MAX_EXPAND]

    for credit in top_cast:
        mtype = credit.get('media_type', 'movie')
        if mtype not in ('movie', 'tv'):
            continue
        title = credit.get('title') or credit.get('name', 'Unknown')
        mid = _nid(mtype, credit['id'])
        g.add_node(mid, mtype, title, {
            'tmdb_id': credit['id'],
            'poster_path': credit.get('poster_path', ''),
            'vote_average': credit.get('vote_average', 0),
        })
        g.add_edge(center, mid, 'acted_in', {'character': credit.get('character', '')})

    return g.to_dict(center)


def expand_company(company_id: int) -> dict:
    data = tmdb.get_company_movies(company_id)

    g = _GraphBuilder()
    center = _nid('company', company_id)

    for movie in data.get('results', [])[:MAX_EXPAND]:
        mid = _nid('movie', movie['id'])
        g.add_node(mid, 'movie', movie.get('title', 'Unknown'), {
            'tmdb_id': movie['id'],
            'poster_path': movie.get('poster_path', ''),
            'vote_average': movie.get('vote_average', 0),
            'release_date': movie.get('release_date', ''),
        })
        g.add_edge(mid, center, 'produced_by')

    return g.to_dict(center)
