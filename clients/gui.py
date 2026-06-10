#!/usr/bin/env python3
"""
Entertainment Graph GUI — connects to the Flask server on localhost:5000.

Usage:
  py clients/gui.py
  py clients/gui.py --server http://localhost:5000
"""

import argparse
import threading
import tkinter as tk
from tkinter import ttk

import requests

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
    'movie':   '[movie]  ',
    'tv':      '[tv]     ',
    'person':  '[person] ',
    'company': '[co]     ',
}


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _get(path: str, params: dict = None) -> dict:
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

def _node_label_text(node: dict, is_center: bool) -> str:
    tag = TYPE_TAGS.get(node['type'], node['type'])
    marker = '* ' if is_center else '  '
    d = node.get('data', {})
    detail = ''
    if node['type'] in ('movie', 'tv'):
        date = d.get('release_date') or d.get('first_air_date', '')
        year = date[:4] if date else ''
        rating = d.get('vote_average', '')
        detail = f"  {year}  *{rating}" if (year or rating) else ''
    elif node['type'] == 'person' and d.get('known_for_department'):
        detail = f"  ({d['known_for_department']})"
    hint = '  [dbl-click to expand]' if (node['type'] in EXPANDABLE and not is_center) else ''
    return f"{marker}{tag} {node['label']}{detail}{hint}"


def _edges_lines(edges: list, nodes_by_id: dict) -> str:
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
    return '\n'.join(lines)


