// Main JavaScript file for Food Truck Fundraiser
// Common functionality and utilities

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    initializeTooltips();
    
    // Initialize confirmation dialogs
    initializeConfirmations();
    
    // Initialize auto-refresh for progress bars
    initializeProgressRefresh();
    
    // Initialize form enhancements
    initializeFormEnhancements();
});

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Initialize confirmation dialogs for dangerous actions
function initializeConfirmations() {
    const confirmButtons = document.querySelectorAll('[data-confirm]');
    
    confirmButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
                return false;
            }
        });
    });
}

// Initialize auto-refresh for progress bars and dynamic content
function initializeProgressRefresh() {
    const progressBars = document.querySelectorAll('.progress-bar[data-auto-refresh]');
    
    if (progressBars.length > 0) {
        // Refresh every 30 seconds
        setInterval(function() {
            location.reload();
        }, 30000);
    }
}

// Initialize form enhancements
function initializeFormEnhancements() {
    // Auto-format currency inputs
    const currencyInputs = document.querySelectorAll('input[type="number"][step="0.01"]');
    currencyInputs.forEach(input => {
        input.addEventListener('blur', function() {
            if (this.value) {
                const value = parseFloat(this.value);
                if (!isNaN(value)) {
                    this.value = value.toFixed(2);
                }
            }
        });
    });
    
    // Auto-save form drafts (for longer forms)
    const forms = document.querySelectorAll('form[data-auto-save]');
    forms.forEach(form => {
        const formId = form.id || 'form_' + Math.random().toString(36).substr(2, 9);
        
        // Load saved data
        loadFormDraft(form, formId);
        
        // Save on input
        form.addEventListener('input', function() {
            saveFormDraft(form, formId);
        });
        
        // Clear draft on successful submit
        form.addEventListener('submit', function() {
            clearFormDraft(formId);
        });
    });
}

// Form draft functionality
function saveFormDraft(form, formId) {
    const formData = new FormData(form);
    const data = {};
    
    for (let [key, value] of formData.entries()) {
        data[key] = value;
    }
    
    try {
        localStorage.setItem('form_draft_' + formId, JSON.stringify(data));
    } catch (e) {
        console.warn('Could not save form draft:', e);
    }
}

function loadFormDraft(form, formId) {
    try {
        const savedData = localStorage.getItem('form_draft_' + formId);
        if (savedData) {
            const data = JSON.parse(savedData);
            
            for (let key in data) {
                const input = form.querySelector(`[name="${key}"]`);
                if (input && input.type !== 'password') {
                    input.value = data[key];
                }
            }
        }
    } catch (e) {
        console.warn('Could not load form draft:', e);
    }
}

function clearFormDraft(formId) {
    try {
        localStorage.removeItem('form_draft_' + formId);
    } catch (e) {
        console.warn('Could not clear form draft:', e);
    }
}

// Utility functions
const utils = {
    // Format currency
    formatCurrency: function(amount) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD'
        }).format(amount);
    },
    
    // Format date
    formatDate: function(date, options = {}) {
        const defaultOptions = {
            year: 'numeric',
            month: 'long',
            day: 'numeric'
        };
        
        return new Intl.DateTimeFormat('en-US', {...defaultOptions, ...options}).format(new Date(date));
    },
    
    // Show temporary success message
    showSuccess: function(message, duration = 3000) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-success alert-dismissible fade show position-fixed';
        alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        setTimeout(() => {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, duration);
    },
    
    // Show temporary error message
    showError: function(message, duration = 5000) {
        const alert = document.createElement('div');
        alert.className = 'alert alert-danger alert-dismissible fade show position-fixed';
        alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        alert.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
        
        document.body.appendChild(alert);
        
        setTimeout(() => {
            if (alert.parentNode) {
                alert.parentNode.removeChild(alert);
            }
        }, duration);
    },
    
    // Copy text to clipboard
    copyToClipboard: function(text, successMessage = 'Copied to clipboard!') {
        if (navigator.clipboard) {
            navigator.clipboard.writeText(text).then(() => {
                this.showSuccess(successMessage);
            }).catch(() => {
                this.fallbackCopyTextToClipboard(text, successMessage);
            });
        } else {
            this.fallbackCopyTextToClipboard(text, successMessage);
        }
    },
    
    // Fallback copy method for older browsers
    fallbackCopyTextToClipboard: function(text, successMessage) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        try {
            document.execCommand('copy');
            this.showSuccess(successMessage);
        } catch (err) {
            this.showError('Failed to copy to clipboard');
        }
        
        document.body.removeChild(textArea);
    },
    
    // Debounce function
    debounce: function(func, wait, immediate) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                timeout = null;
                if (!immediate) func.apply(this, args);
            };
            const callNow = immediate && !timeout;
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
            if (callNow) func.apply(this, args);
        };
    },
    
    // Throttle function
    throttle: function(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
};

// Share functionality
function shareContent(title, text, url) {
    if (navigator.share) {
        navigator.share({
            title: title,
            text: text,
            url: url
        }).catch(console.error);
    } else {
        utils.copyToClipboard(url, 'Link copied! Share it with others.');
    }
}

// Progress bar animation
function animateProgressBar(progressBar, targetPercentage) {
    let currentPercentage = 0;
    const increment = targetPercentage / 50; // 50 steps for smooth animation
    
    const timer = setInterval(() => {
        currentPercentage += increment;
        
        if (currentPercentage >= targetPercentage) {
            currentPercentage = targetPercentage;
            clearInterval(timer);
        }
        
        progressBar.style.width = currentPercentage + '%';
        progressBar.setAttribute('aria-valuenow', currentPercentage);
        progressBar.textContent = Math.round(currentPercentage) + '%';
    }, 20);
}

// Initialize progress bar animations on page load
document.addEventListener('DOMContentLoaded', function() {
    const progressBars = document.querySelectorAll('.progress-bar[data-animate]');
    
    progressBars.forEach(bar => {
        const targetPercentage = parseFloat(bar.getAttribute('data-target')) || 0;
        bar.style.width = '0%';
        
        // Delay animation slightly for better effect
        setTimeout(() => {
            animateProgressBar(bar, targetPercentage);
        }, 500);
    });
});

// Make utils available globally
window.FoodTruckUtils = utils;
