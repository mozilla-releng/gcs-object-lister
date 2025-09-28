// Fetch view page logic for GCS Storage Manager

import { APIClient, APIError, showMessage, clearMessages, formatDate, formatBytes, getDbNameFromPath } from './api.js';

const api = new APIClient();
let currentPage = 1;
let currentPageSize = 200;
let currentFilters = [];
let currentSort = 'name_asc';
let currentCreatedBefore = '';
let currentHasCustomTime = '';
let currentManifestPatterns = [];
let totalObjects = 0;
let dbName = '';

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    dbName = getDbNameFromPath();
    setupEventListeners();
    loadFetchInfo();
    loadObjects();
});

function setupEventListeners() {
    // Search form submission
    document.getElementById('search-form').addEventListener('submit', handleSearchSubmit);
    
    // Make pagination functions and variables global
    window.goToPage = goToPage;
    window.downloadList = downloadList;
    window.getCurrentPage = () => currentPage;
    
    // Make regex filter functions global
    window.addRegexFilter = addRegexFilter;
    window.removeRegexFilter = removeRegexFilter;
    window.clearAllFilters = clearAllFilters;

    // Make manifest filter functions global
    window.loadManifest = loadManifest;
    window.clearManifest = clearManifest;
    
    // Initialize filter UI
    updateFilterCount();
    
    // Add event listeners to initial regex input
    const initialInput = document.querySelector('.regex-filter');
    if (initialInput) {
        initialInput.addEventListener('input', updateFilterCount);
        initialInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.getElementById('search-form').dispatchEvent(new Event('submit'));
            }
        });
    }
}

async function loadFetchInfo() {
    try {
        const fetches = await api.listFetches();
        const fetchInfo = fetches.find(f => f.db_name === dbName);
        
        if (!fetchInfo) {
            showMessage('error', 'Fetch not found.');
            return;
        }
        
        const infoElement = document.getElementById('fetch-info');
        const statusClass = fetchInfo.status === 'success' ? 'status-success' : 
                           fetchInfo.status === 'error' ? 'status-error' : 
                           fetchInfo.status === 'running' ? 'status-running' : '';
        
        infoElement.innerHTML = `
            <strong>Database:</strong> ${fetchInfo.db_name} &bull;
            <strong>Bucket:</strong> ${fetchInfo.bucket_name} &bull;
            <strong>Prefix:</strong> ${fetchInfo.prefix || 'None'} &bull;
            <strong>Objects:</strong> ${(fetchInfo.record_count || 0).toLocaleString()} &bull;
            <strong>Status:</strong> <span class="${statusClass}">${fetchInfo.status}</span>
            ${fetchInfo.error ? `<br><strong>Error:</strong> ${fetchInfo.error}` : ''}
        `;
        
    } catch (error) {
        showMessage('error', `Failed to load fetch info: ${error.details}`);
    }
}

async function handleSearchSubmit(event) {
    event.preventDefault();
    clearMessages();
    
    const formData = new FormData(event.target);
    const sort = formData.get('sort');
    const createdBefore = formData.get('created_before');
    const hasCustomTime = formData.get('has_custom_time');
    
    // Collect all regex filters
    const regexInputs = document.querySelectorAll('.regex-filter');
    const filters = [];
    let hasInvalidRegex = false;
    
    regexInputs.forEach((input, index) => {
        const pattern = input.value.trim();
        if (pattern) {
            try {
                new RegExp(pattern);  // Validate regex
                filters.push(pattern);
                input.classList.remove('invalid');
            } catch (error) {
                input.classList.add('invalid');
                showMessage('error', `Invalid regex pattern in filter ${index + 1}: ${error.message}`);
                hasInvalidRegex = true;
            }
        } else {
            input.classList.remove('invalid');
        }
    });
    
    if (hasInvalidRegex) {
        return;
    }
    
    // Store current filters
    currentFilters = filters;
    currentSort = sort;
    
    // Convert local datetime to UTC ISO format for the API
    if (createdBefore) {
        try {
            const localDate = new Date(createdBefore);
            currentCreatedBefore = localDate.toISOString();
        } catch (error) {
            showMessage('error', 'Invalid date format');
            return;
        }
    } else {
        currentCreatedBefore = '';
    }
    
    currentHasCustomTime = hasCustomTime;
    currentPage = 1; // Reset to first page
    
    await loadObjects();
}

