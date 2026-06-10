'use strict';

// ── config ────────────────────────────────────────────────────────────────────
const SERVER     = 'http://localhost:5000';
const IMAGE_BASE = 'https://image.tmdb.org/t/p/w185';

const NODE_COLORS = {
  movie:   '#ef4444',
  tv:      '#8b5cf6',
  person:  '#22c55e',
  company: '#f97316',
};

const NODE_R     = 22;   // base circle radius
const CENTER_R   = 28;   // radius for the origin node
const EXPANDABLE = new Set(['person', 'company']);

// ── state ─────────────────────────────────────────────────────────────────────
let gNodes       = [];
let gLinks       = [];
let centerNodeId = null;

// ── D3 handles ────────────────────────────────────────────────────────────────
let simulation, svgDefs, zoomGroup, linkGroup, linkLabelGroup, nodeGroup;
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

  // <defs> for clipPaths
  svgDefs = svg.append('defs');

  // layer order: links behind nodes
  zoomGroup      = svg.append('g');
  linkGroup      = zoomGroup.append('g').attr('class', 'links');
  linkLabelGroup = zoomGroup.append('g').attr('class', 'link-labels');
  nodeGroup      = zoomGroup.append('g').attr('class', 'nodes');

  simulation = d3.forceSimulation([])
    .force('link',    d3.forceLink([]).id(d => d.id).distance(160))
    .force('charge',  d3.forceManyBody().strength(-600))
    .force('center',  d3.forceCenter(w / 2, h / 2))
    .force('collide', d3.forceCollide(NODE_R + 16));

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
  document.querySelectorAll('input[name="type"]').forEach(radio => {
    radio.addEventListener('change', () => {
      if (document.getElementById('search-input').value.trim()) doSearch();
    });
  });
}

async function doSearch() {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const type = document.querySelector('input[name="type"]:checked').value;

  setStatus('Searching…');
  clearResults();
  setResultsLoading(true);

  try {
    const data = await apiFetch(`/api/search?q=${encodeURIComponent(q)}&type=${type}`);
    renderResults(data.results || []);
    setStatus(`${(data.results || []).length} result(s) — select one to explore.`);
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  } finally {
    setResultsLoading(false);
  }
}

function clearResults() {
  document.getElementById('results-panel').innerHTML = '';
}

function setResultsLoading(on) {
  const el = document.getElementById('results-loading');
  if (on) {
    el.innerHTML = '<div class="mini-spinner"></div><span>Searching…</span>';
    el.classList.add('visible');
  } else {
    el.classList.remove('visible');
  }
}

