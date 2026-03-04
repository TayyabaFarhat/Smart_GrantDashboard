/* ══════════════════════════════════════════════════════════
   CMACED Startup Intelligence Dashboard — script.js v3
   Superior University × ID92
   ══════════════════════════════════════════════════════════ */

'use strict';

// ── State ─────────────────────────────────────────────────
const S = {
  opps:       [],
  archive:    [],
  tab:        'all',
  query:      '',
  region:     '',
  types:      new Set(),
  sortBy:     'deadline',
  minScore:   0,
};

// ── DOM ───────────────────────────────────────────────────
const $id = id => document.getElementById(id);
const oppGrid    = $id('oppGrid');
const skeletons  = $id('skeletons');
const emptyState = $id('emptyState');
const searchInput= $id('searchInput');
const searchClear= $id('searchClear');
const modal      = $id('modal');
const modalInner = $id('modalInner');

// ── Init ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  bindAll();
  loadData();
  $id('footerBuild').textContent = 'Build ' + new Date().toISOString().slice(0,10);
});

// ── Theme ─────────────────────────────────────────────────
function initTheme() {
  const t = localStorage.getItem('cmaced-theme') || 'light';
  setTheme(t);
}
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  $id('sunIcon').style.display  = t === 'light' ? 'block' : 'none';
  $id('moonIcon').style.display = t === 'dark'  ? 'block' : 'none';
  localStorage.setItem('cmaced-theme', t);
}
$id('themeBtn').addEventListener('click', () => {
  const cur = document.documentElement.getAttribute('data-theme');
  setTheme(cur === 'light' ? 'dark' : 'light');
});

// ── Data ──────────────────────────────────────────────────
async function loadData() {
  try {
    const bust = '?b=' + Date.now();
    const [r1, r2] = await Promise.allSettled([
      fetch('data/opportunities.json' + bust),
      fetch('data/archive.json' + bust),
    ]);

    if (r1.status === 'fulfilled' && r1.value.ok) {
      const d = await r1.value.json();
      S.opps = Array.isArray(d) ? d : [];
    }
    if (r2.status === 'fulfilled' && r2.value.ok) {
      const d = await r2.value.json();
      S.archive = Array.isArray(d) ? d : [];
    }

    // If no data, use fallback
    if (S.opps.length === 0) S.opps = seedData();

  } catch (e) {
    console.warn('Using seed data:', e.message);
    S.opps = seedData();
  }

  showData();
}

function showData() {
  skeletons.style.display = 'none';
  oppGrid.style.display   = '';
  updateAll();
  setLiveStatus();
}

function setLiveStatus() {
  $id('liveText').textContent = 'Live · ' + new Date().toLocaleDateString('en-PK', {
    day:'numeric', month:'short',
  });
}

// ── Aggregate updates ─────────────────────────────────────
function updateAll() {
  updateHero();
  updateStatCards();
  render();
}

// ── Hero ──────────────────────────────────────────────────
function updateHero() {
  const { total, national, intl, closing, fresh } = computeCounts(S.opps);
  $id('hTotal').textContent   = total;
  $id('hNational').textContent= national;
  $id('hIntl').textContent    = intl;
  $id('hClosing').textContent = closing;
  $id('hUpdated').textContent = new Date().toLocaleDateString('en-PK',{
    day:'2-digit', month:'short', year:'numeric',
  });
}

// ── Stat Cards ────────────────────────────────────────────
function updateStatCards() {
  const { total, national, intl, closing, fresh } = computeCounts(S.opps);
  $id('scTotal').textContent   = total;
  $id('scNational').textContent= national;
  $id('scIntl').textContent    = intl;
  $id('scClosing').textContent = closing;
  $id('scNew').textContent     = fresh;
}

function computeCounts(pool) {
  const today = new Date();
  const in7   = new Date(today.getTime() + 7*86400e3);
  const in48  = new Date(today.getTime() - 48*36e5);
  return {
    total:    pool.length,
    national: pool.filter(o => o.region === 'national').length,
    intl:     pool.filter(o => o.region === 'international').length,
    closing:  pool.filter(o => { const d = o.deadline && new Date(o.deadline); return d && d>=today && d<=in7; }).length,
    fresh:    pool.filter(o => o.date_added && new Date(o.date_added) >= in48).length,
  };
}

