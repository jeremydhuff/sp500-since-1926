/* ═══════════════════════════════════════════════════════════════════════
   S&P 500 composition by weight.  Reads window.MARKET (site/market.js, built by
   pipeline/04_build_dataset.py).
   Structure:
     1. DATA      helpers and the dataset
     2. DERIVE    bands for the current view (company or sector), stacking order
     3. LAYOUT    scales and band geometry
     4. Chart     one SVG renderer: grid, bands, topline, seams, annotations, labels, hover
     5. UI        strip, standfirst, legend, ledger, method and caveat panels, toggles
   Geometry: at each month the column is as tall as the index (log, linear, or a constant 100%);
   each band's thickness is its SHARE of the index times that height, so shares stay readable
   even though the top edge is on a log scale.
   Colours and type come from the CSS token block; the only inline colour is band identity.
   ═══════════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── 1 · DATA ───────────────────────────────────────────────────────── */
  const M = window.MARKET;
  if (!M) { document.body.textContent = 'market.js not found: run pipeline/04_build_dataset.py'; return; }
  const N = M.dates.length;
  const SVGNS = 'http://www.w3.org/2000/svg';
  const $ = (s, r) => (r || document).querySelector(s);
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const idxOf = (s) => M.dates.indexOf(s);
  const dlabel = (i) => { const p = M.dates[i].split('-'); return MONTHS[+p[1] - 1] + ' ' + p[0]; };
  const yearOf = (i) => +M.dates[i].slice(0, 4);
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const f1 = (v) => Math.round(v * 10) / 10;
  const money = (b) => b >= 1000 ? '$' + (b / 1000).toFixed(b >= 10000 ? 1 : 2) + 'T' : b >= 10 ? '$' + Math.round(b) + 'B' : '$' + b.toFixed(1) + 'B';
  const tickMoney = (v) => v >= 1000 ? '$' + +(v / 1000).toFixed(1) + 'T' : '$' + Math.round(v) + 'B';
  const pct = (x, d) => (x * 100).toFixed(d != null ? d : x >= 0.095 ? 1 : 2) + '%';
  const lum = (hex) => {
    const c = [1, 3, 5].map((k) => parseInt(hex.substr(k, 2), 16) / 255).map((v) => (v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)));
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  };
  const inkOn = (hex) => (lum(hex) > 0.34 ? '#0F1113' : '#FFFFFF');
  function svgEl(tag, attrs, parent, text) {
    const n = document.createElementNS(SVGNS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  function h(tag, attrs, parent, text) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  }
  const i1957 = Math.max(0, idxOf('1957-03'));
  const startOf = (from) => from === '1926' ? 0 : from === '1990' ? Math.max(0, idxOf('1990-01')) : from === '2010' ? Math.max(0, idxOf('2010-01')) : i1957;
  const last = N - 1;
  const compFrom = M.companies.length ? Math.min.apply(null, M.companies.map((c) => c.start)) : N;
  const WRDS = M.meta.companyTier === 'wrds';
  const sectorShare = (key) => (M.sectors.find((s) => s.key === key) || { share: null }).share;
  const state = {
    group: (N - compFrom) / (N - i1957) >= 0.6 ? 'companies' : 'sectors',
    axis: 'log', from: '1926', sel: last, hover: null, hoverBand: null, iso: null,
  };

  /* ── 2 · DERIVE ─────────────────────────────────────────────────────── */
  const TOP_N = 10, TOP_FADE = 13, TOP_SCALE = 1.5, TOP_MAX = 0.92;                           // company view: how many bands, and the months a band takes to fade in or out
  const topScale = () => state.axis === 'share' ? 1 : TOP_SCALE;   // the 100% view is a true-share view, so no enlargement there
  let D = null;
  function derive() {
    const i0 = startOf(state.from), top = M.topline, bands = [];
    if (state.group === 'companies') {
      for (const c of M.companies) {
        const v = M.caps[c.id], arr = new Float64Array(N);
        for (let k = 0; k < v.length; k++) arr[c.start + k] = v[k] || 0;
        bands.push({ id: c.id, name: c.name, short: c.short, color: c.color, arr });
      }
    } else {
      for (const s of M.sectors) {
        const arr = new Float64Array(N);
        for (let i = 0; i < N; i++) arr[i] = s.share[i] * top[i];
        bands.push({ id: s.key, name: s.name, short: s.name.toUpperCase(), color: s.color, arr });
      }
    }
    const companies = state.group === 'companies';
    if (companies) {                                          // the ten largest each month, faded in and out over TOP_FADE months
      const ind = bands.map(() => new Uint8Array(N)), order = bands.map((_, k) => k);
      for (let i = 0; i < N; i++) {
        order.sort((p, q) => bands[q].arr[i] - bands[p].arr[i]);
        for (let r = 0; r < TOP_N && bands[order[r]].arr[i] > 0; r++) ind[order[r]][i] = 1;
      }
      bands.forEach((b, k) => {
        const pre = new Float64Array(N + 1), half = TOP_FADE >> 1;
        for (let i = 0; i < N; i++) pre[i + 1] = pre[i] + ind[k][i];
        b.m = new Float32Array(N);
        for (let i = 0; i < N; i++) { const lo = Math.max(0, i - half), hi = Math.min(N - 1, i + half); b.m[i] = (pre[hi + 1] - pre[lo]) / (hi - lo + 1); }
      });
    }
    const keep = [];
    for (const b of bands) {
      let peak = 0, sw = 0, swi = 0, ever = !companies;
      b.share = new Float64Array(N); b.g = companies ? new Float64Array(N) : b.share;
      for (let i = i0; i < N; i++) {
        const s = clamp(b.arr[i] / top[i], 0, 1);
        b.share[i] = s;
        if (companies) { b.g[i] = s * b.m[i]; if (b.m[i] > 0 && b.arr[i] > 0) ever = true; sw += b.g[i]; swi += b.g[i] * i; if (b.m[i] >= 0.5 && s > peak) peak = s; }
        else { sw += s; swi += s * i; if (s > peak) peak = s; }
      }
      b.peak = peak; b.com = sw > 0 ? swi / sw : 1e9;
      if (ever && (companies ? sw > 0 : true)) keep.push(b);
    }
    keep.sort((a, b) => a.com - b.com);                       // older nearer the bottom
    if (companies) {                                          // TOP_SCALE multiplies the ten's drawn share (1 = true share); capped so a sliver of grey always remains
      for (let i = i0; i < N; i++) {
        let s = 0; for (const b of keep) s += b.g[i];
        const k = s > 0 ? Math.min(topScale(), TOP_MAX / s) : 1;
        for (const b of keep) b.g[i] *= k;
      }
    }
    if (companies) {                                          // the top ten sit on the baseline, everyone else above them
      const rest = { id: 'rest', name: 'Rest of the index', short: 'REST OF THE INDEX', color: '#DCDEE0', isRest: true,
        arr: new Float64Array(N), share: new Float64Array(N), g: new Float64Array(N), peak: 0, com: 1e9 };
      for (let i = i0; i < N; i++) {
        let sg = 0, sd = 0;
        for (const b of keep) { sg += b.g[i]; if (b.m[i] >= 0.5) sd += b.share[i]; }
        rest.g[i] = clamp(1 - sg, 0, 1); rest.share[i] = clamp(1 - sd, 0, 1); rest.arr[i] = rest.share[i] * top[i];
      }
      keep.push(rest);
    }
    let minT = Infinity, maxT = 0;
    for (let i = i0; i < N; i++) { minT = Math.min(minT, top[i]); maxT = Math.max(maxT, top[i]); }
    D = { i0, bands: keep, minT, maxT, top };
  }

  /* ── 3 · LAYOUT ─────────────────────────────────────────────────────── */
  const svg = $('#chart'), tip = $('#tip');
  let G = null;
  function layout() {
    const W = Math.max(320, svg.clientWidth || 1000);
    const H = Math.round(clamp(W * 0.48, 380, 560));
    const outside = W >= 560 && state.group === 'sectors';   // end-of-series name labels are a sector-view feature
    const m = { t: W < 560 ? 44 : 58, r: W >= 900 ? 118 : W >= 560 ? 100 : 12, b: 46, l: W < 560 ? 46 : 64 };
    if (outside) {                                            // room for the longest end label, its leader, and the end value
      const longest = Math.max.apply(null, D.bands.filter((b) => b.share[N - 1] > 0).map((b) => b.short.length).concat([0]));
      m.r = Math.round(clamp(longest * LABEL_CHAR + 30, m.r, W * 0.3));
    }
    const pw = W - m.l - m.r, ph = H - m.t - m.b, i0 = D.i0;
    const xs = (i) => m.l + ((i - i0) / (N - 1 - i0)) * pw;
    const Tmax = D.maxT * 1.06, lnT0 = Math.log(D.minT / 6), lnTm = Math.log(Tmax);
    const frac = (i) => state.axis === 'share' ? 1 : state.axis === 'linear' ? D.top[i] / Tmax : (Math.log(D.top[i]) - lnT0) / (lnTm - lnT0);
    const yBase = m.t + ph;
    const yVal = (v) => state.axis === 'linear' ? yBase - ph * v / Tmax : yBase - ph * (Math.log(v) - lnT0) / (lnTm - lnT0);
    G = { outside, W, H, m, pw, ph, xs, frac, yBase, yVal, Tmax, lnT0, lnTm };
    const cum = new Float64Array(N);
    for (const b of D.bands) {
      b.lo = new Float32Array(N); b.hi = new Float32Array(N); b.th = new Float32Array(N);
      for (let i = D.i0; i < N; i++) {
        const Hpx = frac(i) * ph;
        b.lo[i] = yBase - cum[i] * Hpx; cum[i] += b.g[i]; b.hi[i] = yBase - cum[i] * Hpx; b.th[i] = b.lo[i] - b.hi[i];
      }
    }
  }

  /* ── 4 · Chart ──────────────────────────────────────────────────────── */
  let xh, dot, paths = {}, labelEls = {};
  function bandPath(b) {                                     // one closed shape per run of months the band has thickness
    const p = [];
    let i = D.i0;
    while (i < N) {
      if (!(b.g[i] > 0)) { i++; continue; }
      let a = i; while (i < N && b.g[i] > 0) i++;
      let z = i - 1; a = Math.max(D.i0, a - 1); z = Math.min(N - 1, z + 1);
      p.push('M' + f1(G.xs(a)) + ',' + f1(b.hi[a]));
      for (let k = a + 1; k <= z; k++) p.push('L' + f1(G.xs(k)) + ',' + f1(b.hi[k]));
      for (let k = z; k >= a; k--) p.push('L' + f1(G.xs(k)) + ',' + f1(b.lo[k]));
      p.push('Z');
    }
    return p.length ? p.join('') : null;
  }
  function ticksY() {
    const out = [];
    if (state.axis === 'log') {
      const lo = Math.exp(G.lnT0);
      for (let e = 0; e <= 6; e++) for (const k of [1, 3]) {
        const v = k * Math.pow(10, e);
        if (v > lo * 1.15 && v < G.Tmax * 0.999) out.push({ y: G.yVal(v), label: tickMoney(v), minor: k === 3 });
      }
    } else if (state.axis === 'linear') {
      const step = [1e3, 2e3, 5e3, 1e4, 2e4, 2.5e4, 5e4].find((s) => G.Tmax / s <= 7) || 5e4;
      for (let v = step; v < G.Tmax; v += step) out.push({ y: G.yVal(v), label: tickMoney(v) });
    } else {
      for (const p of [0.25, 0.5, 0.75, 1]) out.push({ y: G.yBase - G.ph * p, label: Math.round(p * 100) + '%' });
    }
    return out;
  }
  function extreme(a, b, kind) {
    let best = idxOf(a);
    for (let i = idxOf(a); i <= idxOf(b); i++) if (kind === 'max' ? D.top[i] > D.top[best] : D.top[i] < D.top[best]) best = i;
    return best;
  }
  function annotationSpecs() {
    const dc = extreme('1999-01', '2001-12', 'max'), gfc = extreme('2008-06', '2009-12', 'min');
    if (state.from === '1926') {
      const p29 = extreme('1929-01', '1930-12', 'max'), t32 = extreme('1931-06', '1933-12', 'min');
      return [[p29, 'Pre-Depression peak'], [t32, 'Depression low'], [dc, 'Dot-com peak']];
    }
    return [[idxOf('1987-10'), 'Black Monday'], [dc, 'Dot-com peak'], [gfc, 'Financial crisis low']];
  }
  function placeAnnotations(root) {                          // two or three, placed clear of the line and of each other
    if (state.axis === 'share') return;
    const m = G.m, pts = [];
    for (let i = D.i0; i < N; i++) pts.push([G.xs(i), G.yVal(D.top[i])]);
    const placed = [];
    const gl = ticksY().map((t) => t.y).concat([G.yBase]);    // an annotation must fit BETWEEN two gridlines
    const seamX = seamIndices().map((i) => G.xs(i));         // ...and clear of the vertical seams
    const cands = [];
    for (let dy = -32; dy >= -150; dy -= 2) for (const [dx, anc] of [[-16, 'end'], [16, 'start'], [0, 'middle']]) cands.push([dx, dy, anc]);
    for (const [i, what] of annotationSpecs()) {
      if (i < D.i0) continue;
      const x = G.xs(i), y = G.yVal(D.top[i]);
      const val = money(D.top[i]), desc = what + ', ' + dlabel(i);
      const w = Math.max(val.length * 9, desc.length * 7) + 4;
      let pick = null;
      for (const [dx, dy, anc] of cands) {
        const tx = x + dx, ty = y + dy;
        const x0 = anc === 'end' ? tx - w : anc === 'middle' ? tx - w / 2 : tx, x1 = x0 + w, y0 = ty - 16, y1 = ty + 30;
        if (x0 < m.l + 2 || x1 > G.W - m.r || y0 < 10) continue;
        if (gl.some((g) => g > y0 - 4 && g < y1 + 4)) continue;
        if (seamX.some((sx) => sx > x0 - 6 && sx < x1 + 6)) continue;
        if (pts.some((p) => p[0] > x0 - 8 && p[0] < x1 + 8 && p[1] > y0 - 8 && p[1] < y1 + 8)) continue;
        if (placed.some((q) => x0 < q[1] + 8 && x1 > q[0] - 8 && y0 < q[3] + 8 && y1 > q[2] - 8)) continue;
        const lx0 = clamp(x, x0 + 4, x1 - 4), lb = [Math.min(x, lx0) - 4, Math.max(x, lx0) + 4, Math.min(y - 6, y1 + 2), Math.max(y - 6, y1 + 2)];
        if (placed.some((q) => lb[0] < q[1] && lb[1] > q[0] && lb[2] < q[3] && lb[3] > q[2])) continue;
        pick = { tx, ty, anc, x0, x1, y0, y1 }; break;
      }
      if (!pick) continue;                                   // better dropped than colliding
      placed.push([pick.x0, pick.x1, pick.y0, pick.y1]);
      const lx = clamp(x, pick.x0 + 4, pick.x1 - 4), ly = pick.y1 + 2;
      placed.push([Math.min(x, lx) - 4, Math.max(x, lx) + 4, Math.min(y - 6, ly), Math.max(y - 6, ly)]);   // the leader is an obstacle too
      svgEl('line', { class: 'leader', x1: f1(x), y1: f1(y - 6), x2: f1(lx), y2: f1(ly) }, root);
      svgEl('circle', { cx: f1(x), cy: f1(y), r: 4, fill: '#006E93' }, root);
      svgEl('text', { class: 'annv', x: f1(pick.tx), y: f1(pick.ty), 'text-anchor': pick.anc }, root, val);
      svgEl('text', { class: 'annd', x: f1(pick.tx), y: f1(pick.ty + 22), 'text-anchor': pick.anc }, root, desc);
    }
  }
  function seamIndices() {
    const s = [];
    if (state.group === 'companies' && compFrom > D.i0 && compFrom < N) s.push(compFrom);
    return s;
  }
  function draw() {
    derive(); layout();
    const { W, H, m } = G;
    svg.setAttribute('viewBox', '0 0 ' + W + ' ' + H); svg.setAttribute('height', H);
    svg.replaceChildren(); paths = {}; labelEls = {};
    const defs = svgEl('defs', {}, svg), cp = svgEl('clipPath', { id: 'plot-clip' }, defs);
    svgEl('rect', { x: m.l, y: 0, width: G.pw, height: G.yBase }, cp);
    const root = svgEl('g', { class: 'fade', opacity: REDUCED ? 1 : 0 }, svg);

    // horizontal hairlines only; they sit under the bands because they describe the top edge
    for (const t of ticksY()) {
      svgEl('line', { class: 'gridline', x1: m.l, x2: W - m.r, y1: f1(t.y), y2: f1(t.y), opacity: t.minor ? 0.5 : 1 }, root);
      svgEl('text', { class: 'tick', x: m.l - 12, y: f1(t.y) + 4.5, 'text-anchor': 'end' }, root, t.label);
    }
    svgEl('line', { class: 'zeroline', x1: m.l, x2: W - m.r, y1: G.yBase, y2: G.yBase }, root);
    svgEl('text', { class: 'cap', x: m.l - 4, y: m.t - 24 }, root,
      state.axis === 'share' ? 'Share of index market value' : 'Index market value · ' + (state.axis === 'log' ? 'log scale' : 'linear scale'));
    const ystep = yearOf(last) - yearOf(D.i0) < 25 ? 5 : 10, y0 = Math.ceil(yearOf(D.i0) / ystep) * ystep;
    for (let y = y0; y <= yearOf(last); y += ystep) {
      const i = M.dates.findIndex((d) => d.startsWith(y + '-01'));
      if (i >= D.i0) svgEl('text', { class: 'tick', x: f1(G.xs(i)), y: G.yBase + 24, 'text-anchor': 'middle' }, root, y);
    }

    // seams mark where the series definition changes; they sit under the bands so they read in the open space above the index line, not across the fills
    if (state.axis !== 'share') for (const si of seamIndices()) svgEl('line', { class: 'seam', x1: f1(G.xs(si)), x2: f1(G.xs(si)), y1: m.t - 6, y2: G.yBase }, root);
    const gb = svgEl('g', { 'clip-path': 'url(#plot-clip)' }, root);
    for (const b of D.bands) {
      const d = bandPath(b); if (!d) continue;
      paths[b.id] = svgEl('path', { d, fill: b.color, stroke: '#FFFFFF', 'stroke-width': 1, 'stroke-linejoin': 'round', class: 'band', 'data-id': b.id }, gb);
    }


    if (state.axis !== 'share') {                            // the signature move: weight = epistemic status
      const seg = (a, b, w, dash) => {
        let d = '';
        for (let i = a; i <= b; i++) d += (d ? 'L' : 'M') + f1(G.xs(i)) + ',' + f1(G.yVal(D.top[i]));
        svgEl('path', { d, fill: 'none', stroke: '#006E93', 'stroke-width': w, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'stroke-dasharray': dash || 'none' }, root);
      };
      if (D.i0 < i1957) { seg(D.i0, i1957, 2, '7 5'); seg(i1957, last, 3.4); } else seg(D.i0, last, 3.4);
      const ey = G.yVal(D.top[last]);
      svgEl('circle', { cx: f1(G.xs(last)), cy: f1(ey), r: 4, fill: '#006E93', stroke: '#FFFFFF', 'stroke-width': 1.5 }, root);
      if (W >= 560) {
        svgEl('text', { class: 'endv', x: f1(G.xs(last)) + 13, y: f1(ey) - 1 }, root, money(D.top[last]));
        svgEl('text', { class: 'endy', x: f1(G.xs(last)) + 13, y: f1(ey) + 18 }, root, dlabel(last));
      }
      placeAnnotations(root);
    }

    // wide screens: names sit past the last month, each tied to its band by a leader; narrow screens keep names inside the bands
    if (G.outside) endLabels(root); else if (state.group === 'sectors') inlineLabels(root);

    const over = svgEl('g', {}, root);
    xh = svgEl('line', { class: 'zeroline', y1: m.t - 6, y2: G.yBase, 'stroke-dasharray': '2 3', opacity: 0 }, over);
    dot = svgEl('circle', { r: 4.8, fill: '#FFFFFF', stroke: '#006E93', 'stroke-width': 2.4, opacity: 0 }, over);
    svg.setAttribute('aria-label', ariaSummary());
    if (!REDUCED) requestAnimationFrame(() => root.setAttribute('opacity', 1));
    applyDim(); renderAll();
  }
  const LABEL_LH = 14, LABEL_CHAR = 8.2;
  function endBands() {                                       // bands that exist in the last month, thickest first, as many as fit
    const reserve = state.axis === 'share' ? 6 : 34;
    const room = Math.floor((G.ph - reserve) / LABEL_LH);
    return D.bands.filter((b) => b.share[last] > 0).sort((a, b) => b.share[last] - a.share[last]).slice(0, Math.max(0, room));
  }
  function endLabels(root) {
    const bs = endBands(); if (!bs.length) return;
    const xe = G.xs(last), ey = G.yVal(D.top[last]);
    const items = bs.map((b) => ({ b, mid: (b.hi[last] + b.lo[last]) / 2 })).sort((p, q) => p.mid - q.mid);
    let lim = state.axis === 'share' ? G.m.t + 6 : ey + 34;
    for (const it of items) { it.y = Math.max(it.mid, lim); lim = it.y + LABEL_LH; }
    lim = G.yBase - 4;
    for (let k = items.length - 1; k >= 0; k--) { items[k].y = Math.min(items[k].y, lim); lim = items[k].y - LABEL_LH; }
    for (const it of items) {
      const y = f1(it.y), mid = f1(it.mid);
      svgEl('path', { class: 'bl-line', d: 'M' + f1(xe) + ',' + mid + 'L' + f1(xe + 14) + ',' + y + 'L' + f1(xe + 20) + ',' + y }, root);
      labelEls[it.b.id] = svgEl('text', { class: 'band-l out', x: f1(xe + 24), y: y + 4 }, root, it.b.short);
    }
  }
  function inlineLabels(root) {
    const dx = G.pw / (N - 1 - D.i0), sx = seamIndices().map((i) => G.xs(i)), topY = (j) => G.yVal(D.top[j]);
    const cand = [];
    for (const b of D.bands) {
      const minTh = (j) => (state.axis !== 'share' && b.hi[j] - topY(j) < 1 ? 26 : 18);   // the top band must clear the topline stroke
      let bestA = -1, bestL = 0, a = -1;
      for (let i = D.i0; i <= N; i++) {
        const ok = i < N && b.th[i] >= minTh(i);
        if (ok && a < 0) a = i;
        if (!ok && a >= 0) { if (i - a > bestL) { bestL = i - a; bestA = a; } a = -1; }
      }
      if (bestA < 0) continue;
      const tw = b.short.length * (G.W < 560 ? 6.4 : 7.4) + 14;
      if (bestL * dx < tw) continue;
      const half = Math.max(1, Math.round(tw / dx / 2));
      const lowC = Math.max(bestA + half, D.i0 + half), highC = Math.min(bestA + bestL - 1 - half, N - 1 - half);
      let ci = -1, bestMin = -1;
      for (let c = lowC; c <= highC; c++) {
        if (sx.some((x) => Math.abs(x - G.xs(c)) < tw / 2 + 4)) continue;           // never straddle a seam
        const yc = (b.hi[c] + b.lo[c]) / 2;
        if (state.axis !== 'share') { let hit = false; for (let j = Math.max(D.i0, c - half); j <= Math.min(N - 1, c + half); j++) if (Math.abs(topY(j) - yc) < 12) { hit = true; break; } if (hit) continue; }
        let mn = Infinity;
        for (let j = Math.max(D.i0, c - half); j <= Math.min(N - 1, c + half); j++) mn = Math.min(mn, b.th[j]);
        if (mn > bestMin) { bestMin = mn; ci = c; }
      }
      if (ci < 0) continue;
      cand.push({ b, ci, tw, x: G.xs(ci), y: (b.hi[ci] + b.lo[ci]) / 2 });
    }
    cand.sort((p, q) => q.b.peak - p.b.peak);              // bigger bands claim their label first
    const taken = [];
    for (const c of cand) {
      const x0 = c.x - c.tw / 2 - 2, x1 = c.x + c.tw / 2 + 2, y0 = c.y - 10, y1 = c.y + 10;
      if (taken.some((q) => x0 < q[1] && x1 > q[0] && y0 < q[3] && y1 > q[2])) continue;
      taken.push([x0, x1, y0, y1]);
      labelEls[c.b.id] = svgEl('text', { class: 'band-l', x: f1(c.x), y: f1(c.y) + 4, 'text-anchor': 'middle', fill: c.b.isRest ? '#5C636B' : inkOn(c.b.color) }, root, c.b.short);
    }
  }
  function ariaSummary() {
    const lead = D.bands.filter((b) => !b.isRest).sort((a, b) => b.arr[last] - a.arr[last]).slice(0, 3).map((b) => b.name + ' ' + pct(b.share[last])).join(', ');
    return 'Stacked area chart, ' + dlabel(D.i0) + ' to ' + dlabel(last) + ': the index grows from ' + money(D.top[D.i0]) + ' to ' + money(D.top[last]) +
      '; largest ' + (state.group === 'companies' ? 'companies' : 'sectors') + ' now ' + lead + '. Arrow keys move the date; the table below the chart follows.';
  }
  function applyDim() {
    const focus = state.iso || state.hoverBand;
    for (const id in paths) paths[id].style.opacity = !focus || id === focus ? 1 : (state.iso ? 0.16 : 0.5);
    for (const id in labelEls) labelEls[id].style.opacity = !state.iso || id === state.iso ? 1 : 0.3;
  }

  // readout: eight candidate slots, lowest score wins; never under the cursor, off the topline
  function placeTip(rect, mx, my, pts) {
    const bw = tip.offsetWidth, bh = tip.offsetHeight, GAP = 22, FALLBACK = 520;
    const cands = [[mx + GAP, my + GAP, 0], [mx - GAP - bw, my + GAP, 0], [mx + GAP, my - GAP - bh, 0], [mx - GAP - bw, my - GAP - bh, 0],
      [4, 4, FALLBACK], [rect.width - bw - 4, 4, FALLBACK], [4, rect.height - bh - 4, FALLBACK], [rect.width - bw - 4, rect.height - bh - 4, FALLBACK]];
    let best = [2, 2], bestScore = Infinity;
    for (const c of cands) {
      const x = Math.max(2, Math.min(c[0], rect.width - bw - 2)), y = Math.max(2, Math.min(c[1], rect.height - bh - 2));
      let sc = Math.abs(x - c[0]) * 0.6 + Math.abs(y - c[1]) * 0.6 + c[2];
      if (mx >= x - 6 && mx <= x + bw + 6 && my >= y - 6 && my <= y + bh + 6) sc += 1e5;
      let hits = 0; for (const p of pts) if (p.x >= x - 3 && p.x <= x + bw + 3 && p.y >= y - 3 && p.y <= y + bh + 3) hits++;
      sc += Math.min(hits, 40) * 11;
      if (sc < bestScore) { bestScore = sc; best = [x, y]; }
    }
    tip.style.left = best[0] + 'px'; tip.style.top = best[1] + 'px';
  }
  function bandsAt(i) { return D.bands.filter((b) => b.arr[i] > 0 && (!b.m || b.m[i] >= 0.5)).sort((a, b) => (a.isRest - b.isRest) || (b.arr[i] - a.arr[i])); }
  function basisNote(i) {
    const k = M.toplineKind[i];
    return k === 2 ? 'S&P 500 members' : (k === 1 || i < i1957) ? 'Pre-index · 500 largest US companies' : 'S&P 500 proxy · 500 largest by size';
  }
  function showTip(i, evt) {
    const rows = bandsAt(i), named = rows.filter((b) => !b.isRest), rest = rows.find((b) => b.isRest);
    let pick = named.slice(0, 8);
    const hb = state.hoverBand && named.find((b) => b.id === state.hoverBand);
    if (hb && pick.indexOf(hb) < 0) pick = pick.slice(0, 7).concat([hb]);
    tip.replaceChildren();
    h('div', { class: 'y' }, tip, dlabel(i));
    const only = state.group === 'companies' && state.iso ? D.bands.find((b) => b.id === state.iso) : null;   // a company is selected (clicked): show just that one
    const single = !!only;
    if (!single) h('div', { class: 'v' }, tip, money(D.top[i]));
    const tb = h('table', null, tip);
    const row = (b, name) => {
      const tr = h('tr', b && b.id === state.hoverBand ? { class: 'hot' } : null, tb), td = h('td', null, tr);
      const sw = h('i', null, td); sw.style.background = b ? b.color : '#DCDEE0';
      td.appendChild(document.createTextNode(name || b.name));
      h('td', null, tr, b && !(b.arr[i] > 0) ? '—' : money(b ? b.arr[i] : rest.arr[i]) + '  ' + pct(b ? b.share[i] : rest.share[i]));
    };
    if (single) row(only, only.isRest ? 'All other members' : null);
    else {
      pick.forEach((b) => row(b));
      if (rest && state.group === 'companies') row(null, named.length ? 'All other members' : 'Members, not itemised');
    }
    if (!single) h('div', { class: 'm' }, tip, state.group === 'sectors' ? 'Sector weights: all US listed firms' : basisNote(i));
    const box = svg.getBoundingClientRect(), wrap = svg.parentNode.getBoundingClientRect();
    const kx = box.width / G.W, ky = box.height / G.H, pts = [];
    if (state.axis !== 'share') for (let k = D.i0; k < N; k += 2) pts.push({ x: G.xs(k) * kx, y: G.yVal(D.top[k]) * ky });
    tip.classList.add('on'); tip.style.opacity = 1;
    placeTip({ width: box.width, height: box.height }, evt.clientX - box.left, evt.clientY - box.top, pts);
    tip.style.top = (parseFloat(tip.style.top) + box.top - wrap.top) + 'px';
    tip.style.left = (parseFloat(tip.style.left) + box.left - wrap.left) + 'px';
  }
  function inline(i) {
    const named = bandsAt(i).filter((b) => !b.isRest).slice(0, 3);
    const ro = $('#readout'); ro.replaceChildren();
    h('b', null, ro, dlabel(i)); ro.append('   ' + money(D.top[i]) + (named.length ? '   ' + named.map((b) => b.name + ' ' + pct(b.share[i])).join(', ') : ''));
  }
  function hideTip() { tip.classList.remove('on'); tip.style.opacity = 0; }
  function moveHover(i, evt) {
    state.hover = i;
    xh.setAttribute('x1', f1(G.xs(i))); xh.setAttribute('x2', f1(G.xs(i))); xh.setAttribute('opacity', 0.75);
    if (state.axis !== 'share') { dot.setAttribute('cx', f1(G.xs(i))); dot.setAttribute('cy', f1(G.yVal(D.top[i]))); dot.setAttribute('opacity', 1); } else dot.setAttribute('opacity', 0);
    if (G.W < 560) inline(i); else if (evt) showTip(i, evt);
    renderLedger(i);
  }
  function leaveHover() {
    state.hover = null; state.hoverBand = null;
    if (xh) { xh.setAttribute('opacity', 0); dot.setAttribute('opacity', 0); }
    hideTip(); applyDim(); renderLedger(state.sel); if (G && G.W < 560) inline(state.sel);
  }
  const idxFromEvent = (e) => {
    const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (G.W / r.width);
    return clamp(Math.round(D.i0 + ((px - G.m.l) / G.pw) * (N - 1 - D.i0)), D.i0, N - 1);
  };
  const inPlot = (e) => { const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (G.W / r.width); return px >= G.m.l - 2 && px <= G.W - G.m.r + 2; };
  // which band is under the pointer: worked out from the geometry, so the index line, labels and gridlines never intercept
  function bandAt(e) {
    const r = svg.getBoundingClientRect(), py = (e.clientY - r.top) * (G.H / r.height), i = idxFromEvent(e);
    let best = null, bd = Infinity;
    for (const b of D.bands) {
      if (!(b.g[i] > 0)) continue;
      const d = py < b.hi[i] ? b.hi[i] - py : py > b.lo[i] ? py - b.lo[i] : 0;
      if (d < bd) { bd = d; best = b; }
    }
    return best && bd <= 3 ? best.id : null;
  }
  svg.addEventListener('pointermove', (e) => {
    if (!G) return;
    if (!inPlot(e)) { leaveHover(); return; }
    const id = bandAt(e);
    svg.style.cursor = id ? 'pointer' : 'default';
    if (id !== state.hoverBand) { state.hoverBand = id; applyDim(); }
    moveHover(idxFromEvent(e), e);
  });
  svg.addEventListener('pointerleave', leaveHover);
  svg.addEventListener('click', (e) => {
    if (!inPlot(e)) return;
    const id = bandAt(e);
    state.sel = idxFromEvent(e);
    if (id) state.iso = state.iso === id ? null : id; else state.iso = null;
    applyDim(); renderKeys(); renderLedger(state.sel);
  });
  svg.addEventListener('touchmove', (e) => {
    if (!e.touches[0] || !inPlot(e.touches[0])) return;
    const t = e.touches[0]; moveHover(idxFromEvent(t), t); e.preventDefault();
  }, { passive: false });
  svg.addEventListener('keydown', (e) => {
    const step = e.shiftKey ? 12 : 1, cur = state.hover != null ? state.hover : state.sel;
    if (e.key === 'ArrowLeft') state.sel = clamp(cur - step, D.i0, last);
    else if (e.key === 'ArrowRight') state.sel = clamp(cur + step, D.i0, last);
    else if (e.key === 'Home') state.sel = D.i0; else if (e.key === 'End') state.sel = last;
    else if (e.key === 'Escape') { state.iso = null; applyDim(); renderKeys(); return; } else return;
    e.preventDefault();
    xh.setAttribute('x1', f1(G.xs(state.sel))); xh.setAttribute('x2', f1(G.xs(state.sel))); xh.setAttribute('opacity', 0.75);
    state.hover = null; renderLedger(state.sel); if (G.W < 560) inline(state.sel);
  });

  /* ── 5 · UI ─────────────────────────────────────────────────────────── */
  function peakShare(key, a, b) {
    const s = sectorShare(key); if (!s) return null;
    let j = a; for (let i = a; i <= b; i++) if (s[i] > s[j]) j = i;
    return { i: j, v: s[j] };
  }
  function renderStrip() {
    const st = $('#strip'); st.replaceChildren();
    const tech = peakShare('BusEq', idxOf('1995-01'), idxOf('2005-12')), en = peakShare('Enrgy', D.i0, last);
    const tNow = sectorShare('BusEq') && sectorShare('BusEq')[last], eNow = sectorShare('Enrgy') && sectorShare('Enrgy')[last];
    const items = [[money(D.top[last]), dlabel(last) + ' · index'], [money(D.top[D.i0]), yearOf(D.i0) + ' · index']];
    if (tNow != null) items.push([pct(tNow, 1), dlabel(last) + ' · technology share']);
    if (en) items.push([pct(en.v, 1), dlabel(en.i) + ' · energy peak']);
    for (const [v, l] of items) { const d = h('div', null, st); h('b', null, d, v); h('span', null, d, l); }
    return { tech, en, tNow, eNow };
  }
  function renderCopy(f) {
    $('#eyebrow').textContent = 'Monthly series · 500 largest US companies · ' + yearOf(D.i0) + ' to ' + yearOf(last);
    const s = state.group === 'companies' ? 'The 500 largest companies, with each month’s top 10 displayed' + (topScale() === 1 ? '.' : ' at a ' + Math.round(topScale() * 100) + '% scale.') : 'The 500 largest companies, weighted by market value each month.';
    $('#stand').textContent = s;
    $('#src').textContent = 'Month-end market value in nominal US dollars. Index total: the 500 largest US companies by size' + (WRDS ? ', replaced by actual S&P 500 members from March 1957' : '') +
      '. Sector weights: all listed US firms.' + (D.i0 < i1957 ? ' Dashed line: before the index existed.' : '') +
      (M.meta.crspLast ? ' CRSP data ends ' + dlabel(idxOf(M.meta.crspLast)) + '; later months carry that total forward at the size proxy’s growth, with company values from Yahoo Finance and SEC filings.' : '') + ' Sources: ' + (WRDS ? 'CRSP via WRDS; ' : '') + 'Kenneth R. French Data Library (CRSP-derived size and industry portfolios)' + (WRDS ? '' : '; Yahoo Finance prices; SEC EDGAR company facts') + '.';
    $('#foot').textContent = 'American Equity Explorer · data through ' + dlabel(last) + ' · built ' + M.meta.built;
    const lg = $('#legend'); lg.replaceChildren();
    if (state.axis !== 'share') {
      const a = h('span', null, lg); const i1 = h('i', null, a); i1.style.borderTopWidth = '3.4px'; a.append(WRDS ? 'Index total, S&P 500 members' : 'Index total, S&P 500 proxy');
      if (D.i0 < i1957) { const b = h('span', null, lg); const i2 = h('i', null, b); i2.style.borderTopWidth = '2px'; i2.style.borderTopStyle = 'dashed'; b.append('Before 1957: the 500 largest US companies'); }
    }
    const sm = state.axis === 'share' ? [] : seamIndices();
    if (sm.length) { const c = h('span', null, lg); h('i', { class: 'v' }, c); c.append(sm.map((i) => 'Company bands start, ' + dlabel(i)).join('; ')); }
  }
  function renderKeys() {
    const k = $('#keys'); k.replaceChildren();
    const named = D.bands.filter((b) => !b.isRest);
    const list = state.group === 'companies'
      ? named.filter((b) => b.id !== 'rjr-nabisco').sort((a, b) => (b.id === 'tesla') - (a.id === 'tesla') || b.peak - a.peak).slice(0, 16).sort((a, b) => (b.arr[last] - a.arr[last]) || (b.peak - a.peak))   // biggest today first
      : named.slice().sort((a, b) => a.com - b.com);
    for (const b of list) {
      const btn = h('button', { type: 'button', 'aria-pressed': String(state.iso === b.id) }, k);
      const sw = h('span', { class: 'sw' }, btn); sw.style.background = b.color; btn.append(b.name);
      btn.addEventListener('click', () => { state.iso = state.iso === b.id ? null : b.id; applyDim(); renderKeys(); renderLedger(state.hover != null ? state.hover : state.sel); });
    }
    if (state.group === 'companies') {                       // the grey remainder is selectable too
      const rb = D.bands.find((b) => b.isRest);
      if (rb) {
        const btn = h('button', { type: 'button', 'aria-pressed': String(state.iso === 'rest') }, k);
        const sw = h('span', { class: 'sw' }, btn); sw.style.background = rb.color; btn.append('All other companies');
        btn.addEventListener('click', () => { state.iso = state.iso === 'rest' ? null : 'rest'; applyDim(); renderKeys(); renderLedger(state.hover != null ? state.hover : state.sel); });
      }
    }
    if (state.group === 'companies' && named.length > list.length) h('span', { class: 'more' }, k, '+ ' + (named.length - list.length) + ' more that have been in the top ten');
  }
  function renderLedger(i) {
    if (i < D.i0) i = D.i0;
    $('#ledger-h').textContent = 'At ' + dlabel(i);
    const rows = bandsAt(i), named = rows.filter((b) => !b.isRest), rest = rows.find((b) => b.isRest);
    const ln = $('#ledger-line'); ln.replaceChildren();
    ln.append('Index '); h('b', null, ln, money(D.top[i]));
    if (named.length) { ln.append('. Largest ' + (state.group === 'companies' ? 'company' : 'sector') + ': '); h('b', null, ln, named[0].name); ln.append(', ' + pct(named[0].share[i]) + '.'); }
    else ln.append('. Company bands start in ' + dlabel(compFrom) + '; before that the index is not itemised.');
    const tb = $('#ledger'); tb.replaceChildren();
    const hr = h('tr', null, h('thead', null, tb));
    h('th', null, hr, '#'); h('th', null, hr, state.group === 'companies' ? 'Company' : 'Sector'); h('th', null, hr, 'Market value'); h('th', null, hr, 'Share');
    const body = h('tbody', null, tb);
    named.slice(0, 12).forEach((b, k) => {
      const tr = h('tr', null, body); h('td', null, tr, String(k + 1));
      const td = h('td', null, tr); const sw = h('span', { class: 'sw' }, td); sw.style.background = b.color; td.append(b.name);
      h('td', null, tr, money(b.arr[i])); h('td', null, tr, pct(b.share[i]));
    });
    if (state.group === 'companies') {
      const more = Math.max(0, named.length - 12), tr = h('tr', { class: 'rest' }, body); h('td', null, tr, '');
      const td = h('td', null, tr); const sw = h('span', { class: 'sw' }, td); sw.style.background = '#DCDEE0';
      td.append(named.length ? (more ? 'Everyone else (' + more + ' further bands)' : 'Everyone outside the top ten') : 'Index members, not itemised');
      h('td', null, tr, money(rest ? rest.arr[i] : D.top[i])); h('td', null, tr, pct(rest ? rest.share[i] : 1));
    }
  }
  function mathBlock(parent, xml, note) {
    const d = h('div', { class: 'eq' }, parent); d.innerHTML = '<math display="block">' + xml + '</math>'; h('p', { class: 'eqnote' }, parent, note);
  }
  function renderPanels() {
    $('#method-hint').textContent = '— three layers, and how the vertical axis is drawn';
    const mb = $('#method-body'); mb.replaceChildren();
    h('h3', null, mb, 'The index total');
    h('p', null, mb, 'Kenneth French’s data library publishes, for every month since 1926, the number of listed US firms in each size group and their average market value. Multiplying and summing gives the whole market; reading the groups from the largest down and pro-rating the last gives the 500 largest.');
    mathBlock(mb, '<mi>I</mi><mo>(</mo><mi>t</mi><mo>)</mo><mo>=</mo><munder><mo>∑</mo><mi>k</mi></munder><msub><mi>n</mi><mi>k</mi></msub><mo>⋅</mo><msub><mi>s</mi><mi>k</mi></msub>', 'nₖ firms in size group k, each worth sₖ on average, summed over the 500 largest.');
    const i87 = idxOf('1987-10'), i08 = idxOf('2008-10');
    if (i87 > 0 && i08 > 0) {
      const mv = (i) => Math.abs((M.topline[i] / M.topline[i - 1] - 1) * 100).toFixed(1);
      const q = h('p', null, mb); h('b', null, q, 'The crash test. ');
      q.append('The total falls ' + mv(i87) + '% in October 1987 and ' + mv(i08) + '% in October 2008; the S&P 500 price index fell 21.8% and 16.9%. Dividends and the committee’s choices explain the gap, not the method.');
    }
    h('h3', null, mb, 'Sector weights');
    h('p', null, mb, 'The same files, grouped into twelve Fama–French industries, give each industry’s share of all listed US market value. That share is applied to the index total, so a sector band is the market’s weight, not the index’s.');
    h('h3', null, mb, 'Company bands');
    h('p', null, mb, 'Only the ten largest companies in the index are drawn in any month, stacked from the baseline with everyone else above them. A company’s band is faded in and out with a 13-month moving average of “in the top ten”, so a company crossing the cut-off tapers rather than jumps; during that year its band is slightly thinner than its true share. On the log and linear views all ten are drawn at 1.5 times their share (less in the early decades, when they held most of the index and a strip of grey has to remain), so band thickness is not share there; the 100% view draws true shares; the readout and table show the true values.');
    h('p', null, mb, WRDS
      ? 'Monthly market value from CRSP, summed by company across share classes and counted only while the company is an index member. Names are matched to display companies by pattern; unmatched large companies fall into the grey remainder.'
      : 'Month-end price times shares outstanding for ' + M.companies.length + ' large companies that still trade, from ' + dlabel(compFrom) + '. Prices are daily Yahoo Finance closes, adjusted for splits only; share counts come from SEC filings (XBRL cover pages and balance sheets), restated to today’s split basis and interpolated between filings. The last count is tied to current market values.');
    h('h3', null, mb, 'The vertical axis');
    h('p', null, mb, 'On a log axis a band’s own height would stop meaning share. The column is therefore drawn as tall as the log of the index, then divided by true share:');
    mathBlock(mb, '<msub><mi>h</mi><mi>i</mi></msub><mo>(</mo><mi>t</mi><mo>)</mo><mo>=</mo><msub><mi>w</mi><mi>i</mi></msub><mo>(</mo><mi>t</mi><mo>)</mo><mo>⋅</mo><mi>ln</mi><mfrac><mrow><mi>I</mi><mo>(</mo><mi>t</mi><mo>)</mo></mrow><msub><mi>I</mi><mn>0</mn></msub></mfrac>', 'wᵢ the band’s share of the index; I₀ an axis floor set below the lowest value so every band has thickness.');

    const items = [
      WRDS ? ['Company bands depend on name matching.', 'Each CRSP company is mapped to a display name by pattern. A large company missing from the list sits in the grey remainder until it is added, which understates concentration in its years.']
        : ['Company bands are thin before ' + yearOf(compFrom) + '.', 'Only companies that still trade, and only from the first machine-readable SEC share counts, are itemised. AT&T’s monopoly years, General Motors before 2009 and Mobil are inside the grey remainder, so earlier decades look less concentrated than they were.'],
      WRDS ? ['Before March 1957 there was no S&P 500.', 'The earlier index total is the 500 largest US companies by size, shown with a dashed line.']
        : ['The index total is a size proxy, not the S&P 500.', 'It is the 500 largest US companies by size. It lands within a few percent of published totals at the checkpoints tested ($13.1T in Mar 2000, $42.0T at the end of 2021), but the committee’s choices, and the 1926–1956 period before the index existed, are not in it.'],
      ['Sector weights describe all listed US firms, not the index.', 'Small and mid-sized firms shift the mix; the error is likely largest for energy and finance in the 1970s and for technology after 1995.'],
      WRDS ? ['Share classes can differ in price.', 'CRSP sums classes at their own prices; companies with unlisted classes are counted only for the listed shares.']
        : ['Share counts are tied to current values at the end of the series, not throughout.', 'Eighty-nine of 90 last share counts agree with Yahoo’s live values within 10%. Mid-series counts rest on filings that sometimes carry unit slips; the pipeline repairs the unambiguous ones and leaves the rest. Prices are not adjusted for spin-offs, so a company’s value falls when it spins one off, as General Electric’s did in 2023–24. Berkshire’s share count is bridged between 2015 and today.'],
      ['Band thickness is not dollars.', 'On the log and 100% views the thickness is share times a height that changes with the index. Read dollars from the readout, or switch to the linear view, where thickness is dollars.'],
      ['Values are nominal.', 'Nothing is adjusted for inflation, so part of the climb on any view is the price level.'],
    ];
    $('#wrong-hint').textContent = '— ' + items.length + ' caveats, ordered by severity, and the sources';
    const wb = $('#wrong-body'); wb.replaceChildren();
    const ol = h('ol', null, wb);
    for (const [claim, text] of items) { const li = h('li', null, ol); h('b', null, li, claim + ' '); li.append(text); }
    const sb = h('div', { class: 'srcblock' }, wb);
    sb.textContent = 'Sources: ' + (WRDS ? 'CRSP monthly stock file and S&P 500 constituent list via WRDS; ' : '') + 'Kenneth R. French Data Library, size and 12-industry portfolios (CRSP-derived)' + (WRDS ? '' : '; Yahoo Finance daily prices; SEC EDGAR company facts (XBRL) and filings') + '; S&P Dow Jones Indices for the March 1957 launch date.';
    if (WRDS) h('p', null, sb, 'Wharton Research Data Services (WRDS) was used in preparing this chart. This service and the data available thereon constitute valuable intellectual property and trade secrets of WRDS and/or its third-party suppliers.');
  }
  function renderAll() {
    const f = renderStrip(); renderCopy(f); renderKeys(); renderLedger(state.hover != null ? state.hover : state.sel);
    if (G.W < 560) inline(state.hover != null ? state.hover : state.sel);
    renderPanels();
  }
  function syncControls() {
    document.querySelectorAll('#modeSwitch button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.val === state.group)));
    document.querySelectorAll('button.metric').forEach((b) => b.setAttribute('aria-pressed', String(state[b.dataset.key] === b.dataset.val)));
    const on = $('#modeSwitch button[aria-pressed="true"]'), ind = $('#modeIndicator');
    if (on) { ind.style.left = on.offsetLeft + 'px'; ind.style.width = on.offsetWidth + 'px'; }
  }
  document.querySelectorAll('#modeSwitch button').forEach((b) => b.addEventListener('click', () => { state.group = b.dataset.val; state.iso = null; syncControls(); redraw(); }));
  document.querySelectorAll('button.metric').forEach((b) => b.addEventListener('click', () => {
    state[b.dataset.key] = b.dataset.val;
    if (b.dataset.key === 'from') { state.iso = null; if (state.sel < startOf(state.from)) state.sel = last; }
    syncControls(); redraw();
  }));
  const HASH = {};
  location.hash.replace(/^#/, '').split('&').forEach((kv) => { const p = kv.split('='); if (p[0]) HASH[p[0]] = decodeURIComponent(p[1] || ''); });
  ['group', 'axis', 'from'].forEach((k) => { if (HASH[k]) state[k] = HASH[k]; });
  if (HASH.sel && idxOf(HASH.sel) >= 0) state.sel = idxOf(HASH.sel);
  if (HASH.iso) state.iso = HASH.iso;
  function redraw() { hideTip(); draw(); }
  let rt = null;
  window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(() => { syncControls(); redraw(); }, 120); });
  syncControls(); redraw();
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(syncControls);
  if (HASH.hover && idxOf(HASH.hover) >= 0) {
    if (HASH.band) { state.hoverBand = HASH.band; applyDim(); }
    const r = svg.getBoundingClientRect();
    moveHover(idxOf(HASH.hover), { clientX: r.left + G.xs(idxOf(HASH.hover)) * (r.width / G.W), clientY: r.top + r.height * 0.4 });
  }
})();
