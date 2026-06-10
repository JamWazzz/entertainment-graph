import os

from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

from .database import init_db
from . import graph, cache as _cache
from .tmdb import search_multi, search_movie, search_tv


def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)

    with app.app_context():
        init_db()

    # ── health ────────────────────────────────────────────────────────────────

    @app.get('/health')
    def health():
        return jsonify({'status': 'ok'})

    # ── search ────────────────────────────────────────────────────────────────

    @app.get('/api/search')
    def search():
        q = request.args.get('q', '').strip()
        media_type = request.args.get('type', 'multi')  # movie | tv | multi

        if not q:
            return jsonify({'error': 'Query parameter "q" is required'}), 400
        if media_type not in ('movie', 'tv', 'multi'):
            return jsonify({'error': 'type must be movie, tv, or multi'}), 400

        if media_type == 'movie':
            raw = search_movie(q)
        elif media_type == 'tv':
            raw = search_tv(q)
        else:
            raw = search_multi(q)

        results = []
        for item in raw.get('results', []):
            mtype = item.get('media_type', media_type)
            if mtype not in ('movie', 'tv'):
                continue
            results.append({
                'tmdb_id': item['id'],
                'media_type': mtype,
                'title': item.get('title') or item.get('name', 'Unknown'),
                'overview': item.get('overview', ''),
                'poster_path': item.get('poster_path') or '',
                'vote_average': item.get('vote_average', 0),
                'release_date': item.get('release_date') or item.get('first_air_date', ''),
            })

        return jsonify({'results': results, 'total': len(results)})

    # ── graph ─────────────────────────────────────────────────────────────────

    @app.get('/api/graph/<media_type>/<int:tmdb_id>')
    def get_graph(media_type: str, tmdb_id: int):
        if media_type not in ('movie', 'tv'):
            return jsonify({'error': 'media_type must be movie or tv'}), 400

        cached = _cache.get_graph(media_type, tmdb_id)
        if cached is not None:
            return jsonify(cached)

        data = (
            graph.build_movie_graph(tmdb_id)
            if media_type == 'movie'
            else graph.build_tv_graph(tmdb_id)
        )

        _cache.set_graph(media_type, tmdb_id, data)
        return jsonify(data)

    # ── expand node ───────────────────────────────────────────────────────────

    @app.get('/api/expand/<node_type>/<int:node_id>')
    def expand_node(node_type: str, node_id: int):
        if node_type == 'person':
            data = graph.expand_person(node_id)
        elif node_type == 'company':
            data = graph.expand_company(node_id)
        else:
            return jsonify({'error': f'Cannot expand node type "{node_type}"'}), 400

        return jsonify(data)

    # ── error handlers ────────────────────────────────────────────────────────

    @app.errorhandler(404)
    def not_found(_e):
        return jsonify({'error': 'Not found'}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({'error': str(e)}), 500

    return app


if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    create_app().run(debug=True, port=port)