function renderResults(results) {
  const panel = document.getElementById('results-panel');
  if (!results.length) {
    panel.innerHTML = '<div class="no-results">No results found.</div>';
    return;
  }
  panel.innerHTML = results.map((r, i) => {
    const year = (r.release_date || r.first_air_date || '').slice(0, 4) || 'n/a';
    const tag  = r.media_type === 'movie' ? 'movie' : 'tv';
    const rating = r.vote_average ? r.vote_average.toFixed(1) : null;
    const thumb  = r.poster_path
      ? `<img class="result-thumb" src="${IMAGE_BASE}${r.poster_path}" alt="" loading="lazy">`
      : `<div class="result-thumb-placeholder">${tag.toUpperCase()}</div>`;
    return `
      <div class="result-item" data-index="${i}">
        ${thumb}
        <div class="result-info">
          <span class="result-title">${esc(r.title)}</span>
          <span class="result-meta">
            <span class="rt-tag rt-${tag}">${tag}</span>${year}${rating ? `<span><span class="rating-star">★</span>${rating}</span>` : ''}
          </span>
        </div>
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
  // clear old clipPaths
  svgDefs.selectAll('clipPath').remove();
  updateGraph();
  hideEmptyState();
  setGraphLoading(true);
  setStatus(`Loading graph for “${title}”…`);

  try {
    const data = await apiFetch(`/api/graph/${mediaType}/${tmdbId}`);
    centerNodeId = data.center;
    mergeGraph(data);
    setStatus(`${gNodes.length} nodes · ${gLinks.length} edges — click a person or company to expand.`);
  } catch (err) {
    setStatus('Error: ' + err.message, true);
  } finally {
    setGraphLoading(false);
  }
}

function setGraphLoading(on) {
  document.getElementById('graph-loading').classList.toggle('visible', on);
}

// ── expand node ───────────────────────────────────────────────────────────────
async function expandNode(nodeType, nodeId, label) {
  setStatus(`Expanding “${label}”…`);
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
      node.x = cx + (Math.random() - 0.5) * 200;
      node.y = cy + (Math.random() - 0.5) * 200;
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

// ── image URL helper ──────────────────────────────────────────────────────────
function getImageUrl(node) {
  const d = node.data || {};
  if (node.type === 'person'  && d.profile_path) return IMAGE_BASE + d.profile_path;
  if (node.type === 'company' && d.logo_path)    return IMAGE_BASE + d.logo_path;
  if ((node.type === 'movie' || node.type === 'tv') && d.poster_path)
    return IMAGE_BASE + d.poster_path;
  return null;
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

      // bg filled circle
      g.append('circle').attr('class', 'node-bg');

      // initial letter fallback
      g.append('text').attr('class', 'node-initial');

      // clipped image
      g.append('image').attr('class', 'node-image');

      // stroke ring on top of image
      g.append('circle').attr('class', 'node-ring');

      // label below
      g.append('text').attr('class', 'node-label');

      g.call(makeDrag());
      g.on('click',     onNodeClick);
      g.on('mouseover', onMouseover);
      g.on('mouseout',  onMouseout);
      return g;
    });

  // ── update all node sub-elements ──
  nodeGroup.selectAll('g.node').each(function(d) {
    const g   = d3.select(this);
    const r   = d.id === centerNodeId ? CENTER_R : NODE_R;
    const col = NODE_COLORS[d.type] || '#64748b';
    const img = getImageUrl(d);
    const clipId = `clip-${d.id.replace(/[^a-z0-9]/gi, '_')}`;

    // ensure clipPath exists in defs
    if (img && svgDefs.select(`#${clipId}`).empty()) {
      svgDefs.append('clipPath')
        .attr('id', clipId)
        .append('circle')
        .attr('r', r);
    } else if (img) {
      // update radius in case it's the center node
      svgDefs.select(`#${clipId} circle`).attr('r', r);
    }

    // CSS custom property for glow color
    this.style.setProperty('--node-color', col);

    g.classed('is-center',     d.id === centerNodeId)
     .classed('is-expandable', EXPANDABLE.has(d.type) && d.id !== centerNodeId);

    g.select('.node-bg')
      .attr('r',            r)
      .attr('fill',         col)
      .attr('fill-opacity', img ? 0.35 : 1);

    g.select('.node-initial')
      .attr('font-size', Math.round(r * 0.7))
      .text(img ? '' : d.type[0].toUpperCase());

    if (img) {
      g.select('.node-image')
        .attr('href',        img)
        .attr('x',           -r)
        .attr('y',           -r)
        .attr('width',       r * 2)
        .attr('height',      r * 2)
        .attr('clip-path',   `url(#${clipId})`)
        .attr('preserveAspectRatio', 'xMidYMid slice')
        .on('error', function() {
          // image failed — hide it, show initial letter
          d3.select(this).attr('href', null);
          g.select('.node-bg').attr('fill-opacity', 1);
          g.select('.node-initial').text(d.type[0].toUpperCase());
        });
    } else {
      g.select('.node-image').attr('href', null);
    }

    g.select('.node-ring')
      .attr('r',            r)
      .attr('stroke',       d.id === centerNodeId ? '#ffffff' : col)
      .attr('stroke-width', d.id === centerNodeId ? 2.5 : 1.5)
      .attr('stroke-opacity', d.id === centerNodeId ? 1 : 0.6);

    const labelText = d.label.length > 18 ? d.label.slice(0, 16) + '…' : d.label;
    g.select('.node-label')
      .attr('y', r + 14)
      .text(labelText);
  });

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
  const dd  = d.data || {};
  const img = getImageUrl(d);
  let h = '';

  if (img) {
    h += `<img class="tt-thumb" src="${img}" alt="" loading="lazy">`;
  }

  h += `<div class="tt-type tt-${d.type}">${d.type.toUpperCase()}</div>`;
  h += `<div class="tt-name">${esc(d.label)}</div>`;

  if (d.type === 'movie' || d.type === 'tv') {
    const date = dd.release_date || dd.first_air_date || '';
    if (date)                 h += ttRow('Year',    date.slice(0, 4));
    if (dd.vote_average)      h += ttRow('Rating',  dd.vote_average.toFixed(1) + ' / 10');
    if (dd.genres?.length)    h += ttRow('Genres',  dd.genres.join(', '));
    if (dd.number_of_seasons) h += ttRow('Seasons', dd.number_of_seasons);
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
