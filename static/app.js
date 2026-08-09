let campaigns = [];
let categories = [];
let selectedCampaign = null;
let selectedCampaigns = [];
let currentMode = 'new_tab';
let currentCategory = 'All';
let searchTerm = '';

const searchInput = document.getElementById('searchInput');
const tableBody = document.getElementById('campaignTableBody');
const sourceLabel = document.getElementById('sourceLabel');
const campaignCount = document.getElementById('campaignCount');
const lastUpdated = document.getElementById('lastUpdated');
const selectedCount = document.getElementById('selectedCount');
const openBtn = document.getElementById('openBtn');
const copyBtn = document.getElementById('copyBtn');
const refreshBtn = document.getElementById('refreshBtn');
const clearSelectionBtn = document.getElementById('clearSelectionBtn');
const selectionOrderList = document.getElementById('selectionOrderList');
const categoryTabs = document.getElementById('categoryTabs');
const modeButtons = [...document.querySelectorAll('.mode-btn')];

function showToast(message) {
  let toast = document.querySelector('.status-toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.className = 'status-toast';
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('show'), 1800);
}

function escapeHtml(value) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatUpdatedAt(value) {
  if (!value) return '--';

  let parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    parsed = new Date(value.replace(' ', 'T'));
  }

  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return parsed.toLocaleString('en-US', {
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true
  });
}

function renderSelectionOrder() {
  if (!selectedCampaigns.length) {
    selectionOrderList.innerHTML = '<li class="empty-state">No campaigns selected yet.</li>';
    return;
  }

  selectionOrderList.innerHTML = selectedCampaigns
    .map((campaign, index) => `<li>${index + 1}. ${escapeHtml(campaign.name)}</li>`)
    .join('');
}

function renderCategoryTabs() {
  if (!categories.length) {
    categoryTabs.innerHTML = '';
    return;
  }

  const categoryNames = categories.map((category) => category.name);
  const tabs = ['All', ...categoryNames.filter((name) => name !== 'All')];

  categoryTabs.innerHTML = tabs
    .map((name) => `
      <button class="category-tab ${name === currentCategory ? 'active' : ''}" data-category="${escapeHtml(name)}">
        ${escapeHtml(name)}
      </button>
    `)
    .join('');

  categoryTabs.querySelectorAll('.category-tab').forEach((button) => {
    button.addEventListener('click', () => {
      currentCategory = button.dataset.category;
      renderCategoryTabs();
      renderTable();
    });
  });
}

function getVisibleCampaigns() {
  let source = campaigns;
  if (currentCategory !== 'All') {
    const chosen = categories.find((category) => category.name === currentCategory);
    source = chosen ? chosen.campaigns : [];
  }

  return source.filter((item) => {
    if (!searchTerm) return true;
    return item.name.toLowerCase().includes(searchTerm.toLowerCase());
  });
}

function renderTable() {
  const filtered = getVisibleCampaigns();

  selectedCount.textContent = String(filtered.length);
  tableBody.innerHTML = '';

  filtered.forEach((campaign, index) => {
    const row = document.createElement('tr');
    const isSelected = selectedCampaigns.some((item) => item.link === campaign.link);
    if (isSelected) {
      row.classList.add('selected');
    }

    row.innerHTML = `
      <td>${index + 1}</td>
      <td>${escapeHtml(campaign.name)}</td>
      <td class="link-cell">${escapeHtml(campaign.link)}</td>
    `;

    row.addEventListener('click', (event) => {
      if (event.ctrlKey || event.metaKey) {
        toggleCampaignSelection(campaign);
        return;
      }

      selectedCampaign = campaign;
      if (!selectedCampaigns.some((item) => item.link === campaign.link)) {
        selectedCampaigns.push(campaign);
      }
      renderTable();
      renderSelectionOrder();
    });

    row.addEventListener('dblclick', () => openCampaign(campaign.link));
    tableBody.appendChild(row);
  });
}

async function fetchCampaigns() {
  try {
    const response = await fetch('/api/campaigns');
    const data = await response.json();

    const incomingCategories = data.categories || [];
    categories = incomingCategories.length ? incomingCategories : [{ name: 'All', campaigns: data.campaigns || [] }];
    campaigns = data.campaigns || [];

    if (!categories.some((category) => category.name === currentCategory)) {
      currentCategory = 'All';
    }

    sourceLabel.textContent = data.source === 'google_sheets' ? 'Live Camps Link' : 'Data Unavailable';
    campaignCount.textContent = String(campaigns.length);
    lastUpdated.textContent = formatUpdatedAt(data.updated_at);
    renderCategoryTabs();
    renderTable();
  } catch (error) {
    sourceLabel.textContent = 'Load failed';
    showToast('Could not refresh campaign data.');
  }
}

function toggleCampaignSelection(campaign) {
  const existingIndex = selectedCampaigns.findIndex((item) => item.link === campaign.link);
  if (existingIndex >= 0) {
    selectedCampaigns.splice(existingIndex, 1);
    if (selectedCampaign && selectedCampaign.link === campaign.link) {
      selectedCampaign = selectedCampaigns[selectedCampaigns.length - 1] || null;
    }
  } else {
    selectedCampaigns.push(campaign);
    selectedCampaign = campaign;
  }

  renderTable();
  renderSelectionOrder();
}

function normalizeLink(link) {
  if (typeof link !== 'string') {
    return '';
  }
  return link.trim();
}

