const API_BASE = (window.WHERE_TO_OPEN_API_BASE_URL || 'https://where-to-open.onrender.com').replace(/\/$/, '');
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
  notice.innerHTML = `${escapeHtml(message)}${action ? ` <a href="https://where-to-open.onrender.com/docs" target="_blank" rel="noreferrer">API 문서 확인 ↗</a>` : ''}`;
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

function updatePickers() {
  const count = Number($('#location-count').value);
  const host = $('#dong-pickers');
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
    fillDongSelect(guSelect, dongSelect, previousValue.code);
  }
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

function makeAxis(title, key, rows, candidateCount) {
  const body = rows.map((row) => `
    <div class="metric-grid" style="--candidate-count:${candidateCount}">
      <div class="metric-label">${row.label}${row.caption ? `<span class="metric-caption">${row.caption}</span>` : ''}</div>
      ${row.cells.join('')}
    </div>`).join('');
  return `<section class="metric-section" data-axis="${key}"><h3 class="metric-section-title">${title}</h3>${body}</section>`;
}

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
    { label: '점포 밀도', caption: '개 / km²', cells: items.map((item) => {
      const value = item.competition?.density_per_km2;
      const max = Math.max(1, ...items.map((candidate) => candidate.competition?.density_per_km2 || 0));
      return metricCell(value == null ? '자료 없음' : `${formatNumber(value, 1)}개`, `${formatNumber(item.competition?.open_count)}곳 영업 중`, value == null ? null : (value / max) * 100);
    }) },
    { label: '서울 내 밀도 비교', cells: items.map((item) => item.competition ? metricCell(`${formatNumber(item.competition.seoul_rank)} / ${formatNumber(item.competition.seoul_dong_count)}위`, `서울 평균 ${formatNumber(item.competition.seoul_avg_density, 1)}개/km²`) : metricCell('자료 없음')) },
  ], items.length);
  const stability = makeAxis('안정성 · 버팀과 교체 흐름', 'stability', [
    { label: '3년 생존율', cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.survival_3y), basisLabel(item.stability.survival_basis)) : metricCell('자료 없음')) },
    { label: '교체율', cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.turnover_rate), basisLabel(item.stability.turnover_basis)) : metricCell('자료 없음')) },
    { label: '신규율', cells: items.map((item) => item.stability ? metricCell(formatPercent(item.stability.new_rate), basisLabel(item.stability.new_rate_basis)) : metricCell('자료 없음')) },
  ], items.length);
  const site = makeAxis('자리 · 같은 지번의 최근 10년', 'site', [
    { label: '자리 수', cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.site_count)}곳`, '10년 이력 보유 주소') : metricCell('자료 없음')) },
    { label: '단독 자리 평균 교체', cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.avg_single_permits_10y, 2)}회`, '10년 인허가 수') : metricCell('자료 없음')) },
    { label: '한 칸당 평균 교체', cells: items.map((item) => item.site ? metricCell(`${formatNumber(item.site.avg_per_slot_10y, 2)}회`, '10년 기준') : metricCell('자료 없음')) },
  ], items.length);
  const demand = makeAxis('수요 · 오전, 저녁, 밤', 'demand', [
    { label: '연결 역별 승하차', caption: '하루 평균 · 최대 3개 역', cells: items.map((item) => `<div class="metric-cell">${renderDemand(item)}</div>`) },
  ], items.length);
  host.innerHTML = `<div class="comparison" style="--candidate-count:${items.length}">${headings}${competition}${stability}${site}${demand}</div>`;
  $('#results-heading').hidden = false;
}

function renderSite(site) {
  const history = site.history || [];
  $('#site-result').innerHTML = `
    <article class="site-card">
      <header class="site-card-top"><div><p class="eyebrow">${escapeHtml(site.gu)} · ${escapeHtml(site.adm_cd || '행정동 미상')}</p><h2>${escapeHtml(site.site_key)}</h2><p>지번 기준 · 층·호 구분 없음</p></div><span class="site-id-badge">SITE ${formatNumber(site.id)}</span></header>
      <div class="site-metrics">
        <div class="site-metric"><span class="site-metric-label">10년 인허가</span><strong>${formatNumber(site.permits_10y)}건</strong></div>
        <div class="site-metric"><span class="site-metric-label">한 칸당 교체</span><strong>${formatNumber(site.per_slot_10y, 2)}회</strong></div>
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

$$('.nav-item').forEach((button) => button.addEventListener('click', () => {
  const view = button.dataset.view;
  state.activeView = view;
  $$('.nav-item').forEach((item) => item.classList.toggle('is-active', item === button));
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

$('#site-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = $('button[type="submit"]', form);
  $('#global-notice').hidden = true;
  setBusy(button, true, '자리 이력 조회 중');
  try {
    const siteId = $('#site-id').value;
    const category = $('#site-category').value;
    renderSite(await api(`/api/sites/${encodeURIComponent(siteId)}?category=${encodeURIComponent(category)}`));
  } catch (error) {
    $('#site-result').innerHTML = `<div class="notice">${escapeHtml(error.message)}. 유효한 자리 ID인지 확인하세요.</div>`;
  } finally {
    setBusy(button, false, '자리 이력 조회');
  }
});

initialize();