// ── Filter & Sort ─────────────────────────────────────────
function getFiltered() {
  const today = new Date();
  const in7   = new Date(today.getTime() + 7*86400e3);
  const query = S.query.toLowerCase();

  let pool = S.tab === 'archive' ? S.archive : S.opps;

  // Tab
  if (S.tab === 'national')     pool = pool.filter(o => o.region === 'national');
  else if (S.tab === 'international') pool = pool.filter(o => o.region === 'international');
  else if (S.tab === 'closing') pool = pool.filter(o => {
    const d = o.deadline && new Date(o.deadline); return d && d>=today && d<=in7;
  });
  else if (['grant','competition','hackathon','accelerator','fellowship'].includes(S.tab))
    pool = pool.filter(o => o.type === S.tab);

  // Region radio
  if (S.region) pool = pool.filter(o => o.region === S.region);

  // Type checkboxes
  if (S.types.size > 0) pool = pool.filter(o => S.types.has(o.type));

  // Search
  if (query) pool = pool.filter(o =>
    [o.name, o.organization, o.description, o.requirements, o.country, o.type]
      .some(f => (f||'').toLowerCase().includes(query))
  );

  // Min credibility
  if (S.minScore > 0) pool = pool.filter(o => (o.credibility_score||0) >= S.minScore);

  // Sort
  const r = [...pool];
  if (S.sortBy === 'deadline') {
    r.sort((a,b) => {
      if (!a.deadline) return 1; if (!b.deadline) return -1;
      return new Date(a.deadline) - new Date(b.deadline);
    });
  } else if (S.sortBy === 'new') {
    r.sort((a,b) => new Date(b.date_added||0) - new Date(a.date_added||0));
  } else if (S.sortBy === 'prize') {
    r.sort((a,b) => parsePrize(b.prize) - parsePrize(a.prize));
  } else if (S.sortBy === 'credibility') {
    r.sort((a,b) => (b.credibility_score||0) - (a.credibility_score||0));
  }

  return r;
}

function parsePrize(s) {
  if (!s) return 0;
  const m = s.replace(/,/g,'').match(/[\d.]+/);
  return m ? parseFloat(m[0]) : 0;
}

// ── Render ────────────────────────────────────────────────
function render() {
  const data      = getFiltered();
  const isArchive = S.tab === 'archive';

  $id('tabMeta').textContent = `${data.length} result${data.length!==1?'s':''}`;

  if (data.length === 0) {
    oppGrid.style.display = 'none';
    emptyState.style.display = '';
    return;
  }
  emptyState.style.display = 'none';
  oppGrid.style.display = '';
  oppGrid.innerHTML = data.map((o,i) => buildCard(o, isArchive, i)).join('');

  // Card clicks
  oppGrid.querySelectorAll('.opp-card').forEach(c => {
    c.addEventListener('click', e => {
      if (e.target.closest('.btn-apply') || e.target.closest('.btn-src')) return;
      openModal(c.dataset.id, isArchive);
    });
  });
}