async function loadObjects() {
    const loadingDiv = document.getElementById('objects-loading');
    const containerDiv = document.getElementById('objects-container');
    const noObjectsDiv = document.getElementById('no-objects');
    
    // Show loading
    loadingDiv.classList.remove('hidden');
    containerDiv.classList.add('hidden');
    noObjectsDiv.classList.add('hidden');
    
    try {
        const options = {
            page: currentPage,
            pageSize: currentPageSize,
            sort: currentSort
        };
        
        if (currentFilters.length > 0) {
            options.regex_filters = currentFilters;
        }

        if (currentManifestPatterns.length > 0) {
            options.manifest_patterns = currentManifestPatterns;
        }

        if (currentCreatedBefore) {
            options.created_before = currentCreatedBefore;
        }

        if (currentHasCustomTime) {
            options.has_custom_time = currentHasCustomTime;
        }
        
        const result = await api.getObjects(dbName, options);
        
        // Hide loading
        loadingDiv.classList.add('hidden');
        
        if (result.items.length === 0) {
            noObjectsDiv.classList.remove('hidden');
        } else {
            containerDiv.classList.remove('hidden');
            displayObjects(result);
        }
        
    } catch (error) {
        loadingDiv.classList.add('hidden');
        
        if (error.isBadRequest() && error.type === 'invalid_regex') {
            showMessage('error', `Invalid regex: ${error.details}`);
        } else {
            showMessage('error', `Failed to load objects: ${error.details}`);
        }
    }
}

function displayObjects(result) {
    const tbody = document.getElementById('objects-tbody');
    totalObjects = result.total;
    
    // Clear existing rows
    tbody.innerHTML = '';
    
    // Add rows for each object
    result.items.forEach(obj => {
        const row = createObjectRow(obj);
        tbody.appendChild(row);
    });
    
    // Update pagination
    updatePagination(result);
}

function createObjectRow(obj) {
    const row = document.createElement('tr');
    
    row.innerHTML = `
        <td style="word-break: break-all;">${escapeHtml(obj.name)}</td>
        <td>${formatBytes(obj.size)}</td>
        <td>${formatDate(obj.updated)}</td>
        <td>${formatDate(obj.custom_time)}</td>
    `;
    
    return row;
}

function updatePagination(result) {
    const totalPages = Math.ceil(result.total / result.page_size);
    const startItem = (result.page - 1) * result.page_size + 1;
    const endItem = Math.min(result.page * result.page_size, result.total);
    
    const infoText = result.total === 0 ? 'No items' : 
                    `Showing ${startItem.toLocaleString()}-${endItem.toLocaleString()} of ${result.total.toLocaleString()} items`;
    
    // Update both top and bottom pagination info
    document.getElementById('pagination-info').textContent = infoText;
    document.getElementById('pagination-info-bottom').textContent = infoText;
    
    // Update buttons
    const prevButtons = ['prev-btn', 'prev-btn-bottom'];
    const nextButtons = ['next-btn', 'next-btn-bottom'];
    
    prevButtons.forEach(id => {
        const btn = document.getElementById(id);
        btn.disabled = result.page <= 1;
    });
    
    nextButtons.forEach(id => {
        const btn = document.getElementById(id);
        btn.disabled = result.page >= totalPages;
    });
}

async function goToPage(page) {
    if (page < 1) return;
    
    const totalPages = Math.ceil(totalObjects / currentPageSize);
    if (page > totalPages) return;
    
    currentPage = page;
    await loadObjects();
    
    // Scroll to top of table
    document.getElementById('objects-container').scrollIntoView({ behavior: 'smooth' });
}

async function downloadList() {
    const downloadBtn = document.getElementById('download-btn');
    const originalText = downloadBtn.innerHTML;
    
    try {
        downloadBtn.disabled = true;
        downloadBtn.innerHTML = '<span class="spinner"></span> Preparing download...';
        
        const options = {};
        if (currentFilters.length > 0) {
            options.regex_filters = currentFilters;
        }
        if (currentManifestPatterns.length > 0) {
            options.manifest_patterns = currentManifestPatterns;
        }
        if (currentCreatedBefore) {
            options.created_before = currentCreatedBefore;
        }
        if (currentHasCustomTime) {
            options.has_custom_time = currentHasCustomTime;
        }
        
        const response = await api.downloadObjectList(dbName, options);
        
        // Get the blob from the response
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${dbName}_files.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        showMessage('success', 'File list downloaded successfully.');
        
    } catch (error) {
        if (error.isBadRequest() && error.type === 'invalid_regex') {
            showMessage('error', `Invalid regex: ${error.details}`);
        } else {
            showMessage('error', `Failed to download file list: ${error.details}`);
        }
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerHTML = originalText;
    }
}

function addRegexFilter() {
    const container = document.getElementById('regex-filters-container');
    const filterItem = document.createElement('div');
    filterItem.className = 'regex-filter-item';
    
    filterItem.innerHTML = `
        <input type="text" class="regex-filter" placeholder="Enter regex pattern">
        <button type="button" class="remove-filter" onclick="removeRegexFilter(this)">×</button>
    `;
    
    container.appendChild(filterItem);
    updateFilterCount();
    
    // Focus the new input
    const newInput = filterItem.querySelector('.regex-filter');
    newInput.focus();
    
    // Add event listeners
    newInput.addEventListener('input', updateFilterCount);
    newInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('search-form').dispatchEvent(new Event('submit'));
        }
    });
}

