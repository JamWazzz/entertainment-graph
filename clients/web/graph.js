'use strict';

// ── config ────────────────────────────────────────────────────────────────────
const SERVER = 'http://localhost:5000';

const NODE_COLORS = {
  movie:   '#ef4444',
  tv:      '#8b5cf6',
  person:  '#22c55e',
  company: '#f97316',
};

const NODE_R      = 14;   // base circle radius
const CENTER_R    = 19;   // radius for the origin node
const EXPANDABLE  = new Set(['person', 'company']);

// ── state ─────────────────────────────────────────────────────────────────────
let gNodes      = [];     // full node objects (D3 mutates x/y/vx/vy in place)
let gLinks      = [];     // link objects (D3 mutates source/target to object refs)
let centerNodeId = null;

// ── D3 handles ────────────────────────────────────────────────────────────────
let simulation, zoomGroup, linkGroup, linkLabelGroup, nodeGroup;
let isDragging = false;

// ── boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initGraph();
  initSearch();
});

// ── graph init ────────────────────────────────────────────────────────────────
function initGraph() {
  const container = document.getElementById('graph-container');
  const svg       = d3.select('#graph-svg');
  const w = container.clientWidth  || 800;
  const h = container.clientHeight || 600;

  // zoom / pan
  const zoom = d3.zoom()
    .scaleExtent([0.1, 5])
    .on('zoom', e => zoomGroup.attr('transform', e.transform));
  svg.call(zoom);

  // layer order: links behind nodes
  zoomGroup       = svg.append('g');
  linkGroup       = zoomGroup.append('g').attr('class', 'links');
  linkLabelGroup  = zoomGroup.append('g').attr('class', 'link-labels');
  nodeGroup       = zoomGroup.append('g').attr('class', 'nodes');

  simulation = d3.forceSimulation([])
    .force('link',    d3.forceLink([]).id(d => d.id).distance(140))
    .force('charge',  d3.forceManyBody().strength(-500))
    .force('center',  d3.forceCenter(w / 2, h / 2))
    .force('collide', d3.forceCollide(NODE_R + 12));

  // recentre on resize
  new ResizeObserver(() => {
    const cw = container.clientWidth, ch = container.clientHeight;
    simulation.force('center', d3.forceCenter(cw / 2, ch / 2));
    simulation.alpha(0.1).restart();
  }).observe(container);
}

// ── search ────────────────────────────────────────────────────────────────────
function initSearch() {
  document.getElementById('search-btn').addEventListener('click', doSearch);
  document.getElementById('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
  });
}

async function doSearch() {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const type = document.querySelector('input[name="type"]:checked').value;

  setStatus('Searching…');
  clearResults();

  try {
    const data = await apiFetch(`/api/search?q=${encodeURIComponent(q)}&type=${type}`);
    renderResults(data.results || []);
    setStatus(`${(data.results || []).length} result(s) — select one to explore.`);
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  }
}

function clearResults() {
  document.getElementById('results-panel').innerHTML = '';
}

function renderResults(results) {
  const panel = document.getElementById('results-panel');
  if (!results.length) {
    panel.innerHTML = '<div class="no-results">No results found.</div>';
    return;
  }
  panel.innerHTML = results.map((r, i) => {
    const year = (r.release_date || '').slice(0, 4) || 'n/a';
    const tag  = r.media_type === 'movie' ? 'movie' : 'tv';
    return `
      <div class="result-item" data-index="${i}">
        <span class="result-title">${esc(r.title)}</span>
        <span class="result-meta">
          <span class="rt-tag rt-${tag}">${tag}</span>${year}
        </span>
      </div>`;
  }).join('');

  panel.querySelectorAll('.result-item').forEach(el => {
    el.addEventListener('click', () => {
      panel.querySelectorAll('.result-item').forEach(x => x.classList.remove('active'));
      el.classList.add('active');
      const r = results[+el.dataset.index];
      loadGraph(r.media_type, r.tmdb_id, r.title);
    });
  });
}

