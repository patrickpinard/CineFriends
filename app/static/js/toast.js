/**
 * Gestion des notifications toast.
 */
(function() {
    'use strict';
    
    const toastContainer = document.getElementById('toast-container');
    const toastVariants = {
        success: { 
            title: 'Succès', 
            indicator: 'bg-emerald-500', 
            accent: 'text-emerald-600', 
            bg: 'bg-white', 
            text: 'text-slate-700', 
            border: 'border-slate-200' 
        },
        warning: { 
            title: 'Attention', 
            indicator: 'bg-white', 
            accent: 'text-white', 
            bg: 'bg-red-600', 
            text: 'text-white', 
            border: 'border-red-700' 
        },
        danger: { 
            title: 'Erreur', 
            indicator: 'bg-rose-500', 
            accent: 'text-rose-600', 
            bg: 'bg-white', 
            text: 'text-slate-700', 
            border: 'border-slate-200' 
        },
        error: { 
            title: 'Erreur', 
            indicator: 'bg-rose-500', 
            accent: 'text-rose-600', 
            bg: 'bg-white', 
            text: 'text-slate-700', 
            border: 'border-slate-200' 
        },
        info: { 
            title: 'Information', 
            indicator: 'bg-sky-500', 
            accent: 'text-sky-600', 
            bg: 'bg-white', 
            text: 'text-slate-700', 
            border: 'border-slate-200' 
        },
        default: { 
            title: 'Notification', 
            indicator: 'bg-slate-400', 
            accent: 'text-slate-600', 
            bg: 'bg-white', 
            text: 'text-slate-700', 
            border: 'border-slate-200' 
        }
    };

    function createToast(category = 'info', message = '', url = null) {
        if (!toastContainer || !message) return;

        const variant = toastVariants[category] || toastVariants.default;
        const toast = document.createElement('div');
        
        // Pour les warnings, positionner plus bas et utiliser le style rouge
        const isWarning = category === 'warning';
        const toastClasses = isWarning 
            ? `pointer-events-auto overflow-hidden rounded-2xl border ${variant.border} ${variant.bg} shadow-lg ring-1 ring-black/5 transition duration-200 ease-out`
            : `pointer-events-auto overflow-hidden rounded-2xl border ${variant.border} ${variant.bg} shadow-lg ring-1 ring-black/5 transition duration-200 ease-out`;
        
        toast.className = toastClasses;
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(-12px)';
        
        // Pour les warnings, ajouter un style pour les positionner plus bas
        if (isWarning) {
            toast.style.marginTop = '4rem';
        }

        const inner = document.createElement('div');
        inner.className = `flex items-start gap-3 p-4 text-sm ${variant.text}`;

        const dot = document.createElement('span');
        dot.className = `mt-1.5 h-2.5 w-2.5 rounded-full ${variant.indicator}`;
        inner.appendChild(dot);

        const content = document.createElement('div');
        content.className = 'flex-1';

        const titleEl = document.createElement('p');
        titleEl.className = `font-semibold text-base ${variant.accent}`;
        titleEl.textContent = variant.title;
        
        content.appendChild(titleEl);
        
        const messageEl = document.createElement('p');
        messageEl.className = `mt-0.5 ${variant.text}`;
        messageEl.textContent = message;
        content.appendChild(messageEl);

        // Lien d'action optionnel
        if (url) {
            const linkEl = document.createElement('a');
            linkEl.href = url;
            linkEl.className = `mt-1.5 inline-block text-xs font-semibold underline opacity-80 hover:opacity-100 ${variant.accent}`;
            linkEl.textContent = 'Voir →';
            content.appendChild(linkEl);
        }

        inner.appendChild(content);
        toast.appendChild(inner);
        toastContainer.appendChild(toast);
        
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
            toast.style.transform = 'translateY(0)';
        });
        
        // Afficher pendant 5 secondes pour tous les messages
        const displayTime = 5000;
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-12px)';
            setTimeout(() => toast.remove(), 200);
        }, displayTime);
    }
    
    // Rendre la fonction accessible globalement
    window.createToast = createToast;

    // ── Toast broadcast centré ─────────────────────────────────────────────
    const broadcastContainer = document.getElementById('broadcast-toast-container');

    const broadcastStyles = {
        info:    { border: 'border-sky-200',    bg: 'bg-sky-50',    icon: 'text-sky-500',    title: 'text-sky-800',    msg: 'text-sky-700' },
        warning: { border: 'border-amber-200',  bg: 'bg-amber-50',  icon: 'text-amber-500',  title: 'text-amber-800',  msg: 'text-amber-700' },
        error:   { border: 'border-rose-200',   bg: 'bg-rose-50',   icon: 'text-rose-500',   title: 'text-rose-800',   msg: 'text-rose-700' },
    };

    function createBroadcastToast(level, title, message) {
        if (!broadcastContainer) return;
        const style = broadcastStyles[level] || broadcastStyles.info;

        const wrapper = document.createElement('div');
        wrapper.className = `pointer-events-auto w-full max-w-md rounded-2xl border ${style.border} ${style.bg} px-5 py-4 shadow-xl ring-1 ring-black/5 transition duration-300 ease-out`;
        wrapper.style.opacity = '0';
        wrapper.style.transform = 'scale(0.92)';

        wrapper.innerHTML = `
            <div class="flex items-start gap-4">
                <span class="mt-0.5 flex-shrink-0 ${style.icon}">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M10.34 15.84c-.688-.06-1.386-.09-2.09-.09H7.5a4.5 4.5 0 0 1 0-9h.75c.704 0 1.402-.03 2.09-.09m0 9.18c.253.962.584 1.892.985 2.783.247.55.06 1.21-.463 1.511l-.657.38c-.551.318-1.26.117-1.527-.461a20.845 20.845 0 0 1-1.44-4.282m3.102.069a18.03 18.03 0 0 1-.59-4.59c0-1.586.205-3.124.59-4.59m0 9.18a23.848 23.848 0 0 1 8.835 2.535M10.34 6.66a23.847 23.847 0 0 1 8.835-2.535m0 0A23.74 23.74 0 0 1 18.795 3m.38 1.125a23.91 23.91 0 0 1 1.014 5.395m-1.014 8.855c-.118.38-.245.754-.38 1.125m.38-1.125a23.91 23.91 0 0 0 1.014-5.395m0-3.46c.495.413.811 1.035.811 1.73 0 .695-.316 1.317-.811 1.73m0-3.46a24.347 24.347 0 0 1 0 3.46" />
                    </svg>
                </span>
                <div class="flex-1 min-w-0">
                    <p class="text-sm font-semibold ${style.title}">${title || 'Notification'}</p>
                    ${message ? `<p class="mt-1 text-sm ${style.msg}">${message}</p>` : ''}
                </div>
                <button class="flex-shrink-0 rounded-full p-1 ${style.icon} opacity-60 hover:opacity-100 transition" data-broadcast-close>
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>`;

        broadcastContainer.appendChild(wrapper);

        wrapper.querySelector('[data-broadcast-close]').addEventListener('click', () => dismiss(wrapper));

        requestAnimationFrame(() => {
            wrapper.style.opacity = '1';
            wrapper.style.transform = 'scale(1)';
        });

        // Auto-dismiss après 8 secondes
        setTimeout(() => dismiss(wrapper), 8000);

        function dismiss(el) {
            el.style.opacity = '0';
            el.style.transform = 'scale(0.92)';
            setTimeout(() => el.remove(), 300);
        }
    }

    window.createBroadcastToast = createBroadcastToast;
    
    // Écouter les événements de toast depuis pwa.js
    window.addEventListener('app:toast', (event) => {
        const { category, message } = event.detail;
        createToast(category, message);
    });
})();

