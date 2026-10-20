const API_BASE = (window.WHERE_TO_OPEN_API_BASE_URL || 'https://where-to-open-cilr.onrender.com').replace(/\/$/, '');
const state = { guList: [], dongCache: new Map(), categories: [], activeView: 'compare' };

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
}[char]));

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, { method: 'GET', ...options });
  let body;
  try { body = await response.json(); } catch { body = null; }
  if (!response.ok) {
    const message = body?.error?.message || body?.detail?.[0]?.msg || `API 오류 (${response.status})`;
    throw new Error(message);
  }
  return body;
}

function setConnection(online, label) {
  const badge = $('#connection-state');
  badge.classList.toggle('is-online', online);
  badge.classList.toggle('is-offline', !online);
  $('#connection-label').textContent = label;
}

function showNotice(message, action = '') {
  const notice = $('#global-notice');
  notice.hidden = false;
  notice.innerHTML = `${escapeHtml(message)}${action ? ` <a href="${API_BASE}/docs" target="_blank" rel="noreferrer">API 문서 확인 ↗</a>` : ''}`;
}

function setBusy(button, busy, label) {
  button.disabled = busy;
  button.dataset.label = button.dataset.label || button.querySelector('span:first-child').textContent.trim();
  button.querySelector('span:first-child').textContent = busy ? label : button.dataset.label;
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '자료 없음';
  return Number(value).toLocaleString('ko-KR', { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPercent(value) {
  return value === null || value === undefined ? '자료 없음' : `${(Number(value) * 100).toFixed(1)}%`;
}

function basisLabel(value) {
  return ({ dong: '행정동 값', gu: '구 평균 대체', none: '기준 없음' })[value] || '';
}

async function updatePickers() {
  const count = Number($('#location-count').value);
  const host = $('#dong-pickers');
  const pendingLoads = [];
  const previous = $$('.dong-picker', host).map((row) => ({
    gu: $('.gu-select', row).value,
    code: $('.dong-select', row).value,
  }));
  host.replaceChildren();
  for (let index = 0; index < count; index += 1) {
    const previousValue = previous[index] || {};
    const row = document.createElement('div');
    row.className = 'dong-picker';
    row.innerHTML = `
      <span class="dong-picker-number">0${index + 1}</span>
      <div class="form-field"><label for="gu-${index}">자치구</label><select class="gu-select" id="gu-${index}" aria-label="후보 ${index + 1} 자치구"></select></div>
      <div class="form-field"><label for="dong-${index}">행정동</label><select class="dong-select" id="dong-${index}" aria-label="후보 ${index + 1} 행정동" disabled><option>목록 불러오는 중</option></select></div>`;
    host.append(row);
    const guSelect = $('.gu-select', row);
    const dongSelect = $('.dong-select', row);
    guSelect.innerHTML = state.guList.map((gu) => `<option value="${escapeHtml(gu)}">${escapeHtml(gu)}</option>`).join('');
    if (previousValue.gu && state.guList.includes(previousValue.gu)) guSelect.value = previousValue.gu;
    guSelect.addEventListener('change', () => fillDongSelect(guSelect, dongSelect));
    pendingLoads.push(fillDongSelect(guSelect, dongSelect, previousValue.code));
  }

  await Promise.all(pendingLoads);
  const usedCodes = new Set();
  $$('.dong-select', host).forEach((select) => {
    if (usedCodes.has(select.value)) {
      const alternative = [...select.options].find((option) => option.value && !usedCodes.has(option.value));
      if (alternative) select.value = alternative.value;
    }
    if (select.value) usedCodes.add(select.value);
  });
}

async function fillDongSelect(guSelect, dongSelect, preferredCode = '') {
  const gu = guSelect.value;
  dongSelect.disabled = true;
  dongSelect.innerHTML = '<option value="">행정동 불러오는 중</option>';
  try {
    if (!state.dongCache.has(gu)) {
      const result = await api(`/api/dongs?${new URLSearchParams({ gu, page: '1', size: '100' })}`);
      state.dongCache.set(gu, result.items || []);
    }
    const dongs = state.dongCache.get(gu);
    dongSelect.innerHTML = dongs.map((dong) => `<option value="${escapeHtml(dong.adm_cd)}">${escapeHtml(dong.name)}</option>`).join('');
    if (preferredCode && dongs.some((dong) => dong.adm_cd === preferredCode)) dongSelect.value = preferredCode;
    dongSelect.disabled = dongs.length === 0;
  } catch (error) {
    dongSelect.innerHTML = '<option value="">불러오지 못했습니다</option>';
    showNotice(`행정동 목록을 불러오지 못했습니다. ${error.message}`, true);
    setConnection(false, 'API 연결 확인 필요');
  }
}

function metricCell(main, sub = '', bar = null) {
  const barMarkup = bar === null ? '' : `<div class="bar-track"><span class="bar-fill" style="width:${Math.max(0, Math.min(100, bar))}%"></span></div>`;
  return `<div class="metric-cell"><span class="metric-main">${escapeHtml(main)}</span>${sub ? `<span class="metric-sub">${escapeHtml(sub)}</span>` : ''}${barMarkup}</div>`;
}

// 비교 지표 설명. 숫자의 정의와 읽는 법 (docs/common-rules.md, docs/db-tables.md 기준)
const HELP = {
  competition: '같은 업종 가게가 동네에 얼마나 빽빽한지 봅니다. 높을수록 경쟁이 셉니다. 다만 사람이 많이 모이는 곳이라 높을 수도 있으니 수요와 같이 보세요.',
  density: '기준일(2026-09-30)에 영업 중인 이 업종 가게 수 ÷ 행정동 면적(km²). 크기가 다른 동네끼리 비교하려고 면적으로 나눴습니다. 막대는 지금 비교하는 동네 중 가장 높은 값을 끝으로 한 길이입니다.',
  rank: '서울 427개 행정동 중 이 업종 밀도 순위입니다. 1위가 가장 빽빽합니다. 서울 평균은 427개 동의 밀도를 단순 평균한 값이라, 평균보다 크면 보통 동네보다 경쟁이 센 편입니다.',
  stability: '이 업종 가게가 이 동네에서 오래 버티는지, 얼마나 자주 바뀌는지 봅니다. 계산에 쓰는 가게가 20곳 미만이면 비율이 크게 흔들려 같은 구의 값을 쓰고 ‘구 평균 대체’라고 표시합니다.',
  survival: '3~8년 전에 문을 연 가게 중 3년 이상 영업했거나 지금도 영업 중인 비율입니다. 높을수록 이 업종이 이 동네에서 오래 버팁니다. 사업자가 아니라 가게(인허가) 단위라 통계청 생존율보다 높게 나옵니다.',
  turnover: '최근 1년 폐업 수 ÷ 1년 전 영업 중이던 가게 수입니다. 높을수록 가게가 자주 바뀝니다. 신규율과 같이 보세요: 둘 다 높으면 들고 나는 게 활발한 상권, 교체율만 높으면 빠지는 상권입니다.',
  newRate: '최근 1년 새로 문을 연 가게 수 ÷ 1년 전 영업 중이던 가게 수입니다. 교체율보다 높으면 닫는 가게보다 들어오는 가게가 많은 동네입니다.',
  site: '같은 지번(층·호 구분 없음)에 최근 10년 동안 가게가 얼마나 자주 바뀌었는지 봅니다. 업종을 바꿔도 같은 값이며, 일반음식점·휴게음식점·제과점을 모두 셉니다. 특정 주소는 ‘자리 상세’에서 볼 수 있습니다.',
  siteCount: '최근 10년 동안 일반음식점·휴게음식점·제과점이 한 번이라도 영업한 지번 수입니다. 동네에 가게 자리가 얼마나 많은지 보는 값입니다.',
  single: '가게가 한 곳만 들어가는 자리가 최근 10년 동안 맞은 새 가게 수의 평균입니다. 주인만 바뀐 같은 상호는 한 가게로 셉니다. 높을수록 자리가 자주 바뀌는 동네입니다.',
  perSlot: '여러 가게가 들어가는 건물까지 포함해, 자리마다 10년 새 가게 수를 동시에 영업한 최대 가게 수로 나눈 값의 평균입니다. 큰 건물과 작은 가게 자리를 같은 눈높이로 비교하려는 값입니다.',
  demand: '동네 안 지하철역으로 사람이 얼마나, 언제 오가는지 봅니다. 역이 없는 동네는 비어 있습니다. 버스와 생활인구는 포함하지 않습니다.',
  stations: '역별 하루 평균 승차+하차 인원(2024-09~2026-09)입니다. 한 사람이 타고 내리면 두 번 세서 유동인구와 다릅니다. 오전 하차(07~09시)가 많으면 일하러 오는 사람이 많은 동네, 저녁 하차(18~20시)는 저녁에 모이는 사람, 밤 승차(22~23시)는 늦게까지 머무는 사람이 많은 동네입니다.',
};

function helpIcon(text, name) {
  return text ? `<button class="help" type="button" aria-label="${escapeHtml(name)} 설명" data-tip="${escapeHtml(text)}">?</button>` : '';
}

function makeAxis(title, key, rows, candidateCount, help = '') {
  const body = rows.map((row) => `
    <div class="metric-grid" style="--candidate-count:${candidateCount}">
      <div class="metric-label"><span class="metric-name">${row.label}${helpIcon(row.help, row.label)}</span>${row.caption ? `<span class="metric-caption">${row.caption}</span>` : ''}</div>
      ${row.cells.join('')}
    </div>`).join('');
  return `<section class="metric-section" data-axis="${key}"><h3 class="metric-section-title">${title}${helpIcon(help, title)}</h3>${body}</section>`;
}

// 말풍선 하나를 화면에 고정해 두고 아이콘 옆에 띄운다. 마우스는 올리면, 터치·키보드는 누르거나 초점이 가면 보임
const helpTip = document.createElement('div');
helpTip.id = 'help-tip';
helpTip.setAttribute('role', 'tooltip');
helpTip.hidden = true;
document.body.append(helpTip);
function showHelp(button) {
  helpTip.textContent = button.dataset.tip;
  helpTip.style.left = '0px'; // 이전 위치 때문에 폭이 줄어든 채로 재지 않게
  helpTip.style.top = '0px';
  helpTip.hidden = false;
  const box = button.getBoundingClientRect();
  const left = Math.min(Math.max(8, box.left), innerWidth - helpTip.offsetWidth - 8);
  const below = box.bottom + 8;
  const top = below + helpTip.offsetHeight > innerHeight - 8 ? box.top - helpTip.offsetHeight - 8 : below;
  helpTip.style.left = `${left}px`;
  helpTip.style.top = `${Math.max(8, top)}px`;
}
let pinnedHelp = null; // 누르거나 탭해서 연 말풍선은 다른 곳을 누를 때까지 둔다
function hideHelp() { helpTip.hidden = true; pinnedHelp = null; }
document.addEventListener('pointerover', (event) => {
  const b = event.target.closest('.help');
  if (b && event.pointerType === 'mouse') showHelp(b);
});
document.addEventListener('pointerout', (event) => {
  if (event.pointerType !== 'mouse' || pinnedHelp || !event.target.closest('.help')) return;
  if (!event.relatedTarget?.closest?.('.help')) hideHelp();
});
document.addEventListener('focusin', (event) => {
  const b = event.target.closest('.help');
  if (b && b.matches(':focus-visible')) showHelp(b); // 키보드로 이동했을 때
});
document.addEventListener('focusout', (event) => { if (event.target.closest('.help') && !pinnedHelp) hideHelp(); });
document.addEventListener('click', (event) => {
  const b = event.target.closest('.help');
  if (!b) { hideHelp(); return; }
  event.preventDefault();
  if (pinnedHelp === b) { hideHelp(); return; }
  showHelp(b);
  pinnedHelp = b;
});
addEventListener('scroll', hideHelp, { passive: true, capture: true });
document.addEventListener('keydown', (event) => { if (event.key === 'Escape') hideHelp(); });

function renderDemand(report) {
  const stations = report?.demand?.stations || [];
  if (!stations.length) return '<span class="axis-empty">연결된 역 수요 자료가 없습니다.</span>';
  return `<div class="station-stack">${stations.slice(0, 3).map((station) => `
    <div class="station-item"><span class="station-name">${escapeHtml(station.station_name)}</span>
      <small>평일 ${formatNumber(station.weekday_daily_riders)}명 · 주말 ${formatNumber(station.weekend_daily_riders)}명</small>
      <small>오전 하차 ${formatNumber(station.morning_alighting)}명 · 저녁 하차 ${formatNumber(station.evening_alighting)}명</small>
      <small>밤 승차 ${formatNumber(station.night_boarding)}명</small>
    </div>`).join('')}</div>`;
}

function renderComparison(items) {
  const host = $('#compare-results');
  const headings = `<div class="comparison-head" style="--candidate-count:${items.length}"><div class="head-label">비교 항목</div>${items.map((item) => `
    <div><span class="head-label">${escapeHtml(item.dong.gu)}</span><strong class="district-title">${escapeHtml(item.dong.name)}</strong><span class="district-meta">${formatNumber(item.dong.area_km2, 2)} km²</span></div>`).join('')}</div>`;
  const competition = makeAxis('경쟁 · 같은 업종이 얼마나 밀집해 있나', 'competition', [
    { label: '점포 밀도', caption: '개 / km²', help: HELP.density, cells: items.map((item) => {
      const value = item.competition?.density_per_km2;
      const max = Math.max(1, ...items.map((candidate) => candidate.competition?.density_per_km2 || 0));
      return metricCell(value == null ? '자료 없음' : `${formatNumber(value, 1)}개`, `${formatNumber(item.competition?.open_count)}곳 영업 중`, value == null ? null : (value / max) * 100);
    }) },
    { label: '서울 내 밀도 비교', help: HELP.rank, cells: items.map((item) => item.competition ? metricCell(`${formatNumber(item.competition.seoul_rank)} / ${formatNumber(item.competition.seoul_dong_count)}위`, `서울 평균 ${formatNumber(item.competition.seoul_avg_density, 1)}개/km²`) : metricCell('자료 없음')) },
  ], items.length, HELP.competition);
  const stability = makeAxis('안정성 · 버팀과 교체 흐름', 'stability', [
    { label: '3년 생존율', help: HELP.survival, cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.survival_3y), basisLabel(item.stability.survival_basis)) : metricCell('자료 없음')) },
    { label: '교체율', help: HELP.turnover, cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.turnover_rate), basisLabel(item.stability.turnover_basis)) : metricCell('자료 없음')) },
    { label: '신규율', help: HELP.newRate, cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.new_rate), basisLabel(item.stability.new_rate_basis)) : metricCell('자료 없음')) },
  ], items.length, HELP.stability);
  const site = makeAxis('자리 · 같은 지번의 최근 10년', 'site', [
    { label: '자리 수', help: HELP.siteCount, cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.site_count)}곳`, '10년 이력 보유 주소') : metricCell('자료 없음')) },
    { label: '단독 자리 10년 새 가게', help: HELP.single, cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.avg_single_permits_10y, 2)}곳`, '가게 한 곳짜리 자리 평균') : metricCell('자료 없음')) },
    { label: '한 칸당 평균 교체', help: HELP.perSlot, cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.avg_per_slot_10y, 2)}회`, '10년 새 가게 ÷ 동시 영업 수') : metricCell('자료 없음')) },
  ], items.length, HELP.site);
  const demand = makeAxis('수요 · 오전, 저녁, 밤', 'demand', [
    { label: '연결 역별 승하차', caption: '하루 평균 · 최대 3개 역', help: HELP.stations, cells: items.map((item) => `<div class="metric-cell">${renderDemand(item)}</div>`) },
  ], items.length, HELP.demand);
  host.innerHTML = `<div class="comparison" style="--candidate-count:${items.length}">${headings}${competition}${stability}${site}${demand}</div>`;
  $('#results-heading').hidden = false;
}

function renderSite(site, dongName = '') {
  const history = site.history || [];
  const comp = site.dong_competition;
  const dongLine = comp ? `<p class="form-hint site-dong-line">${escapeHtml(dongName || '이 행정동')} ${escapeHtml(site.category?.name || '')} 밀도 ${formatNumber(comp.density_per_km2, 1)}개/km² · 서울 ${formatNumber(comp.seoul_rank)} / ${formatNumber(comp.seoul_dong_count)}위 · 서울 평균 ${formatNumber(comp.seoul_avg_density, 1)}개/km²</p>` : '';
  $('#site-result').innerHTML = `
    <article class="site-card">
      <header class="site-card-top"><div><p class="eyebrow">${escapeHtml(site.gu)} · ${escapeHtml(dongName || site.adm_cd || '행정동 미상')}</p><h2>${escapeHtml(site.site_key)}</h2><p>지번 기준 · 층·호 구분 없음</p>${dongLine}</div><span class="site-id-badge">SITE ${formatNumber(site.id)}</span></header>
      <div class="site-metrics">
        <div class="site-metric"><span class="site-metric-label">10년 새 가게</span><strong>${formatNumber(site.permits_10y)}곳</strong>${site.max_concurrent === 1 && site.dong_avg_single != null ? `<small class="metric-sub">동 평균 ${formatNumber(site.dong_avg_single, 2)}곳 (가게 한 곳짜리 자리)</small>` : ''}</div>
        <div class="site-metric"><span class="site-metric-label">한 칸당 교체</span><strong>${formatNumber(site.per_slot_10y, 2)}회</strong>${site.max_concurrent > 1 && site.dong_avg_per_slot != null ? `<small class="metric-sub">동 평균 ${formatNumber(site.dong_avg_per_slot, 2)}회</small>` : ''}</div>
        <div class="site-metric"><span class="site-metric-label">현재 영업</span><strong>${formatNumber(site.open_now)}곳</strong></div>
        <div class="site-metric"><span class="site-metric-label">폐업 업소 평균 영업</span><strong>${site.avg_months_closed == null ? '자료 없음' : `${formatNumber(site.avg_months_closed, 1)}개월`}</strong></div>
      </div>
      <div class="history-wrap"><h3>이 주소의 업소 이력 <span class="metric-caption">${formatNumber(history.length)}건</span></h3>
        ${history.length ? `<table class="history-table"><thead><tr><th>상호</th><th>업태</th><th>개업</th><th>폐업</th><th>영업 개월</th><th>합쳐진 허가</th></tr></thead><tbody>${history.map((item) => `<tr><td>${escapeHtml(item.name)}</td><td>${escapeHtml(item.uptae || '—')}</td><td>${escapeHtml(item.open_date)}</td><td>${escapeHtml(item.close_date || '영업 중')}</td><td>${formatNumber(item.months)}</td><td>${formatNumber(item.merged)}</td></tr>`).join('')}</tbody></table>` : '<p class="form-hint">업소 이력이 없습니다.</p>'}
      </div>
    </article>`;
}

function renderOverview(data) {
  $('#base-date-heading').textContent = data.base_date.replaceAll('-', '.');
  const host = $('#data-result');
  const summary = (data.record_counts || []).filter((row) => ['dong', 'competition_stat', 'stability_stat', 'subway_station_stat', 'site', 'site_store'].includes(row.table));
  const sources = data.sources || [];
  host.innerHTML = `
    <div class="data-summary">${summary.map((row) => `<div class="data-summary-item"><span>${escapeHtml(row.dataset)}</span><strong>${formatNumber(row.records)}</strong></div>`).join('')}</div>
    <section class="data-section"><h2>데이터 출처</h2><div class="source-list">${sources.map((source) => `<div class="source-row"><strong>${escapeHtml(source.name)}</strong><span>${escapeHtml(source.provider)}</span><span>${escapeHtml(source.axis)}</span><a href="${escapeHtml(source.url)}" target="_blank" rel="noreferrer">${escapeHtml(source.url)}</a></div>`).join('')}</div></section>
    <section class="data-section"><h2>지표 정의</h2><div class="definition-list">${(data.metric_definitions || []).map((definition) => `<div class="definition-row"><strong>${escapeHtml(definition.axis)} · ${escapeHtml(definition.metric)}</strong><span>${escapeHtml(definition.definition)}</span></div>`).join('')}</div></section>
    <p class="form-hint policy-note">${escapeHtml(data.score_policy)}</p>`;
}

async function loadPipeline() {
  const response = await api('/api/data/pipeline');
  const host = $('#pipeline-result');
  host.innerHTML = (response.stages || []).map((stage, index) => `<div class="pipeline-step"><span class="pipeline-step-index">0${index + 1}</span><strong>${escapeHtml(stage.name)}</strong><p>${escapeHtml(stage.description)}</p><small>${escapeHtml(stage.status === 'not_tracked' ? '실행 상태 미추적' : stage.status)}</small></div>`).join('');
}

async function initialize() {
  try {
    const [categories, guList] = await Promise.all([api('/api/categories'), api('/api/dongs/gu')]);
    state.categories = categories;
    state.guList = guList;
    $('#category-select').innerHTML = categories.map((category) => `<option value="${escapeHtml(category.code)}">${escapeHtml(category.name)}</option>`).join('');
    $('#site-category').innerHTML = $('#category-select').innerHTML;
    setConnection(true, 'Render API 연결됨');
    updatePickers();
    const [overview, pipeline] = await Promise.all([api('/api/data/overview'), loadPipeline()]);
    renderOverview(overview);
    void pipeline;
  } catch (error) {
    setConnection(false, 'API 연결 확인 필요');
    showNotice(`Render API에 연결하지 못했습니다. ${error.message} 로컬 브라우저 사용 시 Render의 CORS_ORIGINS에 현재 페이지 주소를 추가해야 할 수 있습니다.`, true);
    $('#data-result').innerHTML = '<p class="form-hint">API 연결을 확인하지 못해 데이터 설명을 불러오지 못했습니다.</p>';
    $('#pipeline-result').innerHTML = '<p class="form-hint">API 연결을 확인하지 못했습니다.</p>';
  }
}

$$('.nav-item[data-view]').forEach((button) => button.addEventListener('click', () => {
  const view = button.dataset.view;
  state.activeView = view;
  $$('.nav-item[data-view]').forEach((item) => item.classList.toggle('is-active', item === button));
  $$('.page-view').forEach((page) => {
    const active = page.id === `view-${view}`;
    page.hidden = !active;
    page.classList.toggle('is-active', active);
  });
  $('#current-crumb').textContent = ({ compare: '동네 비교', site: '자리 상세', data: '데이터와 기준' })[view];
  if (view === 'data') api('/api/data/overview').then(renderOverview).catch((error) => showNotice(error.message, true));
}));

$('#location-count').addEventListener('change', updatePickers);
$('#compare-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('#global-notice').hidden = true;
  const button = $('button[type="submit"]', event.currentTarget);
  setBusy(button, true, '리포트 조회 중');
  try {
    const rows = $$('.dong-picker');
    const selectedCodes = rows.map((row) => $('.dong-select', row).value);
    if (new Set(selectedCodes).size !== selectedCodes.length) {
      showNotice('같은 행정동을 두 번 선택할 수 없습니다. 후보지를 다르게 골라주세요.');
      return;
    }
    const params = new URLSearchParams({ category: $('#category-select').value });
    rows.forEach((row) => params.append('adm_cds', $('.dong-select', row).value));
    const response = await api(`/api/dongs/compare?${params.toString()}`);
    renderComparison(response.items || []);
    $('#base-date-heading').textContent = response.base_date.replaceAll('-', '.');
    setConnection(true, 'Render API 연결됨');
  } catch (error) {
    showNotice(`비교 리포트를 불러오지 못했습니다. ${error.message}`, true);
  } finally {
    setBusy(button, false, '비교 리포트 보기');
  }
});

function renderAddressResults(response) {
  const host = $('#address-results');
  const items = response.items || [];
  if (!items.length) {
    host.innerHTML = `<p class="form-hint">서울에서 '${escapeHtml(response.query)}' 주소를 찾지 못했습니다. 동 이름과 번지를 함께 넣어 보세요.</p>`;
    return;
  }
  const more = response.truncated ? ' · 결과가 많아 앞쪽만 보여 줍니다. 주소를 더 자세히 넣으면 좁혀집니다' : '';
  host.innerHTML = `<p class="form-hint">주소 ${formatNumber(items.length)}건${more}</p>
    <ul class="address-list">${items.map((item, index) => `
      <li><button class="address-item" type="button" data-index="${index}">
        <strong>${escapeHtml(item.jibun_addr)}</strong>
        <span>${escapeHtml(item.road_addr)}</span>
        <small>${escapeHtml(item.dong ? `${item.gu} ${item.dong}` : '행정동 미상')} · ${item.site_id ? `10년 새 가게 ${formatNumber(item.permits_10y)}곳` : '최근 10년 가게 기록 없음'}</small>
      </button></li>`).join('')}</ul>`;
  $$('.address-item', host).forEach((button) => button.addEventListener('click', () => {
    $$('.address-item', host).forEach((other) => other.classList.toggle('is-active', other === button));
    showAddress(items[Number(button.dataset.index)]);
  }));
}

async function showAddress(item) {
  state.lastAddress = item;
  if (!item.site_id) {
    $('#site-result').innerHTML = `<div class="empty-state slim-empty"><p class="eyebrow">${escapeHtml(item.dong ? `${item.gu} · ${item.dong}` : item.gu)}</p><h2>${escapeHtml(item.jibun_addr)}</h2><p>이 지번에는 최근 10년 동안 영업한 일반음식점·휴게음식점·제과점이 없습니다.</p></div>`;
    return;
  }
  $('#site-result').innerHTML = '<div class="loading-state">자리 이력을 불러오는 중...</div>';
  try {
    renderSite(await api(`/api/sites/${encodeURIComponent(item.site_id)}?category=${encodeURIComponent($('#site-category').value)}`), item.dong || '');
  } catch (error) {
    $('#site-result').innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`;
  }
}

$('#site-category').addEventListener('change', () => {
  if (state.lastAddress?.site_id) showAddress(state.lastAddress);
});

$('#site-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $('button[type="submit"]', form);
  $('#global-notice').hidden = true;
  setBusy(button, true, '검색 중');
  try {
    const response = await api(`/api/address/search?${new URLSearchParams({ q: $('#site-address').value.trim() })}`);
    renderAddressResults(response);
    state.lastAddress = null;
    $('#site-result').innerHTML = '';
    if ((response.items || []).length === 1) {
      $('.address-item').classList.add('is-active');
      showAddress(response.items[0]);
    }
  } catch (error) {
    $('#site-result').innerHTML = '';
    $('#address-results').innerHTML = `<div class="notice">${escapeHtml(error.message)}</div>`;
  } finally {
    setBusy(button, false, '주소 검색');
  }
});

initialize();