// ── graph load ────────────────────────────────────────────────────────────────
async function loadGraph(mediaType, tmdbId, title) {
  gNodes = []; gLinks = []; centerNodeId = null;
  updateGraph();                          // clear the canvas
  hideEmptyState();
  setStatus(`Loading graph for "${title}"…`);

  try {
    const data = await apiFetch(`/api/graph/${mediaType}/${tmdbId}`);
    centerNodeId = data.center;
    mergeGraph(data);
    setStatus(`${gNodes.length} nodes · ${gLinks.length} edges — click a person or company to expand.`);
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  }
}

// ── expand node ───────────────────────────────────────────────────────────────
async function expandNode(nodeType, nodeId, label) {
  setStatus(`Expanding "${label}"…`);
  try {
    const data = await apiFetch(`/api/expand/${nodeType}/${nodeId}`);
    mergeGraph(data);
    setStatus(`${gNodes.length} nodes · ${gLinks.length} edges total.`);
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  }
}

// ── merge ─────────────────────────────────────────────────────────────────────
function mergeGraph(data) {
  const knownNodes = new Set(gNodes.map(n => n.id));
  const knownLinks = new Set(gLinks.map(l => l.id));
  const container  = document.getElementById('graph-container');
  const cx = container.clientWidth  / 2;
  const cy = container.clientHeight / 2;

  for (const node of (data.nodes || [])) {
    if (!knownNodes.has(node.id)) {
      node.x = cx + (Math.random() - 0.5) * 160;
      node.y = cy + (Math.random() - 0.5) * 160;
      gNodes.push(node);
    }
  }

  for (const edge of (data.edges || [])) {
    if (!knownLinks.has(edge.id)) {
      gLinks.push({
        id:       edge.id,
        source:   edge.source,
        target:   edge.target,
        relation: edge.relation,
        edgeData: edge.data || {},
      });
    }
  }

  updateGraph();
}

// ── D3 render ─────────────────────────────────────────────────────────────────
function updateGraph() {
  // ── links ──
  linkGroup.selectAll('line')
    .data(gLinks, d => d.id)
    .join('line')
    .attr('class', 'link');

  // ── link labels ──
  linkLabelGroup.selectAll('text')
    .data(gLinks, d => d.id)
    .join('text')
    .attr('class', 'link-label')
    .text(d => d.relation.replace(/_/g, ' '));

  // ── nodes ──
  nodeGroup.selectAll('g.node')
    .data(gNodes, d => d.id)
    .join(enter => {
      const g = enter.append('g').attr('class', 'node');
      g.append('circle');
      g.append('text').attr('dy', '0.35em');
      g.call(makeDrag());
      g.on('click',     onNodeClick);
      g.on('mouseover', onMouseover);
      g.on('mouseout',  onMouseout);
      return g;
    });

  // update styles on every node (enter + update)
  nodeGroup.selectAll('g.node')
    .classed('is-center',     d => d.id === centerNodeId)
    .classed('is-expandable', d => EXPANDABLE.has(d.type) && d.id !== centerNodeId);

  nodeGroup.selectAll('g.node circle')
    .attr('r',            d => d.id === centerNodeId ? CENTER_R : NODE_R)
    .attr('fill',         d => NODE_COLORS[d.type] || '#64748b')
    .attr('stroke',       d => d.id === centerNodeId ? '#ffffff' : 'rgba(255,255,255,0.2)')
    .attr('stroke-width', d => d.id === centerNodeId ? 2.5 : 1.5);

  nodeGroup.selectAll('g.node text')
    .attr('x',  d => (d.id === centerNodeId ? CENTER_R : NODE_R) + 5)
    .text(d => d.label.length > 20 ? d.label.slice(0, 18) + '…' : d.label);

  // ── simulation ──
  simulation.nodes(gNodes);
  simulation.force('link').links(gLinks);
  simulation.alpha(gNodes.length ? 0.45 : 0).restart();
  simulation.on('tick', ticked);
}

