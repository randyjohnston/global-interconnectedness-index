// GII Dashboard — client-side utilities

// Format Temporal status response as HTML
document.addEventListener('htmx:afterSwap', function(event) {
    if (event.detail.target.id === 'temporal-status') {
        try {
            const data = JSON.parse(event.detail.target.innerText);
            const color = data.status === 'connected' ? 'text-green-600' : 'text-red-600';
            const icon = data.status === 'connected' ? '●' : '○';
            event.detail.target.innerHTML = `
                <span class="${color} font-medium">${icon} ${data.status}</span>
                <p class="text-sm text-gray-500 mt-1">${data.message || ''}</p>
            `;
        } catch (e) {
            // Not JSON, leave as-is
        }
    }
});
