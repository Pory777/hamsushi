// ===== Configuration =====
const DATA_URL = 'https://raw.githubusercontent.com/hamsushi-fans/hamsushi-coupon/main/data/deals.json';
const CACHE_KEY = 'hamsushi_deals_cache';
const CITY_KEY = 'preferredCity';
const CACHE_TTL_MS = 60 * 60 * 1000; // 1 hour

// ===== State =====
let allDeals = [];
let currentFilter = 'all';
let currentCity = 'all';
let searchQuery = '';
let availableCities = [];

// ===== Source Icons =====
const SOURCE_ICONS = {
  '美团': '🛵',
  '大众点评': '📝',
  '闲鱼': '🐟',
  '小红书': '📕',
  '其他': '📌'
};

const SOURCE_KEYS = {
  '美团': 'meituan',
  '大众点评': 'dianping',
  '闲鱼': 'xianyu',
  '小红书': 'xiaohongshu',
  '其他': 'other'
};

// ===== DOM Refs =====
const $ = id => document.getElementById(id);
const dealList = $('dealList');
const bestBanner = $('bestBanner');
const bestSource = $('bestSource');
const bestTitle = $('bestTitle');
const bestExpires = $('bestExpires');
const bestLink = $('bestLink');
const updateInfo = $('updateInfo');
const statTotal = $('statTotal');
const statSources = $('statSources');
const statActive = $('statActive');
const filterBar = $('filterBar');
const btnRefresh = $('btnRefresh');
const btnSubmit = $('btnSubmit');
const btnLocate = $('btnLocate');
const submitModal = $('submitModal');
const modalClose = $('modalClose');
const submitForm = $('submitForm');
const searchInput = $('searchInput');
const citySelect = $('citySelect');

// ===== Helpers =====
function isExpired(expires) {
  if (!expires) return false;
  const parts = expires.split('-');
  if (parts.length !== 3) return false;
  const d = new Date(+parts[0], +parts[1] - 1, +parts[2]);
  return d < new Date();
}

function daysUntil(expires) {
  if (!expires) return null;
  const parts = expires.split('-');
  const d = new Date(+parts[0], +parts[1] - 1, +parts[2]);
  const now = new Date();
  const diff = Math.ceil((d - now) / (1000 * 60 * 60 * 24));
  return diff;
}

function formatExpires(expires) {
  if (!expires) return '';
  const days = daysUntil(expires);
  if (days === null) return '';
  if (days < 0) return '已过期';
  if (days === 0) return '今天到期';
  if (days === 1) return '明天到期';
  if (days <= 7) return `${days}天后到期`;
  return `~${expires}`;
}

// ===== Data Loading =====
async function loadDeals() {
  try {
    const cached = await chrome.storage.local.get(CACHE_KEY);
    if (cached[CACHE_KEY]) {
      const { data, timestamp } = cached[CACHE_KEY];
      if (Date.now() - timestamp < CACHE_TTL_MS) {
        return data;
      }
    }
  } catch (e) {}

  try {
    const resp = await fetch(DATA_URL + '?t=' + Date.now());
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    try {
      await chrome.storage.local.set({
        [CACHE_KEY]: { data, timestamp: Date.now() }
      });
    } catch (e) {}
    return data;
  } catch (e) {
    try {
      const resp = await fetch(chrome.runtime.getURL('data/deals.json'));
      if (!resp.ok) throw new Error('local fallback failed');
      return await resp.json();
    } catch (e2) {
      try {
        const cached = await chrome.storage.local.get(CACHE_KEY);
        if (cached[CACHE_KEY]) {
          return cached[CACHE_KEY].data;
        }
      } catch (e3) {}
      throw e;
    }
  }
}

