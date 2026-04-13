(scopeSelector) => {
    const root = scopeSelector ? document.querySelector(scopeSelector) : document;
    if (!root) return [];
    const items = root.querySelectorAll('a, button, input, select, textarea, [role="button"], [role="link"], [role="tab"], [onclick]');
    return Array.from(items).slice(0, 100).map((el, i) => {
        const tag = el.tagName.toLowerCase();
        const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 80);
        const type = el.type || '';
        const href = el.href || '';

        let selector = '';
        if (el.id) selector = '#' + el.id;
        else if (el.getAttribute('data-testid')) selector = `[data-testid="${el.getAttribute('data-testid')}"]`;
        else if (el.name) selector = `${tag}[name="${el.name}"]`;
        else if (text && tag === 'button') selector = `button:has-text("${text.slice(0, 30)}")`;
        else if (text && tag === 'a') selector = `a:has-text("${text.slice(0, 30)}")`;
        else {
            const classes = Array.from(el.classList).slice(0, 2).join('.');
            selector = classes ? `${tag}.${classes}` : `${tag}:nth-of-type(${i + 1})`;
        }

        return { tag, selector, text, type, href };
    });
}
