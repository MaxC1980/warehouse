// Common JavaScript utilities for warehouse management system

const API_BASE = '/api';

// API request helper
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(API_BASE + url, {
            ...options,
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            }
        });

        if (response.status === 401) {
            window.location.href = '/login';
            return null;
        }

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Request failed');
        }
        return data;
    } catch (error) {
        console.error('API Error:', error);
        alert(error.message);
        return null;
    }
}

// Format date for display
function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN');
}

// Format date for input value (YYYY-MM-DD using local time)
function formatDateForInput(d) {
    const pad = n => n < 10 ? '0' + n : n;
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
}

// Init date range controls (通用日期范围初始化)
// 页面加载后调用，传入起始日期 input ID、结束日期 input ID、加载函数
function initDateRange(startId, endId, loadFn) {
    window.setThisMonth = function() {
        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
        document.getElementById(startId).value = formatDateForInput(firstDay);
        document.getElementById(endId).value = formatDateForInput(today);
        if (loadFn) loadFn();
    };
    window.setLastMonth = function() {
        const today = new Date();
        const firstDay = new Date(today.getFullYear(), today.getMonth() - 1, 1);
        const lastDay = new Date(today.getFullYear(), today.getMonth(), 0);
        document.getElementById(startId).value = formatDateForInput(firstDay);
        document.getElementById(endId).value = formatDateForInput(lastDay);
        if (loadFn) loadFn();
    };
}

// Set date range to current week (Monday to today)
function setThisWeek() {
    const today = new Date();
    const dayOfWeek = today.getDay();
    const monday = new Date(today);
    monday.setDate(today.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
    document.getElementById('date-from').value = formatDateForInput(monday);
    document.getElementById('date-to').value = formatDateForInput(today);
    loadReport();
}

// Format datetime
function formatDateTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN');
}

// Logout
async function logout() {
    await apiRequest('/auth/logout', { method: 'POST' });
    window.location.href = '/login';
}

// Check current user
async function checkCurrentUser() {
    const user = await apiRequest('/auth/current_user');
    return user;
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Unified pagination function
// containerId: ID of pagination container element
// total: total number of items
// currentPage: current page number (1-based)
// perPage: items per page
// onPageChange: callback function(pageNumber) when page button is clicked
function renderPagination(containerId, total, currentPage, perPage, onPageChange) {
    const totalPages = Math.ceil(total / perPage);
    const pagination = document.getElementById(containerId);
    let html = `<span class="pagination-info">共 ${total} 条，第 ${currentPage}/${totalPages} 页</span>`;

    if (totalPages > 1) {
        html += ' ';
        for (let i = 1; i <= totalPages; i++) {
            if (i <= 5 || i === totalPages || Math.abs(i - currentPage) <= 2) {
                html += `<button class="${i === currentPage ? 'active' : ''}" onclick="${onPageChange}(${i})">${i}</button>`;
            } else if (i === 6 && currentPage > 5) {
                html += '<span>...</span>';
            }
        }
    }
    pagination.innerHTML = html;
}
