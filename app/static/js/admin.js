// ==========================================
// ADMIN DASHBOARD JAVASCRIPT
// ==========================================

// DOM Elements - Load all at once
const mobileToggle = document.getElementById('mobile-toggle');
const sidebar = document.getElementById('sidebar');
const notifBtn = document.getElementById('notification-btn');
const notifDropdown = document.getElementById('notification-dropdown');
const profileBtn = document.getElementById('profile-btn');
const profileDropdown = document.getElementById('profile-dropdown');
const tableSearch = document.getElementById('table-search');
const dashboardSearch = document.getElementById('dashboard-search');

// ==========================================
// SIDEBAR FUNCTIONS
// ==========================================

// Mobile sidebar toggle
if (mobileToggle && sidebar) {
    mobileToggle.addEventListener('click', (e) => {
        e.stopPropagation();
        sidebar.classList.toggle('active');
    });
    
    // Close on click outside
    document.addEventListener('click', (e) => {
        if (sidebar.classList.contains('active') && 
            !sidebar.contains(e.target) && 
            !mobileToggle.contains(e.target)) {
            sidebar.classList.remove('active');
        }
    });
}

// Sidebar collapse on Escape (desktop only)
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && window.innerWidth > 768) {
        sidebar.classList.toggle('collapsed');
    }
});

// ==========================================
// DROPDOWN FUNCTIONS
// ==========================================

// Notification dropdown
if (notifBtn && notifDropdown) {
    notifBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        notifDropdown.classList.toggle('show');
        if (profileDropdown) profileDropdown.classList.remove('show');
    });
}

// Profile dropdown
if (profileBtn && profileDropdown) {
    profileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        profileDropdown.classList.toggle('show');
        if (notifDropdown) notifDropdown.classList.remove('show');
    });
}

// Close dropdowns on outside click
document.addEventListener('click', () => {
    if (notifDropdown) notifDropdown.classList.remove('show');
    if (profileDropdown) profileDropdown.classList.remove('show');
});

// Mark notifications as read
const markReadBtn = document.querySelector('.mark-read');
if (markReadBtn) {
    markReadBtn.addEventListener('click', () => {
        document.querySelectorAll('.notification-item.unread').forEach(item => {
            item.classList.remove('unread');
        });
        
        // Update badge count
        const badge = notifBtn.querySelector('.badge');
        if (badge) {
            badge.textContent = '0';
            badge.style.display = 'none';
        }
    });
}

// ==========================================
// ANIMATED STAT NUMBERS
// ==========================================

function animateStatNumbers() {
    document.querySelectorAll('.stat-value').forEach(el => {
        const targetValue = parseInt(el.dataset.value);
        if (!targetValue) return;
        
        const isRevenue = targetValue > 100000; // Better check
        let currentValue = 0;
        const increment = Math.ceil(targetValue / 50);
        const duration = 1000; // 1 second
        const stepTime = duration / 50;
        
        const interval = setInterval(() => {
            currentValue += increment;
            if (currentValue >= targetValue) {
                currentValue = targetValue;
                clearInterval(interval);
            }
            
            if (isRevenue) {
                el.textContent = '₹' + (currentValue / 100000).toFixed(1) + 'L';
            } else {
                el.textContent = currentValue.toLocaleString();
            }
        }, stepTime);
    });
}

// Run animation on page load
animateStatNumbers();

// ==========================================
// TABLE SEARCH WITH DEBOUNCE
// ==========================================

let searchTimeout;

function filterTableRows(searchValue) {
    const rows = document.querySelectorAll('.data-table tbody tr');
    const value = searchValue.toLowerCase();
    
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(value) ? '' : 'none';
    });
}

if (tableSearch) {
    tableSearch.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            filterTableRows(e.target.value);
        }, 200); // 200ms debounce
    });
}

// Dashboard search (placeholder functionality)
if (dashboardSearch) {
    dashboardSearch.addEventListener('input', (e) => {
        // Implement global search here
        console.log('Searching for:', e.target.value);
    });
}

// ==========================================
// ACTION BUTTONS WITH EVENT DELEGATION
// ==========================================

document.addEventListener('click', (e) => {
    // Handle all action buttons with delegation
    const actionBtn = e.target.closest('.action-btn');
    if (actionBtn && !actionBtn.classList.contains('approve-btn') && !actionBtn.classList.contains('reject-btn')) {
        actionBtn.style.transform = 'scale(0.9)';
        setTimeout(() => {
            actionBtn.style.transform = 'scale(1)';
        }, 150);
    }
    
    // Approve button
    if (actionBtn && actionBtn.classList.contains('approve-btn')) {
        if (confirm('Approve this event?')) {
            const row = actionBtn.closest('tr');
            const statusBadge = row.querySelector('.status-badge');
            
            statusBadge.textContent = 'Active';
            statusBadge.className = 'status-badge active';
            
            // Visual feedback
            row.style.background = 'rgba(16, 185, 129, 0.05)';
            setTimeout(() => {
                row.style.background = '';
            }, 1000);
            
            // Hide approve/reject buttons
            actionBtn.closest('.action-buttons').style.opacity = '0';
        }
    }
    
    // Reject button
    if (actionBtn && actionBtn.classList.contains('reject-btn')) {
        if (confirm('Reject this event?')) {
            const row = actionBtn.closest('tr');
            
            // Visual feedback
            row.style.background = 'rgba(239, 68, 68, 0.05)';
            setTimeout(() => {
                row.style.opacity = '0';
                row.style.transform = 'translateX(-20px)';
                
                setTimeout(() => {
                    row.remove();
                }, 300);
            }, 500);
        }
    }
});

// ==========================================
// NOTIFICATION CLICK HANDLER
// ==========================================

document.querySelectorAll('.notification-item').forEach(item => {
    item.addEventListener('click', () => {
        item.classList.remove('unread');
        
        // Update unread count
        const unreadCount = document.querySelectorAll('.notification-item.unread').length;
        const badge = notifBtn.querySelector('.badge');
        if (badge) {
            badge.textContent = unreadCount;
            if (unreadCount === 0) {
                badge.style.display = 'none';
            }
        }
    });
});

// ==========================================
// UTILITY FUNCTIONS
// ==========================================

// Update real-time data (placeholder)
function updateDashboardData() {
    // Fetch new data from API
    console.log('Updating dashboard data...');
}

// Set up periodic refresh (optional)
// setInterval(updateDashboardData, 30000); // Every 30 seconds

console.log('✅ Admin dashboard loaded successfully');