function openInCurrentBrowser(link, mode) {
  const safeLink = normalizeLink(link);
  if (!safeLink) {
    showToast('No link available for this campaign.');
    return false;
  }

  if (mode === 'same_tab') {
    window.location.href = safeLink;
    return true;
  }

  const popup = window.open(
    safeLink,
    '_blank',
    mode === 'new_window' ? 'noopener,noreferrer,width=1200,height=800' : 'noopener,noreferrer'
  );

  if (popup) {
    return true;
  }

  window.location.href = safeLink;
  return true;
}

async function openCampaign(link) {
  const safeLink = normalizeLink(link);
  if (!safeLink) {
    showToast('No link available for this campaign.');
    return;
  }

  const isLocal = ['localhost', '127.0.0.1', '0.0.0.0', '::1'].includes(window.location.hostname) || window.location.hostname.startsWith('127.');
  if (!isLocal) {
    const opened = openInCurrentBrowser(safeLink, currentMode);
    if (opened) {
      const label = currentMode === 'same_tab' ? 'same tab' : currentMode === 'new_window' ? 'new window' : 'new tab';
      showToast(`Opened in ${label}`);
    }
    return;
  }

  try {
    const response = await fetch(`/open?url=${encodeURIComponent(safeLink)}&mode=${encodeURIComponent(currentMode)}`);
    const result = await response.json();

    if (result.status === 'ok') {
      showToast('Opened in Brave');
      return;
    }

    if (result.status === 'browser_only') {
      const opened = openInCurrentBrowser(safeLink, currentMode);
      if (opened) {
        const label = currentMode === 'same_tab' ? 'same tab' : currentMode === 'new_window' ? 'new window' : 'new tab';
        showToast(`Opened in ${label}`);
      }
      return;
    }

    if (result.status === 'needs_browser_choice') {
      const shouldOpenChrome = window.confirm('Brave was not found. Open this link in Chrome instead?');
      if (shouldOpenChrome) {
        const chromeWindow = window.open(result.url, '_blank', 'noopener,noreferrer');
        if (chromeWindow) {
          showToast('Opened in Chrome');
        } else {
          showToast('Popup blocked. Please allow popups to open Chrome.');
        }
      }
      return;
    }

    if (result.status === 'error' && result.message) {
      showToast(result.message);
      return;
    }

    showToast('Could not open the link.');
  } catch (error) {
    showToast('Browser launch request failed.');
  }
}

async function openSelectedCampaignsInOrder() {
  if (!selectedCampaigns.length) {
    showToast('Select campaigns first.');
    return;
  }

  const validLinks = selectedCampaigns
    .map((campaign) => normalizeLink(campaign.link))
    .filter(Boolean)
    .filter((link, index, list) => list.indexOf(link) === index);

  if (!validLinks.length) {
    showToast('No valid links to open.');
    return;
  }

  if (currentMode === 'same_tab') {
    openCampaign(validLinks[0]);
    return;
  }

  const first = validLinks[0];
  const rest = validLinks.slice(1);

  const firstOpened = openInCurrentBrowser(first, currentMode);
  if (!firstOpened) {
    showToast('Popup blocked. Please allow popups for this site.');
    return;
  }

  rest.forEach((link, index) => {
    setTimeout(() => {
      const opened = openInCurrentBrowser(link, currentMode);
      if (!opened && index === rest.length - 1) {
        showToast('Popup blocked. Please allow popups for this site.');
      }
    }, 150 * (index + 1));
  });
}

async function copySelectedLink() {
  const target = selectedCampaign || (selectedCampaigns[selectedCampaigns.length - 1] || null);
  if (!target) {
    showToast('Select a campaign first.');
    return;
  }

  try {
    await navigator.clipboard.writeText(target.link);
    showToast('Link copied to clipboard.');
  } catch (error) {
    showToast('Clipboard access blocked by the browser.');
  }
}

searchInput.addEventListener('input', (event) => {
  searchTerm = event.target.value.trim();
  renderTable();
});

modeButtons.forEach((button) => {
  button.addEventListener('click', () => {
    currentMode = button.dataset.mode;
    modeButtons.forEach((btn) => btn.classList.toggle('active', btn === button));
  });
});

openBtn.addEventListener('click', () => {
  if (!selectedCampaigns.length) {
    showToast('Choose campaigns first.');
    return;
  }

  if (selectedCampaigns.length === 1 || currentMode === 'same_tab') {
    const target = selectedCampaigns[selectedCampaigns.length - 1] || selectedCampaigns[0];
    openCampaign(target.link);
    return;
  }

  openSelectedCampaignsInOrder();
});

copyBtn.addEventListener('click', () => {
  const target = selectedCampaign || (selectedCampaigns[selectedCampaigns.length - 1] || null);
  if (!target) {
    showToast('Select a campaign first.');
    return;
  }
  navigator.clipboard.writeText(target.link).then(() => {
    showToast('Link copied to clipboard.');
  }).catch(() => {
    showToast('Clipboard access blocked by the browser.');
  });
});

clearSelectionBtn.addEventListener('click', () => {
  selectedCampaigns = [];
  selectedCampaign = null;
  renderTable();
  renderSelectionOrder();
});

refreshBtn.addEventListener('click', fetchCampaigns);

fetchCampaigns();
renderSelectionOrder();
setInterval(fetchCampaigns, 30000);
