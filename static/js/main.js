/**
 * ModelFlow AI Platform JavaScript Engine
 * Dynamic Chart Renderer, Sidebar Controller, Toast Notifications, and Auto-Resize Listeners.
 */

window.ModelFlow = {
    // Store registered Plotly chart containers for global auto-resize
    charts: new Set(),

    /**
     * Render Plotly chart JSON into target container with responsive auto-resize.
     */
    renderChart: function(containerId, figureData) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (!figureData) {
            container.innerHTML = `
                <div class="flex flex-col items-center justify-center h-64 text-slate-400">
                    <i class="fas fa-chart-pie text-4xl mb-3 opacity-40"></i>
                    <p class="text-sm font-medium">No visual data available</p>
                </div>`;
            return;
        }

        try {
            const fig = (typeof figureData === 'string') ? JSON.parse(figureData) : figureData;
            fig.layout = fig.layout || {};
            fig.layout.autosize = true;
            fig.layout.paper_bgcolor = 'rgba(0,0,0,0)';
            fig.layout.plot_bgcolor = 'rgba(0,0,0,0)';

            const config = {
                responsive: true,
                displayModeBar: true,
                displaylogo: false,
                modeBarButtonsToRemove: ['lasso2d', 'select2d'],
                toImageButtonOptions: {
                    format: 'png',
                    filename: 'automl_chart',
                    height: 500,
                    width: 700,
                    scale: 2
                }
            };

            Plotly.react(containerId, fig.data, fig.layout, config).then(() => {
                this.charts.add(containerId);
                // Remove skeleton loaders if present
                const loader = document.getElementById(containerId + '-loader');
                if (loader) loader.style.display = 'none';
            });
        } catch (err) {
            console.error(`[ModelFlow Chart Error] Container #${containerId}:`, err);
            container.innerHTML = `
                <div class="flex flex-col items-center justify-center h-64 text-rose-400">
                    <i class="fas fa-exclamation-triangle text-3xl mb-2"></i>
                    <p class="text-xs font-mono">${err.message}</p>
                </div>`;
        }
    },

    /**
     * Display SaaS toast notification.
     */
    showToast: function(message, type = 'info') {
        let container = document.getElementById('toast-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toast-container';
            container.className = 'fixed bottom-5 right-5 z-50 flex flex-col gap-3 max-w-sm';
            document.body.appendChild(container);
        }

        const toast = document.createElement('div');
        const bgColors = {
            success: 'bg-emerald-600/90 border-emerald-500/50 text-white',
            danger: 'bg-rose-600/90 border-rose-500/50 text-white',
            warning: 'bg-amber-600/90 border-amber-500/50 text-white',
            info: 'bg-indigo-600/90 border-indigo-500/50 text-white'
        };
        const icons = {
            success: 'fa-check-circle',
            danger: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            info: 'fa-info-circle'
        };

        toast.className = `flex items-center gap-3 px-4 py-3 rounded-xl border shadow-xl backdrop-blur-md transition-all duration-300 transform translate-y-2 opacity-0 ${bgColors[type] || bgColors.info}`;
        toast.innerHTML = `
            <i class="fas ${icons[type] || icons.info} text-lg"></i>
            <span class="text-sm font-medium flex-1">${message}</span>
            <button onclick="this.parentElement.remove()" class="opacity-70 hover:opacity-100"><i class="fas fa-times text-xs"></i></button>
        `;

        container.appendChild(toast);

        // Animate in
        requestAnimationFrame(() => {
            toast.classList.remove('translate-y-2', 'opacity-0');
        });

        // Auto dismiss after 4 seconds
        setTimeout(() => {
            toast.classList.add('opacity-0', 'translate-y-2');
            setTimeout(() => toast.remove(), 300);
        }, 4000);
    },

    /**
     * Display a modern SaaS confirmation popup modal.
     */
    confirm: function(options) {
        const title = options.title || 'Are you sure?';
        const message = options.message || 'This action cannot be undone.';
        const confirmText = options.confirmText || 'Confirm';
        const confirmClass = options.confirmClass || 'bg-rose-600 hover:bg-rose-700 text-white';
        const icon = options.icon || 'fa-exclamation-triangle text-amber-500';
        const onConfirm = options.onConfirm || function() {};

        let modal = document.getElementById('global-confirm-modal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'global-confirm-modal';
            modal.className = 'fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4 transition-all duration-200 opacity-0 pointer-events-none';
            modal.innerHTML = `
                <div class="bg-white border border-slate-200 rounded-3xl shadow-2xl p-6 max-w-sm w-full space-y-4 text-slate-900 transform scale-95 transition-all duration-200">
                    <div class="flex items-center gap-3">
                        <div id="confirm-icon-bg" class="w-10 h-10 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center shrink-0">
                            <i id="confirm-icon" class="fas fa-exclamation-triangle text-amber-600 text-lg"></i>
                        </div>
                        <div>
                            <h3 id="confirm-title" class="text-base font-extrabold text-slate-900"></h3>
                        </div>
                    </div>
                    <p id="confirm-message" class="text-xs text-slate-600 font-medium leading-relaxed"></p>
                    <div class="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                        <button id="confirm-cancel-btn" type="button" class="px-4 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold transition-all">Cancel</button>
                        <button id="confirm-ok-btn" type="button" class="px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-2xs"></button>
                    </div>
                </div>
            `;
            document.body.appendChild(modal);
        }

        const titleEl = modal.querySelector('#confirm-title');
        const msgEl = modal.querySelector('#confirm-message');
        const iconEl = modal.querySelector('#confirm-icon');
        const okBtn = modal.querySelector('#confirm-ok-btn');
        const cancelBtn = modal.querySelector('#confirm-cancel-btn');

        titleEl.textContent = title;
        msgEl.textContent = message;
        iconEl.className = 'fas ' + icon;
        okBtn.textContent = confirmText;
        okBtn.className = 'px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-2xs ' + confirmClass;

        function closeModal() {
            modal.classList.add('opacity-0', 'pointer-events-none');
            modal.querySelector('div').classList.add('scale-95');
        }

        cancelBtn.onclick = function() {
            closeModal();
        };

        okBtn.onclick = function() {
            closeModal();
            onConfirm();
        };

        modal.onclick = function(e) {
            if (e.target === modal) closeModal();
        };

        // Open modal
        requestAnimationFrame(() => {
            modal.classList.remove('opacity-0', 'pointer-events-none');
            modal.querySelector('div').classList.remove('scale-95');
        });
    }
};