// ── Card builder ──────────────────────────────────────────
function buildCard(o, isArchive, idx) {
  const today = new Date();
  const in48  = new Date(today.getTime() - 48*36e5);
  const in7   = new Date(today.getTime() + 7*86400e3);
  const dl    = o.deadline ? new Date(o.deadline) : null;

  const isNew     = !isArchive && o.date_added && new Date(o.date_added) >= in48;
  const isClosing = !isArchive && dl && dl >= today && dl <= in7;
  const daysLeft  = dl ? Math.ceil((dl - today) / 86400e3) : null;

  const typeMap = {grant:'b-grant',competition:'b-comp',hackathon:'b-hack',accelerator:'b-accel',fellowship:'b-fellow'};
  const typeLabel = {grant:'Grant',competition:'Competition',hackathon:'Hackathon',accelerator:'Accelerator',fellowship:'Fellowship'};

  let cls = 'opp-card';
  if (o.type) cls += ` t-${o.type}`;
  if (o.region === 'national') cls += ' is-nat';
  if (isArchive) cls += ' is-arch';

  const typeBadge = `<span class="badge ${typeMap[o.type]||'b-accel'}">${typeLabel[o.type]||o.type}</span>`;

  const statusBadges = [
    isNew     ? `<span class="badge b-new">✦ New</span>` : '',
    isClosing ? `<span class="badge b-closing">⏳ Closing</span>` : '',
    o.region === 'national' ? `<span class="badge b-pk">🇵🇰 PK</span>` : '',
  ].filter(Boolean).join('');

  // Deadline chip
  const dlChip = isArchive
    ? `<span class="chip dl">📁 Archived</span>`
    : dl
      ? `<span class="chip dl${isClosing?' close':''}">${isClosing?'⏳':'📅'} ${fmtDate(dl)}${isClosing&&daysLeft>0?`<span class="cdl-countdown">${daysLeft}d</span>`:''}</span>`
      : '';

  const prizeChip = o.prize ? `<span class="chip prize">💰 ${esc(o.prize)}</span>` : '';
  const scoreChip = o.credibility_score ? `<span class="chip score">⭐ ${o.credibility_score}</span>` : '';

  const applyBtn = o.application_link
    ? `<a class="btn-apply" href="${esc(o.application_link)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">Apply ↗</a>`
    : '';
  const srcBtn = o.source_url
    ? `<a class="btn-src" href="${esc(o.source_url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()" title="View source">🔗</a>`
    : '';

  const delay = `animation-delay:${Math.min(idx*22,320)}ms`;

  return `
  <article class="${cls}" data-id="${esc(o.id)}" style="${delay}" tabindex="0"
    role="button" onkeydown="if(event.key==='Enter'||event.key===' ')this.click()">
    <div class="card-row1">
      <div class="card-badges">${typeBadge}${statusBadges}</div>
      <span class="card-region" title="${o.region==='national'?'Pakistan':'International'}">${o.region==='national'?'🇵🇰':'🌍'}</span>
    </div>
    <div>
      <div class="card-name">${esc(o.name||'Untitled')}</div>
      <div class="card-org">${esc(o.organization||'')}</div>
    </div>
    ${o.description ? `<p class="card-desc">${esc(o.description)}</p>` : ''}
    <div class="card-chips">${dlChip}${prizeChip}${scoreChip}</div>
    <div class="card-footer">
      <span class="card-src" title="${esc(o.source_url||'')}">${esc(domainOf(o.source_url))}</span>
      <div class="card-btns">${srcBtn}${applyBtn}</div>
    </div>
  </article>`;
}

// ── Modal ─────────────────────────────────────────────────
function openModal(id, isArchive) {
  const pool = isArchive ? S.archive : S.opps;
  const o = pool.find(x => x.id === id);
  if (!o) return;

  const dl    = o.deadline ? new Date(o.deadline) : null;
  const today = new Date();
  const in7   = new Date(today.getTime() + 7*86400e3);
  const isClosing = dl && dl >= today && dl <= in7;
  const daysLeft  = dl ? Math.ceil((dl - today)/86400e3) : null;
  const score     = o.credibility_score || 0;
  const typeMap   = {grant:'b-grant',competition:'b-comp',hackathon:'b-hack',accelerator:'b-accel',fellowship:'b-fellow'};
  const typeLabel = {grant:'Grant',competition:'Competition',hackathon:'Hackathon',accelerator:'Accelerator',fellowship:'Fellowship'};

  modalInner.innerHTML = `
    <div class="modal-top">
      <span class="badge ${typeMap[o.type]||'b-accel'}">${typeLabel[o.type]||o.type}</span>
      <span class="badge" style="background:var(--bg-2);color:var(--ink-3);border-color:var(--border-3)">${o.region==='national'?'🇵🇰 Pakistan':'🌍 International'}</span>
      ${isClosing?`<span class="badge b-closing">⏳ ${daysLeft}d left</span>`:''}
    </div>
    <h2 class="modal-h2">${esc(o.name||'')}</h2>
    <p class="modal-org">${esc(o.organization||'')}</p>
    ${score ? `
    <div class="modal-score">
      <div class="fp-label" style="white-space:nowrap">Credibility</div>
      <div class="score-bar"><div class="score-fill" style="width:${score}%"></div></div>
      <div class="score-label">${score}/100</div>
    </div>` : ''}
    <div class="modal-fields">
      ${mf('Deadline', dl ? fmtDate(dl) + (isClosing?' — closing soon':'') : 'Not specified')}
      ${mf('Prize / Funding', o.prize || 'Not specified')}
      ${mf('Country', o.country || 'Not specified')}
      ${mf('Region', o.region === 'national' ? '🇵🇰 Pakistan' : '🌍 International')}
      ${mf('Requirements', o.requirements || 'See official page', true)}
      ${mf('Date Added', o.date_added ? fmtDate(new Date(o.date_added)) : 'N/A')}
      ${o.source_url ? `
      <div class="mf full">
        <div class="mf-k">Official Source</div>
        <a class="mf-v mf-link" href="${esc(o.source_url)}" target="_blank" rel="noopener">${esc(o.source_url)}</a>
      </div>` : ''}
    </div>
    <div class="modal-actions">
      ${o.application_link
        ? `<a class="modal-apply" href="${esc(o.application_link)}" target="_blank" rel="noopener">Apply Now ↗</a>`
        : `<span style="font-size:13px;color:var(--ink-3);padding:12px 0">No direct link — check official source.</span>`
      }
      ${o.source_url
        ? `<a class="modal-src-btn" href="${esc(o.source_url)}" target="_blank" rel="noopener">🔗 Official Site</a>`
        : ''
      }
    </div>
  `;

  modal.classList.add('open');
  modal.setAttribute('aria-hidden','false');
  document.body.style.overflow = 'hidden';
}

