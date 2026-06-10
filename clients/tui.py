#!/usr/bin/env python3
"""
Entertainment Graph TUI — connects to the Flask server on localhost:5000.

Usage:
  py clients/tui.py
  py clients/tui.py --server http://localhost:5000
"""

import sys
import argparse

import asyncio

import requests
from textual.app import App, ComposeResult
from textual.screen import Screen
from textual.widgets import (
    Header, Footer, Input, ListView, ListItem,
    Label, Static, LoadingIndicator, Select,
)
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual import on, work

BASE_URL = 'http://localhost:5000'
EXPANDABLE = {'person', 'company'}

RELATION_LABELS = {
    'acted_in':    'acted in',
    'directed':    'directed',
    'wrote':       'wrote',
    'created':     'created',
    'produced_by': 'produced by',
}

TYPE_TAGS = {
    'movie':   '[movie]',
    'tv':      '[tv]   ',
    'person':  '[person]',
    'company': '[co]   ',
}


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _get(path: str, params: dict | None = None) -> dict:
    try:
        resp = requests.get(f'{BASE_URL}{path}', params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.ConnectionError:
        return {'error': f'Cannot reach server at {BASE_URL}. Is it running?'}
    except requests.HTTPError as exc:
        body = exc.response.json() if exc.response.content else {}
        return {'error': body.get('error', str(exc))}


# ── helpers ───────────────────────────────────────────────────────────────────

def _edges_text(edges: list, nodes_by_id: dict) -> str:
    lines = []
    for edge in edges:
        src = nodes_by_id.get(edge['source'], {}).get('label', edge['source'])
        dst = nodes_by_id.get(edge['target'], {}).get('label', edge['target'])
        rel = RELATION_LABELS.get(edge['relation'], edge['relation'])
        d = edge.get('data', {})
        extra = ''
        if d.get('character'):
            extra = f" (as {d['character']})"
        elif d.get('job'):
            extra = f" ({d['job']})"
        lines.append(f"{src}  -[{rel}]->  {dst}{extra}")
    return '\n'.join(lines) if lines else '(no edges)'


def _node_detail(node: dict) -> str:
    d = node.get('data', {})
    if node['type'] in ('movie', 'tv'):
        date = d.get('release_date') or d.get('first_air_date', '')
        year = date[:4] if date else ''
        rating = d.get('vote_average', '')
        return f"  {year}  *{rating}" if (year or rating) else ''
    if node['type'] == 'person':
        dept = d.get('known_for_department', '')
        return f"  ({dept})" if dept else ''
    return ''


# ── custom list items ─────────────────────────────────────────────────────────

class ResultItem(ListItem):
    def __init__(self, result: dict) -> None:
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        r = self.result
        year = (r.get('release_date') or '')[:4] or 'n/a'
        tag = TYPE_TAGS.get(r['media_type'], r['media_type'])
        rating = r.get('vote_average', 0)
        yield Label(f"{r['title']}  {tag}  {year}  *{rating}  (ID: {r['tmdb_id']})")
        if r.get('overview'):
            snippet = r['overview'][:100] + ('...' if len(r['overview']) > 100 else '')
            yield Label(f"  {snippet}", classes='muted')


class NodeItem(ListItem):
    def __init__(self, node: dict, is_center: bool = False) -> None:
        super().__init__()
        self.node = node
        self.is_center = is_center

    def compose(self) -> ComposeResult:
        n = self.node
        tag = TYPE_TAGS.get(n['type'], n['type'])
        marker = '* ' if self.is_center else '  '
        detail = _node_detail(n)
        hint = '  [expand]' if (n['type'] in EXPANDABLE and not self.is_center) else ''
        yield Label(f"{marker}{tag}  {n['label']}{detail}{hint}")


# ── screens ───────────────────────────────────────────────────────────────────

class SearchScreen(Screen):
    BINDINGS = [('q', 'app.quit', 'Quit')]

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            with Horizontal(id='search-bar'):
                yield Input(
                    placeholder='Search for a movie or TV show... (Enter to search)',
                    id='search-input',
                )
                yield Select(
                    options=[('All', 'multi'), ('Movies', 'movie'), ('TV Shows', 'tv')],
                    value='multi',
                    allow_blank=False,
                    id='type-select',
                )
            yield LoadingIndicator(id='loading')
            yield ListView(id='results-list')
        yield Footer()

    def on_mount(self) -> None:
        self.query_one('#loading').display = False
        self.query_one('#search-input').focus()

    @on(Input.Submitted, '#search-input')
    def do_search(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        sel = self.query_one('#type-select')
        media_type = 'multi' if sel.value is Select.BLANK else str(sel.value)
        self.query_one('#loading').display = True
        self.query_one(ListView).clear()
        self._fetch(query, media_type)

    @work
    async def _fetch(self, query: str, media_type: str) -> None:
        data = await asyncio.to_thread(_get, '/api/search', {'q': query, 'type': media_type})
        self._show_results(data)

    def _show_results(self, data: dict) -> None:
        self.query_one('#loading').display = False
        lv = self.query_one(ListView)
        if 'error' in data:
            lv.append(ListItem(Label(f"Error: {data['error']}")))
            return
        results = data.get('results', [])
        if not results:
            lv.append(ListItem(Label('No results found.')))
            return
        for r in results:
            lv.append(ResultItem(r))

    @on(ListView.Selected, '#results-list')
    def open_graph(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, ResultItem):
            return
        r = event.item.result
        self.app.push_screen(
            GraphScreen(r['tmdb_id'], r['media_type'], r['title'])
        )


class GraphScreen(Screen):
    BINDINGS = [('escape', 'app.pop_screen', 'Back'), ('q', 'app.quit', 'Quit')]

    def __init__(self, tmdb_id: int, media_type: str, title: str) -> None:
        super().__init__()
        self._tmdb_id = tmdb_id
        self._media_type = media_type
        self._title = title

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f" {self._title}  ({self._media_type} / ID {self._tmdb_id})",
            id='screen-title',
        )
        with Horizontal(id='graph-body'):
            with Vertical(id='nodes-panel'):
                yield Static('Nodes', id='nodes-label')
                yield ListView(id='nodes-list')
            with Vertical(id='edges-panel'):
                yield Static('Edges', id='edges-label')
                with VerticalScroll():
                    yield Static('Loading...', id='edges-content')
        yield Footer()

    def on_mount(self) -> None:
        self._fetch()

    @work
    async def _fetch(self) -> None:
        data = await asyncio.to_thread(_get, f'/api/graph/{self._media_type}/{self._tmdb_id}')
        self._show_graph(data)

    def _show_graph(self, data: dict) -> None:
        if 'error' in data:
            self.query_one('#edges-content').update(f"Error: {data['error']}")
            return

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        center = data.get('center', '')
        nodes_by_id = {n['id']: n for n in nodes}

        self.query_one('#nodes-label').update(
            f"Nodes ({len(nodes)})  (* = center  [expand] = clickable)"
        )
        lv = self.query_one('#nodes-list')
        for node in nodes:
            lv.append(NodeItem(node, is_center=(node['id'] == center)))

        self.query_one('#edges-label').update(f"Edges ({len(edges)})")
        self.query_one('#edges-content').update(_edges_text(edges, nodes_by_id))

    @on(ListView.Selected, '#nodes-list')
    def expand_node(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, NodeItem):
            return
        item = event.item
        if item.is_center or item.node['type'] not in EXPANDABLE:
            return
        node = item.node
        self.app.push_screen(
            ExpandScreen(node['type'], node['data']['tmdb_id'], node['label'])
        )


class ExpandScreen(Screen):
    BINDINGS = [('escape', 'app.pop_screen', 'Back'), ('q', 'app.quit', 'Quit')]

    def __init__(self, node_type: str, node_id: int, label: str) -> None:
        super().__init__()
        self._node_type = node_type
        self._node_id = node_id
        self._label = label

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            f" Expanding: {self._label}  ({self._node_type} / ID {self._node_id})",
            id='screen-title',
        )
        with Horizontal(id='graph-body'):
            with Vertical(id='nodes-panel'):
                yield Static('Nodes', id='nodes-label')
                yield ListView(id='nodes-list')
            with Vertical(id='edges-panel'):
                yield Static('Edges', id='edges-label')
                with VerticalScroll():
                    yield Static('Loading...', id='edges-content')
        yield Footer()

    def on_mount(self) -> None:
        self._fetch()

    @work
    async def _fetch(self) -> None:
        data = await asyncio.to_thread(_get, f'/api/expand/{self._node_type}/{self._node_id}')
        self._show_expand(data)

    def _show_expand(self, data: dict) -> None:
        if 'error' in data:
            self.query_one('#edges-content').update(f"Error: {data['error']}")
            return

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        center = data.get('center', '')
        nodes_by_id = {n['id']: n for n in nodes}

        self.query_one('#nodes-label').update(
            f"Nodes ({len(nodes)})  (* = center  [expand] = clickable)"
        )
        lv = self.query_one('#nodes-list')
        for node in nodes:
            lv.append(NodeItem(node, is_center=(node['id'] == center)))

        self.query_one('#edges-label').update(f"Edges ({len(edges)})")
        self.query_one('#edges-content').update(_edges_text(edges, nodes_by_id))

    @on(ListView.Selected, '#nodes-list')
    def expand_node(self, event: ListView.Selected) -> None:
        if not isinstance(event.item, NodeItem):
            return
        item = event.item
        if item.is_center or item.node['type'] not in EXPANDABLE:
            return
        node = item.node
        self.app.push_screen(
            ExpandScreen(node['type'], node['data']['tmdb_id'], node['label'])
        )