// Global listener for data-confirm forms and links
document.addEventListener('submit', (e) => {
    const form = e.target;
    if (form.hasAttribute('data-confirm') && !form.dataset.confirmed) {
        e.preventDefault();
        ModelFlow.confirm({
            title: form.dataset.confirmTitle || 'Confirmation Required',
            message: form.getAttribute('data-confirm'),
            confirmText: form.dataset.confirmBtn || 'Proceed',
            confirmClass: form.dataset.confirmClass || 'bg-rose-600 hover:bg-rose-700 text-white',
            onConfirm: () => {
                form.dataset.confirmed = 'true';
                form.submit();
            }
        });
    }
});

document.addEventListener('click', (e) => {
    const link = e.target.closest('a[data-confirm]');
    if (link && !link.dataset.confirmed) {
        e.preventDefault();
        ModelFlow.confirm({
            title: link.dataset.confirmTitle || 'Confirmation Required',
            message: link.getAttribute('data-confirm'),
            confirmText: link.dataset.confirmBtn || 'Delete',
            confirmClass: link.dataset.confirmClass || 'bg-rose-600 hover:bg-rose-700 text-white',
            onConfirm: () => {
                link.dataset.confirmed = 'true';
                window.location.href = link.href;
            }
        });
    }
});

// Global resize listener for all registered Plotly charts
window.addEventListener('resize', () => {
    ModelFlow.charts.forEach(containerId => {
        const el = document.getElementById(containerId);
        if (el && el.clientWidth > 0) {
            Plotly.Plots.resize(containerId);
        }
    });
});