function mf(label, value, full=false) {
  return `<div class="mf${full?' full':''}">
    <div class="mf-k">${label}</div>
    <div class="mf-v">${esc(value)}</div>
  </div>`;
}

function closeModal() {
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden','true');
  document.body.style.overflow = '';
}
$id('modalClose').addEventListener('click', closeModal);
$id('modalBg').addEventListener('click', closeModal);
document.addEventListener('keydown', e => { if (e.key==='Escape') closeModal(); });

// ── Event Binding ─────────────────────────────────────────
function bindAll() {
  // Tabs
  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      S.tab = btn.dataset.tab;
      render();
    });
  });

  // Search
  searchInput.addEventListener('input', e => {
    S.query = e.target.value;
    searchClear.classList.toggle('show', S.query.length > 0);
    render();
  });
  searchClear.addEventListener('click', () => {
    searchInput.value = ''; S.query = '';
    searchClear.classList.remove('show');
    searchInput.focus(); render();
  });

  // Region radios
  document.querySelectorAll('input[name="region"]').forEach(r => {
    r.addEventListener('change', e => { S.region = e.target.value; render(); });
  });

  // Type checkboxes
  document.querySelectorAll('input[name="type"]').forEach(c => {
    c.addEventListener('change', e => {
      if (e.target.checked) S.types.add(e.target.value);
      else S.types.delete(e.target.value);
      render();
    });
  });

  // Sort
  $id('sortSelect').addEventListener('change', e => { S.sortBy = e.target.value; render(); });

  // Credibility range
  $id('credRange').addEventListener('input', e => {
    S.minScore = +e.target.value;
    $id('credVal').textContent = e.target.value;
    render();
  });

  // Reset
  $id('resetBtn').addEventListener('click', resetAll);
  $id('emptyReset').addEventListener('click', resetAll);

  // Export
  $id('exportBtn').addEventListener('click', exportCSV);
  $id('footerExport').addEventListener('click', e => { e.preventDefault(); exportCSV(); });
}

function resetAll() {
  searchInput.value = ''; S.query = '';
  S.region = ''; S.types.clear(); S.sortBy = 'deadline'; S.minScore = 0;
  searchClear.classList.remove('show');
  document.querySelectorAll('input[name="region"]')[0].checked = true;
  document.querySelectorAll('input[name="type"]').forEach(c => c.checked = false);
  $id('sortSelect').value = 'deadline';
  $id('credRange').value = '0'; $id('credVal').textContent = '0';
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.querySelector('.tab[data-tab="all"]').classList.add('active');
  S.tab = 'all';
  render();
}

