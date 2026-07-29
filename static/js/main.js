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
    }
};

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
    // Mobile Sidebar Drawer Toggle
    const sidebar = document.getElementById('sidebar');
    const openSidebarBtn = document.getElementById('openSidebar');
    const closeSidebarBtn = document.getElementById('closeSidebar');

    if (openSidebarBtn && sidebar) {
        openSidebarBtn.addEventListener('click', () => {
            sidebar.classList.remove('-translate-x-full');
        });
    }

    if (closeSidebarBtn && sidebar) {
        closeSidebarBtn.addEventListener('click', () => {
            sidebar.classList.add('-translate-x-full');
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
