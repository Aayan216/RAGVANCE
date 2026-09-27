// RAGVANCE - Main JavaScript

// ---------------------------------------------------------------
// Theme (dark mode) — attributes set in <head>; Chart.js handled here
// ---------------------------------------------------------------
const THEME_KEY = 'ragvance-theme';

function getTheme() {
    return document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
}

function applyChartTheme(theme) {
    if (typeof Chart === 'undefined') return;

    const textColor = theme === 'dark' ? '#B5B5B5' : '#6B7280';
    const gridColor = theme === 'dark' ? '#3A3A3A' : 'rgba(0, 0, 0, 0.1)';
    const titleColor = theme === 'dark' ? '#F5F5F5' : '#1F2937';

    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;

    // Update charts already created on the page
    document.querySelectorAll('canvas').forEach((canvas) => {
        const chart = (typeof Chart.getChart === 'function') ? Chart.getChart(canvas) : null;
        if (!chart) return;

        if (chart.options.plugins) {
            chart.options.plugins.legend = chart.options.plugins.legend || {};
            chart.options.plugins.legend.labels = chart.options.plugins.legend.labels || {};
            chart.options.plugins.legend.labels.color = textColor;
            if (chart.options.plugins.title) {
                chart.options.plugins.title.color = titleColor;
            }
        }

        if (chart.options.scales) {
            Object.values(chart.options.scales).forEach((scale) => {
                if (!scale) return;
                scale.ticks = Object.assign({}, scale.ticks, { color: textColor });
                scale.grid = Object.assign({}, scale.grid, { color: gridColor });
                if (scale.title) {
                    scale.title = Object.assign({}, scale.title, { color: titleColor });
                }
            });
        }

        chart.update('none');
    });
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    document.documentElement.setAttribute('data-bs-theme', theme);
    try {
        localStorage.setItem(THEME_KEY, theme);
    } catch (e) {}

    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = theme === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
    }

    applyChartTheme(theme);
}

// Apply chart defaults as soon as main.js loads (charts are created after this)
applyChartTheme(getTheme());

document.addEventListener('DOMContentLoaded', () => {
    // Sync toggle icon with current theme
    const icon = document.getElementById('themeIcon');
    if (icon) {
        icon.className = getTheme() === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
    }

    const toggle = document.getElementById('themeToggle');
    if (toggle) {
        toggle.addEventListener('click', () => {
            setTheme(getTheme() === 'dark' ? 'light' : 'dark');
        });
    }
});

// ---------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------

// Global CSRF token helper
function getCSRFToken() {
    return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
}

// Generic fetch wrapper with CSRF
async function apiFetch(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCSRFToken(),
        },
    };
    const mergedOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...(options.headers || {}),
        },
    };
    return fetch(url, mergedOptions);
}

// Show toast notification
function showToast(message, type = 'info') {
    const toastContainer = document.getElementById('toastContainer') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    toastContainer.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toastContainer';
    container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
    container.style.zIndex = '1055';
    document.body.appendChild(container);
    return container;
}

// Format time helper
function formatTime(seconds) {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

// Debounce helper
function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

// Copy to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard!', 'success');
    } catch (err) {
        showToast('Failed to copy', 'danger');
    }
}

// Initialize tooltips
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Bootstrap tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(el => new bootstrap.Tooltip(el));
    
    // Initialize Bootstrap popovers
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(el => new bootstrap.Popover(el));
});

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.alert-dismissible').forEach(alert => {
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        }, 5000);
    });
});

// Export for use in other scripts
window.RAGVANCE = {
    apiFetch,
    showToast,
    formatTime,
    debounce,
    copyToClipboard,
    getCSRFToken,
};