# ── app ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Entertainment Graph Explorer')
        self.geometry('1200x720')
        self.minsize(800, 500)

        self._nodes: list = []
        self._result_data: dict = {}  # treeview iid -> result dict

        self._build_ui()
        self._search_entry.focus_set()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Search bar
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill='x', side='top')

        ttk.Label(bar, text='Search:').pack(side='left')
        self._query_var = tk.StringVar()
        self._search_entry = ttk.Entry(bar, textvariable=self._query_var, width=46)
        self._search_entry.pack(side='left', padx=(4, 10))
        self._search_entry.bind('<Return>', lambda _e: self._do_search())

        self._type_var = tk.StringVar(value='multi')
        for label, value in [('All', 'multi'), ('Movies', 'movie'), ('TV', 'tv')]:
            ttk.Radiobutton(bar, text=label, variable=self._type_var, value=value).pack(
                side='left', padx=2
            )

        ttk.Button(bar, text='Search', command=self._do_search).pack(side='left', padx=(10, 0))

        self._status_var = tk.StringVar(value='Ready.')
        self._status_lbl = ttk.Label(bar, textvariable=self._status_var, foreground='gray')
        self._status_lbl.pack(side='right', padx=8)

        ttk.Separator(self, orient='horizontal').pack(fill='x')

        # Left / right split
        main_pane = ttk.PanedWindow(self, orient='horizontal')
        main_pane.pack(fill='both', expand=True, padx=6, pady=6)

        left = ttk.Frame(main_pane)
        main_pane.add(left, weight=1)
        self._build_results_panel(left)

        right = ttk.Frame(main_pane)
        main_pane.add(right, weight=2)
        self._build_graph_panel(right)

    def _build_results_panel(self, parent):
        ttk.Label(parent, text='Results', font=('', 10, 'bold')).pack(anchor='w', pady=(0, 2))

        self._tree = ttk.Treeview(
            parent, columns=('type', 'year'),
            show='tree headings', selectmode='browse',
        )
        self._tree.heading('#0', text='Title')
        self._tree.heading('type', text='Type')
        self._tree.heading('year', text='Year')
        self._tree.column('#0', width=220, minwidth=120)
        self._tree.column('type', width=65, anchor='center', stretch=False)
        self._tree.column('year', width=50, anchor='center', stretch=False)

        scroll = ttk.Scrollbar(parent, orient='vertical', command=self._tree.yview)
        self._tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        self._tree.pack(fill='both', expand=True)
        self._tree.bind('<<TreeviewSelect>>', self._on_result_select)

    def _build_graph_panel(self, parent):
        graph_pane = ttk.PanedWindow(parent, orient='vertical')
        graph_pane.pack(fill='both', expand=True)

        # Nodes
        nodes_frame = ttk.LabelFrame(
            graph_pane,
            text='Nodes    (* = center    double-click a person or company to expand)',
            padding=4,
        )
        graph_pane.add(nodes_frame, weight=1)

        self._nodes_lb = tk.Listbox(
            nodes_frame, font=('Courier New', 9),
            activestyle='none', selectbackground='#3a7ebf', selectforeground='white',
        )
        ns = ttk.Scrollbar(nodes_frame, orient='vertical', command=self._nodes_lb.yview)
        self._nodes_lb.configure(yscrollcommand=ns.set)
        ns.pack(side='right', fill='y')
        self._nodes_lb.pack(fill='both', expand=True)
        self._nodes_lb.bind('<Double-Button-1>', self._on_node_expand)
        self._nodes_lb.bind('<Return>', self._on_node_expand)

        # Edges
        edges_frame = ttk.LabelFrame(graph_pane, text='Edges', padding=4)
        graph_pane.add(edges_frame, weight=1)

        self._edges_text = tk.Text(
            edges_frame, font=('Courier New', 9),
            state='disabled', wrap='none', height=8,
        )
        eys = ttk.Scrollbar(edges_frame, orient='vertical', command=self._edges_text.yview)
        exs = ttk.Scrollbar(edges_frame, orient='horizontal', command=self._edges_text.xview)
        self._edges_text.configure(yscrollcommand=eys.set, xscrollcommand=exs.set)
        exs.pack(side='bottom', fill='x')
        eys.pack(side='right', fill='y')
        self._edges_text.pack(fill='both', expand=True)

    # ── search ────────────────────────────────────────────────────────────────

    def _do_search(self):
        query = self._query_var.get().strip()
        if not query:
            return
        self._set_status('Searching...')
        self._tree.delete(*self._tree.get_children())
        self._result_data.clear()
        self._clear_graph()
        threading.Thread(
            target=self._bg_search,
            args=(query, self._type_var.get()),
            daemon=True,
        ).start()

    def _bg_search(self, query: str, media_type: str):
        data = _get('/api/search', {'q': query, 'type': media_type})
        self.after(0, self._show_results, data)

    def _show_results(self, data: dict):
        if 'error' in data:
            self._set_status(data['error'], error=True)
            return
        results = data.get('results', [])
        self._set_status(f"{len(results)} result(s) — select one to view its graph.")
        for r in results:
            year = (r.get('release_date') or '')[:4] or 'n/a'
            iid = self._tree.insert('', 'end', text=r['title'],
                                    values=(r['media_type'], year))
            self._result_data[iid] = r

    # ── graph ─────────────────────────────────────────────────────────────────

    def _on_result_select(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        r = self._result_data.get(sel[0])
        if not r:
            return
        self._set_status('Loading graph...')
        self._clear_graph()
        threading.Thread(
            target=self._bg_graph,
            args=(r['media_type'], r['tmdb_id']),
            daemon=True,
        ).start()

    def _bg_graph(self, media_type: str, tmdb_id: int):
        data = _get(f'/api/graph/{media_type}/{tmdb_id}')
        self.after(0, self._populate_graph, data)

    # ── expand ────────────────────────────────────────────────────────────────

    def _on_node_expand(self, _event):
        idx = self._nodes_lb.curselection()
        if not idx:
            return
        node = self._nodes[idx[0]]
        if node['type'] not in EXPANDABLE:
            return
        self._set_status(f"Expanding {node['label']}...")
        threading.Thread(
            target=self._bg_expand,
            args=(node['type'], node['data']['tmdb_id']),
            daemon=True,
        ).start()

    def _bg_expand(self, node_type: str, node_id: int):
        data = _get(f'/api/expand/{node_type}/{node_id}')
        self.after(0, self._populate_graph, data)

    # ── shared graph renderer ─────────────────────────────────────────────────

    def _populate_graph(self, data: dict):
        if 'error' in data:
            self._set_status(data['error'], error=True)
            return

        nodes = data.get('nodes', [])
        edges = data.get('edges', [])
        center = data.get('center', '')
        nodes_by_id = {n['id']: n for n in nodes}

        self._nodes = nodes
        self._nodes_lb.delete(0, 'end')
        for node in nodes:
            self._nodes_lb.insert('end', _node_label_text(node, node['id'] == center))

        self._set_edges(_edges_lines(edges, nodes_by_id))
        self._set_status(f"{len(nodes)} nodes, {len(edges)} edges.")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _clear_graph(self):
        self._nodes = []
        self._nodes_lb.delete(0, 'end')
        self._set_edges('')

    def _set_edges(self, text: str):
        self._edges_text.configure(state='normal')
        self._edges_text.delete('1.0', 'end')
        if text:
            self._edges_text.insert('1.0', text)
        self._edges_text.configure(state='disabled')

    def _set_status(self, msg: str, error: bool = False):
        self._status_var.set(msg)
        self._status_lbl.configure(foreground='red' if error else 'gray')


# ── entry point ───────────────────────────────────────────────────────────────

def main():
    global BASE_URL
    parser = argparse.ArgumentParser(description='Entertainment Graph GUI')
    parser.add_argument('--server', default=BASE_URL, metavar='URL',
                        help=f'Server base URL (default: {BASE_URL})')
    args = parser.parse_args()
    BASE_URL = args.server.rstrip('/')
    App().mainloop()


if __name__ == '__main__':
    main()
