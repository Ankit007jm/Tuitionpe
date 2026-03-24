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
let currentSignupStep = 1;

function goToSignupStep(step) {
    const step1 = document.getElementById('signupStep1');
    const step2 = document.getElementById('signupStep2');
    const step3 = document.getElementById('signupStep3');

    // Validate current step before moving forward
    if (currentSignupStep === 1 && step > 1) {
        const name = document.getElementById('signupName');
        const phone = document.getElementById('signupPhone');
        const password = document.getElementById('signupPass');
        const confirm = document.getElementById('signupConfirmPass');

        if (!name || !name.value.trim() || name.value.trim().length < 2) {
            showToast('Name must be at least 2 characters.', 'error');
            return;
        }
        if (!phone || phone.value.length !== 10) {
            showToast('Enter a valid 10-digit phone number.', 'error');
            return;
        }
        if (!password || password.value.length < 6) {
            showToast('Password must be at least 6 characters.', 'error');
            return;
        }
        if (!confirm || password.value !== confirm.value) {
            showToast('Passwords do not match.', 'error');
            return;
        }
    }

    if (currentSignupStep === 2 && step > 2) {
        const checked = document.querySelectorAll('input[name="subjects"]:checked');
        if (checked.length === 0) {
            showToast('Please select at least one subject.', 'error');
            return;
        }
    }

    // Hide all steps
    if (step1) step1.style.display = 'none';
    if (step2) step2.style.display = 'none';
    if (step3) step3.style.display = 'none';

    // Show target step
    const target = document.getElementById('signupStep' + step);
    if (target) target.style.display = 'block';

    currentSignupStep = step;
    updateSignupStepIndicators();
}

function updateSignupStepIndicators() {
    for (let i = 1; i <= 3; i++) {
        const indicator = document.getElementById('step' + i + 'Indicator');
        const label = document.getElementById('step' + i + 'Label');

        if (!indicator) continue;

        indicator.className = '';
        if (i < currentSignupStep) {
            indicator.classList.add('w-9', 'h-9', 'rounded-full', 'gradient-accent', 'flex', 'items-center', 'justify-center', 'text-sm', 'font-bold', 'transition-all');
            indicator.innerHTML = '<i class="fas fa-check text-xs"></i>';
        } else if (i === currentSignupStep) {
            indicator.classList.add('w-9', 'h-9', 'rounded-full', 'gradient-accent', 'flex', 'items-center', 'justify-center', 'text-sm', 'font-bold', 'transition-all');
            indicator.textContent = i;
        } else {
            indicator.classList.add('w-9', 'h-9', 'rounded-full', 'bg-white/10', 'flex', 'items-center', 'justify-center', 'text-sm', 'font-bold', 'text-gray-500', 'transition-all');
            indicator.textContent = i;
        }

        if (label) {
            label.style.color = i <= currentSignupStep ? '#10b981' : '#6b7280';
        }
    }
}

function handleSignup(event) {
    event.preventDefault();
    const form = document.getElementById('signupForm');
    if (form) {
        const subjects = [];
        document.querySelectorAll('input[name="subjects"]:checked').forEach(cb => {
            subjects.push(cb.value);
        });
        document.getElementById('subjectsHidden').value = subjects.join(',');

        const classes = [];
        document.querySelectorAll('input[name="classes"]:checked').forEach(cb => {
            classes.push(cb.value);
        });
        document.getElementById('classesHidden').value = classes.join(',');

        form.submit();
    }
}

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
function initPaymentChart(labels, collected, pending) {
    const ctx = document.getElementById('paymentChart');
    if (!ctx) return;
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Collected',
                data: collected,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16,185,129,0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#10b981',
            }, {
                label: 'Pending',
                data: pending,
                borderColor: '#f97316',
                backgroundColor: 'rgba(249,115,22,0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: '#f97316',
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: true, labels: { color: '#9ca3af', font: { size: 11 } } } },
            scales: {
                x: { ticks: { color: '#6b7280', font: { size: 10 } }, grid: { color: 'rgba(255,255,255,0.03)' } },
                y: { ticks: { color: '#6b7280', font: { size: 10 }, callback: v => '₹' + v }, grid: { color: 'rgba(255,255,255,0.03)' } }
            }
        }
    });
}

function initFeesPieChart(collected, pending, overdue) {
    const ctx = document.getElementById('feesPieChart');
    if (!ctx) return;
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Collected', 'Pending', 'Overdue'],
            datasets: [{
                data: [collected, pending, overdue],
                backgroundColor: ['#10b981', '#f97316', '#ef4444'],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '65%',
            plugins: {
                legend: { display: true, position: 'bottom', labels: { color: '#9ca3af', padding: 16, font: { size: 11 } } }
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
