// ========== UTILITY FUNCTIONS ==========

// Hide loading screen
function hideLoadingScreen() {
    const loading = document.getElementById('loading');
    if (loading) {
        setTimeout(() => loading.classList.add('hidden'), 500);
    }
}

// Toggle password visibility
function togglePass(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('fa-eye', 'fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.replace('fa-eye-slash', 'fa-eye');
    }
}

// Show toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (toast) {
        toast.textContent = (type === 'success' ? '✓ ' : '✕ ') + message;
        toast.className = 'toast show';
        setTimeout(() => { toast.classList.remove('show'); }, 3000);
    }
}

// Count-up animation
function animateCountUp(element, target, duration = 1000) {
    const start = parseInt(element.textContent) || 0;
    const increment = (target - start) / (duration / 16);
    let current = start;

    const timer = setInterval(() => {
        current += increment;
        if (current >= target) {
            element.textContent = target;
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(current);
        }
    }, 16);
}

// Get initials from name
function getInitials(name) {
    return name.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
}

// Coming Soon modal
function showComingSoon(feature) {
    const modal = document.getElementById('comingSoonModal');
    const msg = document.getElementById('comingSoonMsg');
    if (modal && msg) {
        msg.textContent = feature + ' will be available in a future update.';
        modal.classList.add('active');
    }
}

function closeComingSoon() {
    const modal = document.getElementById('comingSoonModal');
    if (modal) modal.classList.remove('active');
}

// ========== SIGNUP WIZARD ==========
// The signup wizard lives in templates/auth/signup.html, which is the only
// page that uses it. It was duplicated here too, and because both copies
// declared `let currentSignupStep`, whichever script parsed second threw a
// SyntaxError — on /signup that was this file, so every helper below
// (showToast, togglePass, ripples...) silently failed to load on the signup page.

// ========== WHATSAPP ==========
function sendWhatsAppReminder(phone, studentName, amount, month, tutorName, isOverdue) {
    const template = isOverdue
        ? `🙏 Namaste, ${studentName}'s fee of ₹${amount} for ${month} is overdue. Kindly clear dues. — ${tutorName}`
        : `🙏 Namaste, ${studentName}'s fee of ₹${amount} for ${month} is due. — ${tutorName}`;
    const encoded = encodeURIComponent(template);
    const url = `https://wa.me/91${phone}?text=${encoded}`;
    window.open(url, '_blank');
}

// ========== SEARCH ==========
function filterStudents() {
    const search = document.getElementById('studentSearch');
    if (search) {
        const params = new URLSearchParams(window.location.search);
        params.set('search', search.value);
        window.location.href = '/students?' + params.toString();
    }
}

let searchTimeout;
function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(filterStudents, 500);
}

// ========== PROFILE EDIT TOGGLES ==========
function toggleEdit(section) {
    const display = document.getElementById(section + 'Display');
    const form = document.getElementById(section + 'Form');
    if (display && form) {
        const isEditing = form.style.display !== 'none';
        display.style.display = isEditing ? 'block' : 'none';
        form.style.display = isEditing ? 'none' : 'block';
    }
}

// ========== CHART INITIALIZATION ==========
// Read design tokens so charts match the active theme
function chartTheme() {
    const s = getComputedStyle(document.documentElement);
    const v = name => s.getPropertyValue(name).trim();
    return {
        accent: v('--accent') || '#0d9488',
        warning: v('--warning') || '#d97706',
        danger: v('--danger') || '#dc2626',
        text: v('--text-muted') || '#7d8c88',
        grid: v('--border-default') || '#e3eae8',
    };
}

function initPaymentChart(labels, collected, pending) {
    const ctx = document.getElementById('paymentChart');
    if (!ctx) return;
    const t = chartTheme();
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Collected',
                data: collected,
                borderColor: t.accent,
                backgroundColor: t.accent + '1a',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointBackgroundColor: t.accent,
                borderWidth: 2,
            }, {
                label: 'Pending',
                data: pending,
                borderColor: t.warning,
                backgroundColor: t.warning + '1a',
                fill: true,
                tension: 0.4,
                pointRadius: 3,
                pointBackgroundColor: t.warning,
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, labels: { color: t.text, font: { size: 11, weight: 600 }, boxWidth: 12, boxHeight: 12, borderRadius: 3, useBorderRadius: true } } },
            scales: {
                x: { ticks: { color: t.text, font: { size: 10 } }, grid: { display: false } },
                y: { ticks: { color: t.text, font: { size: 10 }, callback: v => '₹' + v }, grid: { color: t.grid }, border: { display: false } }
            }
        }
    });
}

function initFeesPieChart(collected, pending, overdue) {
    const ctx = document.getElementById('feesPieChart');
    if (!ctx) return;
    const t = chartTheme();
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Collected', 'Pending', 'Overdue'],
            datasets: [{
                data: [collected, pending, overdue],
                backgroundColor: [t.accent, t.warning, t.danger],
                borderWidth: 0,
                borderRadius: 4,
                spacing: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '68%',
            plugins: {
                legend: { display: true, position: 'bottom', labels: { color: t.text, padding: 16, font: { size: 11, weight: 600 }, boxWidth: 12, boxHeight: 12, borderRadius: 3, useBorderRadius: true } }
            }
        }
    });
}

// ========== SCHEDULE ADD MODAL ==========
function openAddClass() {
    const modal = document.getElementById('addClassModal');
    if (modal) modal.classList.add('active');
}

function closeAddClass() {
    const modal = document.getElementById('addClassModal');
    if (modal) modal.classList.remove('active');
}

// ========== FLASH MESSAGES AUTO-HIDE ==========
document.addEventListener('DOMContentLoaded', function() {
    const flashes = document.querySelectorAll('.flash-message');
    flashes.forEach(f => {
        setTimeout(() => {
            f.style.opacity = '0';
            setTimeout(() => f.remove(), 300);
        }, 4000);
    });
});

// ========== INTERACTION POLISH ==========
//
// Navigation is deliberately instant: an earlier version faded the page
// out for 180ms on every link click, which (a) delayed every navigation
// and (b) broke the browser Back button — the browser restores a page
// from its back/forward cache with inline styles intact, so pages came
// back stuck at opacity:0 (blank screen). DOMContentLoaded does not fire
// on a bfcache restore, so nothing reset it.

// Safety net: clear any leftover fade from a cached page (including
// pages cached by the previous version of this script). `pageshow` fires
// on first load AND on back/forward cache restores.
window.addEventListener('pageshow', () => {
    document.body.style.opacity = '';
    document.body.style.transition = '';
});

// Click ripple on buttons
function initRipples() {
    document.addEventListener('click', e => {
        const btn = e.target.closest('.btn-primary, .btn-outline');
        if (!btn) return;
        const r = btn.getBoundingClientRect();
        const d = Math.max(r.width, r.height);
        const s = document.createElement('span');
        s.className = 'ripple';
        s.style.width = s.style.height = d + 'px';
        s.style.left = (e.clientX - r.left - d / 2) + 'px';
        s.style.top = (e.clientY - r.top - d / 2) + 'px';
        btn.appendChild(s);
        setTimeout(() => s.remove(), 600);
    });
}

// Animate progress bars from 0 to their target width on load
function initProgressBars() {
    document.querySelectorAll('.progress-bar').forEach(bar => {
        const target = bar.style.width;
        if (!target) return;
        bar.style.width = '0%';
        requestAnimationFrame(() => requestAnimationFrame(() => { bar.style.width = target; }));
    });
}

document.addEventListener('DOMContentLoaded', () => {
    if (!window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        initRipples();
        initProgressBars();
    }
});
