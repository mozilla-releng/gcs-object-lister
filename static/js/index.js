// Main page logic for GCS Object Lister

import { APIClient, APIError, showMessage, clearMessages, formatDate, formatBytes } from './api.js';

const api = new APIClient();
let statusPollingInterval = null;
let fetchToDelete = null;

// Initialize page
document.addEventListener('DOMContentLoaded', function() {
    setupEventListeners();
    loadFetches();
    checkFetchStatus();
});

function setupEventListeners() {
    // Fetch form submission
    document.getElementById('fetch-form').addEventListener('submit', handleFetchSubmit);
    
    // Delete modal functions (make them global)
    window.closeDeleteModal = closeDeleteModal;
    window.confirmDelete = confirmDelete;
    window.deleteFetch = deleteFetch;
}

async function handleFetchSubmit(event) {
    event.preventDefault();
    clearMessages();
    
    const formData = new FormData(event.target);
    const bucket = formData.get('bucket').trim() || null;
    const prefix = formData.get('prefix').trim() || null;
    
    try {
        setFetchButtonLoading(true);
        
        const result = await api.startFetch(bucket, prefix);
        
        showMessage('success', `Fetch started successfully! Database: ${result.db_name}`);
        
        // Start polling for status
        startStatusPolling();
        
        // Reload fetches to show the new one
        setTimeout(() => loadFetches(), 1000);
        
    } catch (error) {
        setFetchButtonLoading(false);
        
        if (error.isConflict()) {
            showMessage('error', 'A fetch is already running. Please wait for it to complete.');
        } else {
            showMessage('error', `Failed to start fetch: ${error.details}`);
        }
    }
}

function setFetchButtonLoading(loading) {
    const button = document.getElementById('fetch-button');
    const buttonText = document.getElementById('fetch-button-text');
    const spinner = document.getElementById('fetch-spinner');
    
    button.disabled = loading;
    
    if (loading) {
        buttonText.textContent = 'Starting...';
        spinner.classList.remove('hidden');
    } else {
        buttonText.textContent = 'Fetch Current Files';
        spinner.classList.add('hidden');
    }
}

async function checkFetchStatus() {
    try {
        const status = await api.getStatus();
        updateStatusDisplay(status);
        
        if (status.running) {
            startStatusPolling();
        }
    } catch (error) {
        console.error('Failed to check fetch status:', error);
    }
}

function startStatusPolling() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
    }
    
    statusPollingInterval = setInterval(async () => {
        try {
            const status = await api.getStatus();
            updateStatusDisplay(status);
            
            if (!status.running) {
                stopStatusPolling();
                setFetchButtonLoading(false);
                loadFetches(); // Refresh the fetches list
            }
        } catch (error) {
            console.error('Status polling error:', error);
        }
    }, 2000);
}

function stopStatusPolling() {
    if (statusPollingInterval) {
        clearInterval(statusPollingInterval);
        statusPollingInterval = null;
    }
}

function updateStatusDisplay(status) {
    const statusDiv = document.getElementById('fetch-status');
    const statusText = document.getElementById('status-text');
    
    if (status.running) {
        statusDiv.classList.remove('hidden');
        
        let message = status.message || 'Fetch in progress...';
        if (status.processed) {
            message += ` - ${status.processed.toLocaleString()} objects fetched`;
        }
        
        statusText.textContent = message;
        setFetchButtonLoading(true);
    } else {
        statusDiv.classList.add('hidden');
        setFetchButtonLoading(false);
    }
}

async function loadFetches() {
    const loadingDiv = document.getElementById('fetches-loading');
    const containerDiv = document.getElementById('fetches-container');
    const noFetchesDiv = document.getElementById('no-fetches');
    const tbody = document.getElementById('fetches-tbody');
    
    // Show loading
    loadingDiv.classList.remove('hidden');
    containerDiv.classList.add('hidden');
    
    try {
        const fetches = await api.listFetches();
        
        // Hide loading
        loadingDiv.classList.add('hidden');
        
        if (fetches.length === 0) {
            noFetchesDiv.classList.remove('hidden');
            containerDiv.classList.add('hidden');
        } else {
            noFetchesDiv.classList.add('hidden');
            containerDiv.classList.remove('hidden');
            
            // Populate table
            tbody.innerHTML = '';
            fetches.forEach(fetch => {
                const row = createFetchRow(fetch);
                tbody.appendChild(row);
            });
        }
    } catch (error) {
        loadingDiv.classList.add('hidden');
        showMessage('error', `Failed to load fetches: ${error.details}`);
    }
}

function createFetchRow(fetch) {
    const row = document.createElement('tr');
    
    const statusClass = fetch.status === 'success' ? 'status-success' : 
                       fetch.status === 'error' ? 'status-error' : 
                       fetch.status === 'running' ? 'status-running' : '';
    
    const endedAt = fetch.ended_at ? formatDate(fetch.ended_at) : 
                   fetch.status === 'running' ? 'In progress...' : 'Unknown';
    
    const objectCount = fetch.record_count || 0;
    const dbSizeMB = fetch.db_size_mb || 0;
    const dbSizeText = dbSizeMB > 0 ? `${dbSizeMB} MB` : '-';
    
    row.innerHTML = `
        <td>${fetch.db_name}</td>
        <td>${fetch.bucket_name}</td>
        <td>${fetch.prefix || '<em>None</em>'}</td>
        <td>${formatDate(fetch.started_at)}</td>
        <td>${endedAt}</td>
        <td>${objectCount.toLocaleString()}</td>
        <td>${dbSizeText}</td>
        <td class="${statusClass}">
            <i class="fas fa-${getStatusIcon(fetch.status)}"></i>
            ${fetch.status}
            ${fetch.error ? `<br><small>${fetch.error}</small>` : ''}
        </td>
        <td>
            <div class="fetch-actions">
                <a href="/${fetch.db_name}" class="btn-small">
                    <i class="fas fa-folder-open"></i> Open
                </a>
                <button class="btn-small secondary" onclick="deleteFetch('${fetch.db_name}')" 
                        ${fetch.status === 'running' ? 'disabled' : ''}>
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </td>
    `;
    
    return row;
}

function getStatusIcon(status) {
    switch (status) {
        case 'success': return 'check-circle';
        case 'error': return 'exclamation-triangle';
        case 'running': return 'sync-alt fa-spin';
        default: return 'question-circle';
    }
}

function deleteFetch(dbName) {
    fetchToDelete = dbName;
    document.getElementById('delete-fetch-name').textContent = dbName;
    document.getElementById('delete-modal').showModal();
}

function closeDeleteModal() {
    document.getElementById('delete-modal').close();
    fetchToDelete = null;
}

async function confirmDelete() {
    if (!fetchToDelete) return;
    
    const deleteBtn = document.getElementById('confirm-delete-btn');
    const originalText = deleteBtn.textContent;
    
    try {
        deleteBtn.disabled = true;
        deleteBtn.innerHTML = '<span class="spinner"></span> Deleting...';
        
        await api.deleteFetch(fetchToDelete);
        
        showMessage('success', `Fetch ${fetchToDelete} deleted successfully.`);
        closeDeleteModal();
        loadFetches();
        
    } catch (error) {
        if (error.isConflict()) {
            showMessage('error', 'Cannot delete a running fetch.');
        } else if (error.isNotFound()) {
            showMessage('error', 'Fetch not found.');
        } else {
            showMessage('error', `Failed to delete fetch: ${error.details}`);
        }
    } finally {
        deleteBtn.disabled = false;
        deleteBtn.textContent = originalText;
    }
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopStatusPolling();
});