function removeRegexFilter(button) {
    const filterItem = button.parentElement;
    filterItem.remove();
    updateFilterCount();
}

function clearAllFilters() {
    const container = document.getElementById('regex-filters-container');
    container.innerHTML = `
        <div class="regex-filter-item">
            <input type="text" class="regex-filter" placeholder="Enter regex pattern">
            <button type="button" class="remove-filter hidden" onclick="removeRegexFilter(this)">×</button>
        </div>
    `;
    updateFilterCount();
}

function updateFilterCount() {
    const inputs = document.querySelectorAll('.regex-filter');
    const removeButtons = document.querySelectorAll('.remove-filter');
    const clearButton = document.getElementById('clear-filters-btn');
    const filterCount = document.getElementById('filter-count');
    
    let activeFilters = 0;
    inputs.forEach(input => {
        if (input.value.trim()) {
            activeFilters++;
        }
    });
    
    // Update count display
    filterCount.textContent = `(${activeFilters})`;
    
    // Show/hide remove buttons based on filter count
    removeButtons.forEach((button, index) => {
        if (inputs.length > 1) {
            button.classList.remove('hidden');
        } else {
            button.classList.add('hidden');
        }
    });
    
    // Show/hide clear all button
    if (activeFilters > 0) {
        clearButton.classList.remove('hidden');
    } else {
        clearButton.classList.add('hidden');
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function loadManifest() {
    const manifestUrlInput = document.getElementById('manifest-url');
    const loadBtn = document.getElementById('load-manifest-btn');
    const clearBtn = document.getElementById('clear-manifest-btn');
    const statusDiv = document.getElementById('manifest-status');
    const statusText = document.getElementById('manifest-status-text');

    const manifestUrl = manifestUrlInput.value.trim();
    if (!manifestUrl) {
        showMessage('error', 'Please enter a manifest URL');
        return;
    }

    const originalText = loadBtn.textContent;

    try {
        loadBtn.disabled = true;
        loadBtn.textContent = 'Loading...';
        statusDiv.classList.add('hidden');

        const response = await fetch('/api/manifest/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: manifestUrl })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.details || `HTTP ${response.status}`);
        }

        if (data.patterns) {
            currentManifestPatterns = data.patterns;

            // Show success status
            statusDiv.classList.remove('hidden');
            statusText.textContent = data.message;
            statusText.className = 'manifest-success';

            // Show and populate patterns list
            displayManifestPatterns(data.patterns);

            // Show clear button
            clearBtn.classList.remove('hidden');

            // Reload objects with manifest filters
            currentPage = 1;
            loadObjects();

            showMessage('success', `Manifest loaded with ${data.patterns.length} patterns`);
        } else {
            throw new Error(data.details || 'Failed to parse manifest');
        }

    } catch (error) {
        statusDiv.classList.remove('hidden');
        statusText.textContent = `Error: ${error.message || error.details || 'Failed to load manifest'}`;
        statusText.className = 'manifest-error';
        showMessage('error', `Failed to load manifest: ${error.message || error.details}`);
    } finally {
        loadBtn.disabled = false;
        loadBtn.textContent = originalText;
    }
}

function clearManifest() {
    currentManifestPatterns = [];

    // Clear UI
    document.getElementById('manifest-url').value = '';
    document.getElementById('manifest-status').classList.add('hidden');
    document.getElementById('manifest-patterns').classList.add('hidden');
    document.getElementById('clear-manifest-btn').classList.add('hidden');

    // Reload objects without manifest filters
    currentPage = 1;
    loadObjects();

    showMessage('success', 'Manifest filter cleared');
}

function displayManifestPatterns(patterns) {
    const patternsDiv = document.getElementById('manifest-patterns');
    const patternsList = document.getElementById('manifest-patterns-list');

    // Clear existing patterns
    patternsList.innerHTML = '';

    // Create a collapsible list of patterns
    const summary = document.createElement('details');
    summary.innerHTML = `
        <summary>Show ${patterns.length} patterns</summary>
        <div class="patterns-container"></div>
    `;

    const container = summary.querySelector('.patterns-container');

    patterns.forEach((pattern, index) => {
        const patternItem = document.createElement('div');
        patternItem.className = 'pattern-item';
        patternItem.innerHTML = `
            <code class="pattern-code">${escapeHtml(pattern)}</code>
        `;
        container.appendChild(patternItem);
    });

    patternsList.appendChild(summary);
    patternsDiv.classList.remove('hidden');
}