document.addEventListener('DOMContentLoaded', () => {
    // Sidebar Drawer & Responsive Hamburger Controller
    const sidebar = document.getElementById('sidebar');
    const openSidebarBtn = document.getElementById('openSidebar');
    const closeSidebarBtn = document.getElementById('closeSidebar');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    // Restore saved sidebar collapsed preference on desktop
    if (window.innerWidth >= 1024 && localStorage.getItem('sidebarCollapsed') === 'true') {
        document.body.classList.add('sidebar-collapsed');
    }

    function toggleSidebar() {
        if (!sidebar) return;
        
        const isMobile = window.innerWidth < 1024;
        
        if (isMobile) {
            const isHidden = sidebar.classList.contains('-translate-x-full');
            if (isHidden) {
                sidebar.classList.remove('-translate-x-full');
                if (sidebarBackdrop) sidebarBackdrop.classList.remove('hidden');
            } else {
                sidebar.classList.add('-translate-x-full');
                if (sidebarBackdrop) sidebarBackdrop.classList.add('hidden');
            }
        } else {
            // Desktop Mini Sidebar Toggle (Icon-Only Mode)
            document.body.classList.toggle('sidebar-collapsed');
            const isCollapsed = document.body.classList.contains('sidebar-collapsed');
            localStorage.setItem('sidebarCollapsed', isCollapsed ? 'true' : 'false');
            
            // Trigger Plotly chart resize after transition
            setTimeout(() => window.dispatchEvent(new Event('resize')), 300);
        }
    }

    if (openSidebarBtn) {
        openSidebarBtn.addEventListener('click', toggleSidebar);
    }
    if (closeSidebarBtn) {
        closeSidebarBtn.addEventListener('click', toggleSidebar);
    }
    if (sidebarBackdrop) {
        sidebarBackdrop.addEventListener('click', () => {
            if (sidebar) sidebar.classList.add('-translate-x-full');
            sidebarBackdrop.classList.add('hidden');
        });
    }

    // Sidebar Project Switcher Dropdown Toggle
    const projectDropdownBtn = document.getElementById('sidebarProjectDropdownBtn');
    const projectDropdownMenu = document.getElementById('sidebarProjectDropdownMenu');
    const projectDropdownArrow = document.getElementById('sidebarProjectArrow');

    if (projectDropdownBtn && projectDropdownMenu) {
        projectDropdownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = projectDropdownMenu.classList.contains('hidden');
            if (isHidden) {
                projectDropdownMenu.classList.remove('hidden');
                if (projectDropdownArrow) projectDropdownArrow.classList.add('rotate-180');
            } else {
                projectDropdownMenu.classList.add('hidden');
                if (projectDropdownArrow) projectDropdownArrow.classList.remove('rotate-180');
            }
        });

        document.addEventListener('click', (e) => {
            if (!projectDropdownMenu.contains(e.target) && !projectDropdownBtn.contains(e.target)) {
                projectDropdownMenu.classList.add('hidden');
                if (projectDropdownArrow) projectDropdownArrow.classList.remove('rotate-180');
            }
        });
    }

    // Project Switcher Modal Handlers
    const openProjectModalBtn = document.getElementById('openProjectModalBtn');
    const projectModal = document.getElementById('projectModal');
    const closeProjectModal = document.getElementById('closeProjectModal');

    if (openProjectModalBtn && projectModal) {
        openProjectModalBtn.addEventListener('click', () => {
            projectModal.classList.remove('hidden');
        });
    }
    if (closeProjectModal && projectModal) {
        closeProjectModal.addEventListener('click', () => {
            projectModal.classList.add('hidden');
        });
    }
    if (projectModal) {
        projectModal.addEventListener('click', (e) => {
            if (e.target === projectModal) projectModal.classList.add('hidden');
        });
    }

    // Theme Toggle
    const themeToggle = document.getElementById('themeToggle');
    const html = document.documentElement;

    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            html.classList.toggle('dark');
            const icon = themeToggle.querySelector('i');
            if (html.classList.contains('dark')) {
                icon.classList.remove('fa-moon');
                icon.classList.add('fa-sun');
            } else {
                icon.classList.remove('fa-sun');
                icon.classList.add('fa-moon');
            }
            // Trigger Plotly chart resize on theme toggle
            window.dispatchEvent(new Event('resize'));
        });
    }

    // User Dropdown Menu
    const userDropdownBtn = document.getElementById('userDropdownBtn');
    const userDropdownMenu = document.getElementById('userDropdownMenu');

    if (userDropdownBtn && userDropdownMenu) {
        userDropdownBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            userDropdownMenu.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!userDropdownMenu.contains(e.target) && !userDropdownBtn.contains(e.target)) {
                userDropdownMenu.classList.add('hidden');
            }
        });
    }
});