# ── app ───────────────────────────────────────────────────────────────────────

class EntertainmentGraphApp(App):
    TITLE = 'Entertainment Graph Explorer'
    CSS = '''
    Screen {
        background: $surface;
    }

    #search-bar {
        height: 3;
        dock: top;
    }

    #search-input {
        width: 1fr;
    }

    #type-select {
        width: 20;
    }

    #loading {
        height: 1;
        dock: top;
    }

    #results-list {
        height: 1fr;
        border: solid $primary-darken-2;
    }

    ResultItem {
        padding: 0 1;
    }

    ResultItem .muted {
        color: $text-muted;
    }

    #screen-title {
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 0;
    }

    #graph-body {
        height: 1fr;
    }

    #nodes-panel {
        width: 45%;
        border: solid $primary;
    }

    #edges-panel {
        width: 55%;
        border: solid $secondary;
    }

    #nodes-list {
        height: 1fr;
    }

    NodeItem {
        padding: 0 1;
    }

    #edges-content {
        padding: 1;
    }

    #nodes-label, #edges-label {
        height: 1;
        background: $primary-darken-3;
        color: $accent;
        padding: 0 1;
    }
    '''

    def on_mount(self) -> None:
        self.push_screen(SearchScreen())


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    global BASE_URL
    parser = argparse.ArgumentParser(description='Entertainment Graph TUI')
    parser.add_argument('--server', default=BASE_URL, metavar='URL',
                        help=f'Server base URL (default: {BASE_URL})')
    args = parser.parse_args()
    BASE_URL = args.server.rstrip('/')
    EntertainmentGraphApp().run()


if __name__ == '__main__':
    main()
