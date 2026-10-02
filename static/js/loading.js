(() => {
    if (window.__portalLoadingInitialized) return;
    window.__portalLoadingInitialized = true;

    const overlay = document.getElementById('page-loading');
    const showOverlay = (label) => {
        if (!overlay) return;
        const text = overlay.querySelector('span:last-child');
        if (text) text.textContent = label;
        overlay.hidden = false;
    };

    document.addEventListener('submit', (event) => {
        if (event.defaultPrevented) return;
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || form.dataset.noLoading === 'true') return;
        if (form.dataset.loadingActive === 'true') {
            event.preventDefault();
            return;
        }

        const submitter = event.submitter instanceof HTMLButtonElement
            ? event.submitter
            : form.querySelector('button[type="submit"], input[type="submit"]');
        if (submitter && !submitter.disabled) {
            submitter.setAttribute('aria-busy', 'true');
            submitter.disabled = true;
            const label = submitter.dataset.loadingText || (
                form.enctype === 'multipart/form-data' ? 'Uploading…' : 'Submitting…'
            );
            if (submitter instanceof HTMLButtonElement) {
                submitter.dataset.loadingOriginal = submitter.innerHTML;
                const indicator = document.createElement('span');
                indicator.className = 'button-loading-indicator';
                const spinner = document.createElement('span');
                spinner.className = 'button-loading-spinner';
                spinner.setAttribute('aria-hidden', 'true');
                const text = document.createElement('span');
                text.textContent = label;
                indicator.append(spinner, text);
                submitter.replaceChildren(indicator);
            } else {
                submitter.dataset.loadingOriginalValue = submitter.value;
                submitter.value = label;
            }
        }
        form.dataset.loadingActive = 'true';
        showOverlay(form.enctype === 'multipart/form-data' ? 'Uploading…' : 'Submitting…');
    });

    document.addEventListener('click', (event) => {
        if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        const link = event.target.closest('a[href]');
        if (!link || link.target || link.hasAttribute('download')) return;
        const destination = new URL(link.href, window.location.href);
        if (destination.origin !== window.location.origin || destination.href === window.location.href) return;
        if (destination.pathname === window.location.pathname && destination.search === window.location.search && destination.hash) return;
        showOverlay('Loading page…');
    });

    window.addEventListener('pageshow', () => {
        if (overlay) overlay.hidden = true;
        document.querySelectorAll('[aria-busy="true"]').forEach((submitter) => {
            submitter.removeAttribute('aria-busy');
            submitter.disabled = false;
            if (submitter instanceof HTMLButtonElement && submitter.dataset.loadingOriginal) {
                submitter.innerHTML = submitter.dataset.loadingOriginal;
                delete submitter.dataset.loadingOriginal;
            } else if (submitter instanceof HTMLInputElement && submitter.dataset.loadingOriginalValue) {
                submitter.value = submitter.dataset.loadingOriginalValue;
                delete submitter.dataset.loadingOriginalValue;
            }
        });
        document.querySelectorAll('form[data-loading-active="true"]').forEach((form) => {
            delete form.dataset.loadingActive;
        });
    });
})();