// ── CSV Export ────────────────────────────────────────────
function exportCSV() {
  const all = S.archive;
  if (!all.length) { alert('Archive is empty.'); return; }
  const keys = ['id','name','organization','type','country','region','deadline',
                 'prize','description','requirements','application_link',
                 'source_url','credibility_score','date_added','status'];
  const lines = [
    keys.join(','),
    ...all.map(o => keys.map(k => `"${(o[k]||'').toString().replace(/"/g,'""')}"`).join(',')),
  ];
  const blob = new Blob([lines.join('\n')], {type:'text/csv;charset=utf-8;'});
  const url  = URL.createObjectURL(blob);
  const a    = Object.assign(document.createElement('a'), {
    href:url, download:`cmaced-archive-${new Date().getFullYear()}.csv`
  });
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

// ── Helpers ───────────────────────────────────────────────
function esc(s) {
  return String(s||'')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#039;');
}
function fmtDate(d) {
  return d.toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
}
function domainOf(url) {
  try { return new URL(url).hostname.replace('www.',''); } catch { return url||''; }
}

// ── Seed Data (fallback) ──────────────────────────────────
function seedData() {
  const t = new Date();
  const d = n => new Date(t.getTime() + n*86400e3).toISOString().slice(0,10);
  const today = t.toISOString().slice(0,10);

  return [
    {
      id:'ignite-startup-fund', name:'Ignite Startup Fund',
      organization:'Ignite National Technology Fund', type:'grant',
      country:'Pakistan', region:'national', deadline:d(45),
      prize:'PKR 5–25 million',
      description:'Government fund for early-stage Pakistani tech startups with working prototypes.',
      requirements:'Registered Pakistan tech startup. Working prototype. Up to 3 years old.',
      application_link:'https://ignite.org.pk/programs/',
      source_url:'https://ignite.org.pk',
      credibility_score:100, date_added:d(-1), status:'Open'
    },
    {
      id:'plan9-incubator', name:'Plan9 Incubation Program',
      organization:'PITB – Punjab Information Technology Board', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(30),
      prize:'Office space + PKR 1M seed grant',
      description:'Punjab government-backed incubator for technology startups. Provides space, mentorship, and seed funding.',
      requirements:'Tech-based teams from Punjab. Pre-revenue or early revenue. Full-time commitment required.',
      application_link:'https://plan9.pitb.gov.pk',
      source_url:'https://plan9.pitb.gov.pk',
      credibility_score:95, date_added:d(-2), status:'Open'
    },
    {
      id:'nic-lahore', name:'National Incubation Center Lahore',
      organization:'NIC Lahore / STZA', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(20),
      prize:'USD 10,000 + mentorship',
      description:'Pakistan\'s flagship national incubation center offering 6-month intensive program for technology startups.',
      requirements:'Pakistani founders. Tech/innovation focused. Pitch presentation required.',
      application_link:'https://niclahore.com',
      source_url:'https://niclahore.com',
      credibility_score:95, date_added:d(-3), status:'Open'
    },
    {
      id:'hec-innovation', name:'HEC Innovation & Research Fund',
      organization:'Higher Education Commission Pakistan', type:'grant',
      country:'Pakistan', region:'national', deadline:d(35),
      prize:'PKR 2–10 million',
      description:'Competitive research and innovation grant for university-affiliated startups and researchers.',
      requirements:'Must be affiliated with a Pakistani HEC-recognized university.',
      application_link:'https://hec.gov.pk/english/services/faculty/NRPU/Pages/Default.aspx',
      source_url:'https://hec.gov.pk',
      credibility_score:90, date_added:d(-6), status:'Open'
    },
    {
      id:'pseb-ites', name:'PSEB IT Export Startup Support',
      organization:'Pakistan Software Export Board', type:'grant',
      country:'Pakistan', region:'national', deadline:d(18),
      prize:'PKR 3 million + export facilitation',
      description:'Support program for IT companies targeting international export markets.',
      requirements:'Must be PSEB registered. Targeting IT export markets.',
      application_link:'https://pseb.org.pk',
      source_url:'https://pseb.org.pk',
      credibility_score:90, date_added:d(-5), status:'Open'
    },
    {
      id:'cmaced-grant', name:'CMACED Internal Startup Grant',
      organization:'CMACED – Superior University', type:'grant',
      country:'Pakistan', region:'national', deadline:d(10),
      prize:'PKR 500,000',
      description:'Internal grant for currently enrolled Superior University students with startup ideas or working prototypes.',
      requirements:'Currently enrolled at Superior University. Working prototype preferred.',
      application_link:'https://superior.edu.pk',
      source_url:'https://superior.edu.pk',
      credibility_score:85, date_added:today, status:'Open'
    },
    {
      id:'lums-coe', name:'LUMS Centre for Entrepreneurship Program',
      organization:'LUMS', type:'accelerator',
      country:'Pakistan', region:'national', deadline:d(40),
      prize:'Mentorship + USD 5,000 seed',
      description:'Structured entrepreneurship acceleration program with access to LUMS alumni network and mentors.',
      requirements:'Pakistani university graduates or students. Business plan required.',
      application_link:'https://lums.edu.pk/centre-entrepreneurship',
      source_url:'https://lums.edu.pk',
      credibility_score:85, date_added:d(-7), status:'Open'
    },
    {
      id:'pm-youth-loan', name:'PM Youth Entrepreneurship Programme',
      organization:'Prime Minister Youth Program', type:'grant',
      country:'Pakistan', region:'national', deadline:d(55),
      prize:'PKR 0.5–7.5 million loan',
      description:'Federal government interest-reduced loan program for youth entrepreneurs aged 21–45.',
      requirements:'Pakistani national aged 21–45. Business plan or existing business.',
      application_link:'https://pmyp.gov.pk',
      source_url:'https://pmyp.gov.pk',
      credibility_score:95, date_added:d(-4), status:'Open'
    },
    {
      id:'yc', name:'Y Combinator Accelerator',
      organization:'Y Combinator', type:'accelerator',
      country:'USA', region:'international', deadline:d(60),
      prize:'USD 500,000',
      description:'The world\'s most prestigious startup accelerator. Equity-based. Open to founders from any country.',
      requirements:'Any stage, any country. Strong founding team. Online application open to Pakistan.',
      application_link:'https://www.ycombinator.com/apply',
      source_url:'https://www.ycombinator.com',
      credibility_score:100, date_added:d(-1), status:'Open'
    },
    {
      id:'hult-prize', name:'Hult Prize Global Competition',
      organization:'Hult Prize Foundation', type:'competition',
      country:'Global', region:'international', deadline:d(14),
      prize:'USD 1,000,000',
      description:'The Nobel Prize of student entrepreneurship. Annual global competition for university teams.',
      requirements:'University student teams. Social impact focus. Virtual application open worldwide.',
      application_link:'https://www.hultprize.org',
      source_url:'https://www.hultprize.org',
      credibility_score:90, date_added:today, status:'Open'
    },
    {
      id:'mit-solve', name:'MIT Solve Global Challenge',
      organization:'MIT Solve', type:'competition',
      country:'USA', region:'international', deadline:d(90),
      prize:'USD 10,000–150,000',
      description:'MIT-backed social impact challenge seeking technology-based solutions to global challenges.',
      requirements:'Social entrepreneurs worldwide. Online application accepted from Pakistan.',
      application_link:'https://solve.mit.edu',
      source_url:'https://solve.mit.edu',
      credibility_score:95, date_added:d(-4), status:'Open'
    },
    {
      id:'google-startups', name:'Google for Startups Accelerator',
      organization:'Google', type:'accelerator',
      country:'USA', region:'international', deadline:d(50),
      prize:'USD 100,000 in Cloud credits',
      description:'Equity-free accelerator for AI-first startups. Includes Google Cloud credits and expert mentorship.',
      requirements:'Series A or earlier. AI/ML focused preferred. Virtual participation available.',
      application_link:'https://startup.google.com/programs/accelerator/',
      source_url:'https://startup.google.com',
      credibility_score:95, date_added:d(-2), status:'Open'
    },
    {
      id:'msft-founders-hub', name:'Microsoft for Startups Founders Hub',
      organization:'Microsoft', type:'grant',
      country:'USA', region:'international', deadline:d(365),
      prize:'USD 150,000 in Azure credits',
      description:'No-equity support program offering Azure credits, GitHub, and Microsoft tools for startups.',
      requirements:'Pre-seed to Series A. No equity required. Pakistan-based startups welcome.',
      application_link:'https://www.microsoft.com/en-us/startups',
      source_url:'https://www.microsoft.com/en-us/startups',
      credibility_score:95, date_added:d(-5), status:'Open'
    },
    {
      id:'aws-activate', name:'AWS Activate for Startups',
      organization:'Amazon Web Services', type:'grant',
      country:'USA', region:'international', deadline:d(365),
      prize:'USD 5,000–100,000 in AWS credits',
      description:'AWS credits, technical support, and training for eligible startups at any stage.',
      requirements:'Incorporated startup. No equity taken. Open to Pakistani founders.',
      application_link:'https://aws.amazon.com/activate/',
      source_url:'https://aws.amazon.com/activate/',
      credibility_score:90, date_added:d(-3), status:'Open'
    },
    {
      id:'seedstars', name:'Seedstars World Competition',
      organization:'Seedstars World', type:'competition',
      country:'Switzerland', region:'international', deadline:d(25),
      prize:'USD 500,000 investment',
      description:'Global startup competition for emerging market entrepreneurs with local qualifying rounds.',
      requirements:'Early-stage tech startup. Local qualifying round followed by global summit.',
      application_link:'https://www.seedstars.com/programs/',
      source_url:'https://www.seedstars.com',
      credibility_score:88, date_added:d(-2), status:'Open'
    },
    {
      id:'masschallenge', name:'MassChallenge Global Accelerator',
      organization:'MassChallenge', type:'accelerator',
      country:'USA', region:'international', deadline:d(55),
      prize:'USD 250,000 equity-free',
      description:'Zero-equity global accelerator connecting high-impact startups with world-class mentors and resources.',
      requirements:'No equity taken. Open to international founders including Pakistan.',
      application_link:'https://masschallenge.org',
      source_url:'https://masschallenge.org',
      credibility_score:90, date_added:d(-4), status:'Open'
    },
    {
      id:'devpost-hackathons', name:'Devpost Global Hackathons',
      organization:'Devpost', type:'hackathon',
      country:'USA', region:'international', deadline:d(7),
      prize:'Varies per hackathon',
      description:'Official hackathon platform hosting global virtual competitions open to all nationalities.',
      requirements:'Virtual. Open to all nationalities. Individual or team submission.',
      application_link:'https://devpost.com/hackathons',
      source_url:'https://devpost.com',
      credibility_score:85, date_added:d(-1), status:'Open'
    },
    {
      id:'500-global', name:'500 Global Accelerator',
      organization:'500 Global', type:'accelerator',
      country:'USA', region:'international', deadline:d(42),
      prize:'USD 150,000 investment',
      description:'Early-stage VC fund and accelerator with global portfolio. Open to Pakistani founders.',
      requirements:'Early-stage startup. Online application. Open to all nationalities.',
      application_link:'https://500.co/accelerators',
      source_url:'https://500.co',
      credibility_score:90, date_added:d(-3), status:'Open'
    },
    {
      id:'plug-play', name:'Plug and Play Tech Center',
      organization:'Plug and Play', type:'accelerator',
      country:'USA', region:'international', deadline:d(70),
      prize:'Investment + USD 25,000',
      description:'Silicon Valley accelerator specializing in industry-specific programs. Global network of corporate partners.',
      requirements:'Series A or earlier. Sector-specific programs available. Online application.',
      application_link:'https://www.plugandplaytechcenter.com/select/',
      source_url:'https://www.plugandplaytechcenter.com',
      credibility_score:85, date_added:d(-6), status:'Open'
    },
    {
      id:'un-sdg-challenge', name:'UN SDG Innovation Challenge',
      organization:'United Nations', type:'competition',
      country:'Global', region:'international', deadline:d(80),
      prize:'USD 50,000–300,000',
      description:'UN challenge seeking technology solutions aligned with Sustainable Development Goals.',
      requirements:'Social ventures aligned with UN SDGs. Virtual application from any country.',
      application_link:'https://www.un.org/en/academic-impact/entrepreneurship',
      source_url:'https://www.un.org',
      credibility_score:90, date_added:d(-5), status:'Open'
    },
  ];
}