// ===== City Detection =====
async function detectCity() {
  // Check saved preference
  try {
    const saved = await chrome.storage.local.get(CITY_KEY);
    if (saved[CITY_KEY] && saved[CITY_KEY] !== 'all') {
      return saved[CITY_KEY];
    }
  } catch (e) {}

  // Try geolocation
  try {
    const pos = await new Promise((resolve, reject) => {
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        timeout: 8000,
        enableHighAccuracy: false
      });
    });
    const resp = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${pos.coords.latitude}&lon=${pos.coords.longitude}&accept-language=zh`,
      { headers: { 'User-Agent': 'hamsushi-coupon/1.0' } }
    );
    if (!resp.ok) throw new Error('geocode failed');
    const data = await resp.json();
    const detected = data.address?.city || data.address?.town || data.address?.county || data.address?.state;
    if (detected) {
      const match = availableCities.find(c => detected.includes(c) || c.includes(detected));
      if (match) {
        await chrome.storage.local.set({ [CITY_KEY]: match });
        return match;
      }
    }
  } catch (e) {}
  return 'all';
}

// ===== Populate City Dropdown =====
function populateCities() {
  // Get unique cities from data (exclude '全国')
  const cities = new Set();
  if (allDeals.cities) {
    allDeals.cities.forEach(c => {
      if (c.city !== '全国') cities.add(c.city);
    });
  }
  availableCities = ['全国', ...Array.from(cities).sort()];

  citySelect.innerHTML = availableCities.map(c => 
    `<option value="${c}">${c === '全国' ? '全部城市' : c}</option>`
  ).join('');
  citySelect.value = currentCity;
}

// ===== Rendering =====
function render() {
  const now = new Date();
  updateInfo.textContent = allDeals.updated_at
    ? `最近更新：${allDeals.updated_at}`
    : '数据加载中';

  // Flatten all deals
  let deals = [];
  const sourceSet = new Set();
  let activeCount = 0;

  if (allDeals.cities) {
    allDeals.cities.forEach(city => {
      (city.deals || []).forEach(d => {
        d._city = city.city;
        deals.push(d);
        sourceSet.add(d.source);
        if (!isExpired(d.expires)) activeCount++;
      });
    });
  }

  // ---- Apply City Filter ----
  let cityFiltered = deals;
  if (currentCity !== 'all' && currentCity !== '全国') {
    cityFiltered = deals.filter(d => d._city === '全国' || d._city === currentCity);
  }

  // ---- Apply Search Filter ----
  let searchFiltered = cityFiltered;
  if (searchQuery.trim()) {
    const q = searchQuery.trim().toLowerCase();
    searchFiltered = cityFiltered.filter(d =>
      d.title.toLowerCase().includes(q) ||
      (d.detail && d.detail.toLowerCase().includes(q)) ||
      (d.source && d.source.toLowerCase().includes(q))
    );
  }

  // Update stats
  statTotal.textContent = deals.length;
  statSources.textContent = sourceSet.size;
  statActive.textContent = activeCount;

  // Find best deal
  const bestDeal = deals.find(d => d.is_best && !isExpired(d.expires))
    || deals.filter(d => !isExpired(d.expires)).sort((a, b) => {
      return (b.value || '').length - (a.value || '').length;
    })[0];

  if (bestDeal) {
    bestBanner.style.display = 'flex';
    bestSource.textContent = bestDeal.source;
    bestTitle.textContent = bestDeal.title;
    bestExpires.textContent = bestDeal.expires ? `有效期至 ${bestDeal.expires}` : '';
    bestLink.href = bestDeal.url || '#';
  }

  // ---- Apply Source Filter ----
  let filtered = searchFiltered;
  if (currentFilter !== 'all') {
    filtered = searchFiltered.filter(d => d.source === currentFilter);
  }

  // Sort: active first, best flag, expiry
  filtered.sort((a, b) => {
    const aExp = isExpired(a.expires);
    const bExp = isExpired(b.expires);
    if (aExp !== bExp) return aExp - bExp;
    if (a.is_best !== b.is_best) return a.is_best ? -1 : 1;
    return 0;
  });

  // Render list
  if (filtered.length === 0) {
    dealList.innerHTML = '<div class="empty">没有找到匹配的优惠</div>';
    return;
  }

  dealList.innerHTML = filtered.map(d => {
    const expired = isExpired(d.expires);
    const expText = formatExpires(d.expires);
    const icon = SOURCE_ICONS[d.source] || '📌';
    return `
      <div class="deal-item source-${d.source}${d.is_best && !expired ? ' is-best' : ''}${expired ? ' expired' : ''}" data-url="${d.url || ''}">
        <div class="deal-icon">${icon}</div>
        <div class="deal-body">
          <div class="deal-title">${d.title}</div>
          ${d.detail ? `<div class="deal-detail">${d.detail}</div>` : ''}
          <div class="deal-meta">
            <span class="deal-tag source">${d.source}</span>
            ${d._city && d._city !== '全国' ? `<span class="deal-tag" style="background:#e8f5e9;color:#388e3c;">${d._city}</span>` : ''}
            ${d.type ? `<span class="deal-tag" style="background:#e3f2fd;color:#1976d2;">${d.type}</span>` : ''}
            ${expText ? `<span class="deal-tag expires">${expText}</span>` : ''}
            ${d.is_best && !expired ? '<span class="deal-tag best-tag">🔥 最优</span>' : ''}
          </div>
        </div>
        <div class="deal-arrow">→</div>
      </div>
    `;
  }).join('');

  // Attach click handlers
  document.querySelectorAll('.deal-item').forEach(el => {
    el.addEventListener('click', () => {
      const url = el.dataset.url;
      if (url) chrome.tabs.create({ url });
    });
  });
}

// ===== Re-render with current filters =====
function refreshDisplay() {
  render();
}

// ===== Setup Filters =====
function setupFilters() {
  filterBar.addEventListener('click', e => {
    const btn = e.target.closest('.filter-btn');
    if (!btn) return;
    filterBar.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentFilter = btn.dataset.filter;
    render();
  });
}

// ===== Setup City Selector =====
function setupCitySelector() {
  citySelect.addEventListener('change', () => {
    currentCity = citySelect.value;
    // Save preference
    try {
      chrome.storage.local.set({ [CITY_KEY]: currentCity === '全国' ? 'all' : currentCity });
    } catch (e) {}
    render();
  });

  btnLocate.addEventListener('click', async () => {
    btnLocate.classList.add('loading');
    btnLocate.textContent = '⏳';
    const city = await detectCity();
    btnLocate.classList.remove('loading');
    btnLocate.textContent = '📍';
    if (city !== 'all') {
      currentCity = city;
      citySelect.value = city;
      render();
    } else {
      // Could not detect - show quick feedback
      btnLocate.textContent = '❌';
      setTimeout(() => { btnLocate.textContent = '📍'; }, 1500);
    }
  });
}

// ===== Setup Search =====
function setupSearch() {
  let debounceTimer;
  searchInput.addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      searchQuery = searchInput.value;
      render();
    }, 250);
  });
}

// ===== Refresh =====
btnRefresh.addEventListener('click', async () => {
  btnRefresh.style.transform = 'rotate(360deg)';
  try {
    await chrome.storage.local.remove(CACHE_KEY);
    allDeals = await loadDeals();
    populateCities();
    render();
  } catch (e) {
    dealList.innerHTML = `<div class="empty">加载失败，请稍后再试</div>`;
  }
  setTimeout(() => { btnRefresh.style.transform = ''; }, 400);
});

// ===== Submit Modal =====
btnSubmit.addEventListener('click', () => submitModal.classList.add('open'));
modalClose.addEventListener('click', () => submitModal.classList.remove('open'));
submitModal.addEventListener('click', e => {
  if (e.target === submitModal) submitModal.classList.remove('open');
});

submitForm.addEventListener('submit', e => {
  e.preventDefault();
  const data = {
    source: $('formSource').value,
    title: $('formTitle').value,
    detail: $('formDetail').value,
    url: $('formUrl').value,
    expires: $('formExpires').value,
    city: $('formCity').value || '全国'
  };

  const subject = encodeURIComponent(`[优惠提交] ${data.source} - ${data.title}`);
  const body = encodeURIComponent(
    `来源：${data.source}\n标题：${data.title}\n详情：${data.detail}\n链接：${data.url}\n有效期：${data.expires}\n城市：${data.city}`
  );
  window.open(`mailto:hamsushi@coupon.app?subject=${subject}&body=${body}`);

  submitModal.classList.remove('open');
  submitForm.reset();
  alert('感谢提交！管理员会尽快审核你的优惠信息，审核通过后所有用户都能看到。');
});

// ===== Init =====
async function init() {
  setupFilters();
  setupSearch();
  setupCitySelector();

  try {
    allDeals = await loadDeals();
    populateCities();

    // Try city detection
    currentCity = await detectCity();
    citySelect.value = currentCity;

    render();
  } catch (e) {
    dealList.innerHTML = `<div class="empty">加载失败<br><span style="font-size:12px;color:#999;">请检查网络后点击刷新</span></div>`;
  }
}

init();