function ticked() {
  linkGroup.selectAll('line')
    .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x).attr('y2', d => d.target.y);

  linkLabelGroup.selectAll('text')
    .attr('x', d => (d.source.x + d.target.x) / 2)
    .attr('y', d => (d.source.y + d.target.y) / 2);

  nodeGroup.selectAll('g.node')
    .attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`);
}

// ── drag ──────────────────────────────────────────────────────────────────────
function makeDrag() {
  return d3.drag()
    .on('start', (event, d) => {
      isDragging = false;
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    })
    .on('drag', (event, d) => {
      isDragging = true;
      d.fx = event.x; d.fy = event.y;
    })
    .on('end', (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
      // defer reset so the click handler can still read isDragging
      setTimeout(() => { isDragging = false; }, 0);
    });
}

// ── node click ────────────────────────────────────────────────────────────────
function onNodeClick(event, d) {
  if (isDragging) return;
  if (!EXPANDABLE.has(d.type)) return;
  expandNode(d.type, d.data.tmdb_id, d.label);
}

// ── tooltip ───────────────────────────────────────────────────────────────────
function onMouseover(event, d) {
  document.getElementById('tooltip').innerHTML = buildTooltip(d);
  document.getElementById('tooltip').style.display = 'block';
  placeTooltip(event);

  // dim unconnected links
  linkGroup.selectAll('line').each(function(l) {
    const sid = nodeId(l.source), tid = nodeId(l.target);
    const connected = sid === d.id || tid === d.id;
    d3.select(this).classed('hi', connected).classed('dim', !connected);
  });
}

function onMouseout() {
  document.getElementById('tooltip').style.display = 'none';
  linkGroup.selectAll('line').classed('hi', false).classed('dim', false);
}

document.addEventListener('mousemove', e => {
  if (document.getElementById('tooltip').style.display !== 'none') placeTooltip(e);
});

function placeTooltip(event) {
  const tt = document.getElementById('tooltip');
  const x  = event.clientX + 16;
  const y  = event.clientY - 10;
  const flip = x + tt.offsetWidth > window.innerWidth;
  tt.style.left = (flip ? event.clientX - tt.offsetWidth - 16 : x) + 'px';
  tt.style.top  = Math.min(y, window.innerHeight - tt.offsetHeight - 8) + 'px';
}

function buildTooltip(d) {
  const dd = d.data || {};
  let h = `<div class="tt-type tt-${d.type}">${d.type.toUpperCase()}</div>`;
  h += `<div class="tt-name">${esc(d.label)}</div>`;

  if (d.type === 'movie' || d.type === 'tv') {
    const date = dd.release_date || dd.first_air_date || '';
    if (date)                h += ttRow('Year',    date.slice(0, 4));
    if (dd.vote_average)     h += ttRow('Rating',  dd.vote_average.toFixed(1) + ' / 10');
    if (dd.genres?.length)   h += ttRow('Genres',  dd.genres.join(', '));
    if (dd.number_of_seasons)h += ttRow('Seasons', dd.number_of_seasons);
    if (dd.overview) {
      const snip = dd.overview.slice(0, 160);
      h += `<div class="tt-overview">${esc(snip)}${dd.overview.length > 160 ? '…' : ''}</div>`;
    }
  } else if (d.type === 'person') {
    if (dd.known_for_department) h += ttRow('Known for', dd.known_for_department);
    if (dd.birthday)             h += ttRow('Born',      dd.birthday);
    h += '<div class="tt-hint">Click to expand credits</div>';
  } else if (d.type === 'company') {
    if (dd.origin_country) h += ttRow('Country', dd.origin_country);
    h += '<div class="tt-hint">Click to expand productions</div>';
  }
  return h;
}

function ttRow(label, value) {
  return `<div class="tt-row"><span class="tt-label">${esc(label)}:</span> ${esc(String(value))}</div>`;
}

// ── helpers ───────────────────────────────────────────────────────────────────
function nodeId(ref) {
  return typeof ref === 'object' ? ref.id : ref;
}

async function apiFetch(path) {
  const resp = await fetch(SERVER + path);
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.error || resp.statusText);
  }
  return resp.json();
}

function setStatus(msg, error = false) {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.style.color = error ? '#f87171' : '#475569';
}

function hideEmptyState() {
  document.getElementById('empty-state').style.display = 'none';
}

function esc(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
