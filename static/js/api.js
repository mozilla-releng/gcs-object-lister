// API client utilities for GCS Storage Manager

class APIClient {
    constructor(baseURL = '/api') {
        this.baseURL = baseURL;
    }

    async request(method, endpoint, data = null) {
        const url = `${this.baseURL}${endpoint}`;
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
            },
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        try {
            const response = await fetch(url, options);
            
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({
                    error: 'unknown_error',
                    details: `HTTP ${response.status}`
                }));
                throw new APIError(errorData.error, errorData.details, response.status);
            }

            // Handle non-JSON responses (like file downloads)
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return response;
            }
        } catch (error) {
            if (error instanceof APIError) {
                throw error;
            }
            throw new APIError('network_error', `Network error: ${error.message}`);
        }
    }

    // Health check
    async health() {
        return this.request('GET', '/health');
    }

    // Get current fetch status
    async getStatus() {
        return this.request('GET', '/status');
    }

    // Start new fetch
    async startFetch(bucket = null, prefix = null) {
        const data = {};
        if (bucket) data.bucket = bucket;
        if (prefix) data.prefix = prefix;
        return this.request('POST', '/fetches', data);
    }

    // List all fetches
    async listFetches() {
        return this.request('GET', '/fetches');
    }

    // Delete a fetch
    async deleteFetch(dbName) {
        return this.request('DELETE', `/fetches/${dbName}`);
    }

    // Get objects for a fetch
    async getObjects(dbName, options = {}) {
        const params = new URLSearchParams();
        
        if (options.regex) params.append('regex', options.regex);
        if (options.regex_filters) {
            options.regex_filters.forEach(filter => {
                params.append('regex_filters[]', filter);
            });
        }
        if (options.manifest_patterns) {
            options.manifest_patterns.forEach(pattern => {
                params.append('manifest_patterns[]', pattern);
            });
        }
        if (options.page) params.append('page', options.page);
        if (options.pageSize) params.append('page_size', options.pageSize);
        if (options.sort) params.append('sort', options.sort);
        if (options.created_before) params.append('created_before', options.created_before);
        if (options.has_custom_time) params.append('has_custom_time', options.has_custom_time);
        if (options.matches_manifest) params.append('matches_manifest', options.matches_manifest);

        const query = params.toString();
        const endpoint = `/fetches/${dbName}/objects${query ? '?' + query : ''}`;

        // Debug logging for API call
        console.log('API getObjects - Full URL:', endpoint);

        return this.request('GET', endpoint);
    }

    // Get manifest entries
    async getManifestEntries(dbName) {
        return this.request('GET', `/manifest/entries/${dbName}`);
    }

    // Download object list
    async downloadObjectList(dbName, options = {}) {
        const params = new URLSearchParams();
        
        if (options.regex) params.append('regex', options.regex);
        if (options.regex_filters) {
            options.regex_filters.forEach(filter => {
                params.append('regex_filters[]', filter);
            });
        }
        if (options.manifest_patterns) {
            options.manifest_patterns.forEach(pattern => {
                params.append('manifest_patterns[]', pattern);
            });
        }
        if (options.created_before) params.append('created_before', options.created_before);
        if (options.has_custom_time) params.append('has_custom_time', options.has_custom_time);
        if (options.matches_manifest) params.append('matches_manifest', options.matches_manifest);

        const query = params.toString();
        const endpoint = `/fetches/${dbName}/download${query ? '?' + query : ''}`;
        
        return this.request('GET', endpoint);
    }
}

class APIError extends Error {
    constructor(type, details, status = null) {
        super(`${type}: ${details}`);
        this.type = type;
        this.details = details;
        this.status = status;
    }

    isConflict() {
        return this.status === 409;
    }

    isNotFound() {
        return this.status === 404;
    }

    isBadRequest() {
        return this.status === 400;
    }
}

// Utility functions for UI
function showMessage(type, message, container = 'message-area') {
    const messageArea = document.getElementById(container);
    const className = type === 'error' ? 'error-message' : 'success-message';
    
    messageArea.innerHTML = `
        <div class="${className}">
            <i class="fas fa-${type === 'error' ? 'exclamation-triangle' : 'check-circle'}"></i>
            ${message}
        </div>
    `;
    
    // Auto-hide success messages after 5 seconds
    if (type === 'success') {
        setTimeout(() => {
            messageArea.innerHTML = '';
        }, 5000);
    }
}

function clearMessages(container = 'message-area') {
    document.getElementById(container).innerHTML = '';
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function formatDate(dateString) {
    if (!dateString || dateString === 'null' || dateString === 'undefined') return 'Unknown';
    
    try {
        // Clean up malformed date strings (remove duplicate timezone info)
        let cleanDateString = dateString;
        
        // Fix dates that have both +00:00 and Z (invalid format)
        if (cleanDateString.includes('+00:00Z')) {
            cleanDateString = cleanDateString.replace('+00:00Z', 'Z');
        }
        
        const date = new Date(cleanDateString);
        
        // Check if the date is valid
        if (isNaN(date.getTime())) {
            console.warn('Invalid date detected:', dateString);
            return 'Invalid Date';
        }
        
        return date.toLocaleString('en-US', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false,
            timeZoneName: 'short'
        });
    } catch (error) {
        console.warn('Date parsing error:', error, 'for date:', dateString);
        return 'Invalid Date';
    }
}

function getDbNameFromPath() {
    const pathParts = window.location.pathname.split('/');
    return pathParts[pathParts.length - 1];
}

// Export for use in other modules
export { APIClient, APIError, showMessage, clearMessages, formatBytes, formatDate, getDbNameFromPath };