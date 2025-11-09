const FILTER_DEBOUNCE_MS = 450;

function setupFilterForm(form) {
  const inputs = Array.from(form.querySelectorAll('input, select'));
  let debounceTimer = null;

  inputs.forEach((input) => {
    const isInstant = input.type === 'search' || input.type === 'text';
    const handler = () => {
      if (isInstant) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => form.submit(), FILTER_DEBOUNCE_MS);
      } else {
        form.submit();
      }
    };

    if (isInstant) {
      input.addEventListener('input', handler);
    } else {
      input.addEventListener('change', handler);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  const filters = document.querySelectorAll('[data-filter-form]');
  filters.forEach((form) => setupFilterForm(form));
});

