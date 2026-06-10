#!/usr/bin/env python3
"""
Entertainment Graph CLI — connects to the Flask server on localhost:5000.

Usage:
  python clients/cli.py search "Inception"
  python clients/cli.py search "Breaking Bad" --type tv
  python clients/cli.py graph movie 27205
  python clients/cli.py graph tv 1396
  python clients/cli.py expand person 6193
  python clients/cli.py expand company 174
"""

import argparse
import sys

import requests

BASE_URL = 'http://localhost:5000'

RELATION_LABEL = {
    'acted_in':   'acted in',
    'directed':   'directed',
    'wrote':      'wrote',
    'created':    'created',
    'produced_by': 'produced by',
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(f'{BASE_URL}{path}', params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        print(f'Error: cannot reach server at {BASE_URL}. Is it running?', file=sys.stderr)
        sys.exit(1)
    except requests.HTTPError as exc:
        body = exc.response.json() if exc.response.content else {}
        print(f'Error {exc.response.status_code}: {body.get("error", exc)}', file=sys.stderr)
        sys.exit(1)


# ── formatting helpers ────────────────────────────────────────────────────────

def _type_tag(media_type: str) -> str:
    return {'movie': '[movie]', 'tv': '[tv]   ', 'person': '[person]',
            'company': '[co]   '}.get(media_type, f'[{media_type}]')


def _print_nodes(nodes: list[dict], center: str):
    print(f'\n  Nodes ({len(nodes)}):')
    for node in nodes:
        tag = _type_tag(node['type'])
        marker = ' *' if node['id'] == center else '  '
        data = node.get('data', {})
        detail = ''
        if node['type'] in ('movie', 'tv'):
            date = data.get('release_date') or data.get('first_air_date', '')
            rating = data.get('vote_average', '')
            detail = f"  {date[:4] if date else ''}  *{rating}" if date or rating else ''
        elif node['type'] == 'person':
            detail = f"  {data.get('known_for_department', '')}"
        print(f'{marker} {tag} {node["label"]}{detail}')


def _print_edges(edges: list[dict], nodes_by_id: dict):
    print(f'\n  Edges ({len(edges)}):')
    for edge in edges:
        src_label = nodes_by_id.get(edge['source'], {}).get('label', edge['source'])
        dst_label = nodes_by_id.get(edge['target'], {}).get('label', edge['target'])
        rel = RELATION_LABEL.get(edge['relation'], edge['relation'])
        extra = ''
        if 'character' in edge.get('data', {}) and edge['data']['character']:
            extra = f' (as {edge["data"]["character"]})'
        if 'job' in edge.get('data', {}) and edge['data']['job']:
            extra = f' ({edge["data"]["job"]})'
        print(f'    {src_label}  -[{rel}]->  {dst_label}{extra}')


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_search(args):
    params = {'q': args.query}
    if args.type:
        params['type'] = args.type

    data = _get('/api/search', params)
    results = data.get('results', [])

    if not results:
        print('No results found.')
        return

    print(f'\nSearch results for "{args.query}" ({len(results)} found):\n')
    for i, item in enumerate(results, start=1):
        date = item.get('release_date', '')
        year = date[:4] if date else 'n/a'
        mtype = item.get('media_type', '')
        print(f'  {i:>2}. {item["title"]}')
        print(f'      {_type_tag(mtype)}  {year}  ID: {item["tmdb_id"]}')
        if item.get('overview'):
            snippet = item['overview'][:120].rstrip()
            if len(item['overview']) > 120:
                snippet += '…'
            print(f'      {snippet}')
        print()


def cmd_graph(args):
    if args.media_type not in ('movie', 'tv'):
        print('Error: media_type must be "movie" or "tv".', file=sys.stderr)
        sys.exit(1)

    data = _get(f'/api/graph/{args.media_type}/{args.tmdb_id}')
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    center = data.get('center', '')

    center_node = next((n for n in nodes if n['id'] == center), None)
    title = center_node['label'] if center_node else center

    print(f'\nGraph for: {title}  ({args.media_type} / ID {args.tmdb_id})')
    print(f'  (* = center node)')

    nodes_by_id = {n['id']: n for n in nodes}
    _print_nodes(nodes, center)
    _print_edges(edges, nodes_by_id)
    print()


def cmd_expand(args):
    if args.node_type not in ('person', 'company'):
        print('Error: node_type must be "person" or "company".', file=sys.stderr)
        sys.exit(1)

    data = _get(f'/api/expand/{args.node_type}/{args.node_id}')
    nodes = data.get('nodes', [])
    edges = data.get('edges', [])
    center = data.get('center', '')

    center_node = next((n for n in nodes if n['id'] == center), None)
    label = center_node['label'] if center_node else center

    print(f'\nExpanded connections for: {label}  ({args.node_type} / ID {args.node_id})')
    print(f'  (* = expanded node)')

    nodes_by_id = {n['id']: n for n in nodes}
    _print_nodes(nodes, center)
    _print_edges(edges, nodes_by_id)
    print()


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    global BASE_URL
    parser = argparse.ArgumentParser(
        prog='cli',
        description='Entertainment Graph CLI — explore movies and TV connections.',
    )
    parser.add_argument(
        '--server', default=BASE_URL, metavar='URL',
        help=f'Server base URL (default: {BASE_URL})',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    # search
    p_search = subparsers.add_parser('search', help='Search for a movie or TV show')
    p_search.add_argument('query', help='Title to search for')
    p_search.add_argument('--type', choices=['movie', 'tv', 'multi'], default='multi',
                          help='Filter by media type (default: multi)')

    # graph
    p_graph = subparsers.add_parser('graph', help='Show the connection graph for a title')
    p_graph.add_argument('media_type', choices=['movie', 'tv'], help='movie or tv')
    p_graph.add_argument('tmdb_id', type=int, help='TMDB numeric ID')

    # expand
    p_expand = subparsers.add_parser('expand', help='Expand a person or company node')
    p_expand.add_argument('node_type', choices=['person', 'company'], help='person or company')
    p_expand.add_argument('node_id', type=int, help='TMDB numeric ID')

    args = parser.parse_args()

    # allow --server override to propagate into _get
    BASE_URL = args.server.rstrip('/')

    dispatch = {'search': cmd_search, 'graph': cmd_graph, 'expand': cmd_expand}
    dispatch[args.command](args)


if __name__ == '__main__':
    main()
