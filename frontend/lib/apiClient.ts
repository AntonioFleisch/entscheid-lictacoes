let accessToken: string | null = null;
let currentOrgId: string | null = null;

if (typeof window !== 'undefined') {
    currentOrgId = localStorage.getItem('current_org_id');
}

export const setAccessToken = (token: string | null) => {
    accessToken = token;
};

export const getAccessToken = () => accessToken;

export const setCurrentOrgId = (orgId: string | null) => {
    currentOrgId = orgId;
    if (orgId && typeof window !== 'undefined') {
        localStorage.setItem('current_org_id', orgId);
    } else if (typeof window !== 'undefined') {
        localStorage.removeItem('current_org_id');
    }
};

export const getCurrentOrgId = () => currentOrgId;

/**
 * Central fetch wrapper for all API calls.
 * 
 * IMPORTANT: All URLs should be relative (e.g., "/api/licitacoes").
 * Next.js rewrites in next.config.ts proxy these to the backend,
 * keeping everything same-origin and avoiding CORS issues.
 */
export async function apiFetch(url: string, options: RequestInit = {}) {
    const headers = new Headers(options.headers || {});
    
    // Always include credentials (cookies for refresh_token)
    options.credentials = 'include';
    
    // Auto-inject JSON Content-Type if there's a body
    if (options.body && !headers.has('Content-Type')) {
        headers.set('Content-Type', 'application/json');
    }

    if (accessToken && !url.includes('/api/auth/register') && !url.includes('/api/auth/login')) {
        headers.set('Authorization', `Bearer ${accessToken}`);
    }

    if (currentOrgId && !url.includes('/api/auth/register') && !url.includes('/api/auth/login')) {
        headers.set('X-Workspace-Id', currentOrgId);
        headers.set('X-Org-Id', currentOrgId); // Keep for legacy if needed
    }
    
    options.headers = headers;
    
    // Use the URL as-is — Next.js proxy handles /api/* rewrites to the backend
    const targetUrl = url;

    try {
        let response = await fetch(targetUrl, options);

        if (response.status === 401 && !url.includes('/api/auth/login') && !url.includes('/api/auth/refresh')) {
            // Try to refresh the token
            try {
                const refreshRes = await fetch('/api/auth/refresh', {
                    method: 'POST',
                    credentials: 'include'
                });

                if (refreshRes.ok) {
                    const data = await refreshRes.json();
                    accessToken = data.access_token;
                    
                    // Retry original request with new token
                    headers.set('Authorization', `Bearer ${accessToken}`);
                    options.headers = headers;
                    response = await fetch(targetUrl, options);
                } else {
                    accessToken = null;
                    if (typeof window !== 'undefined') {
                        window.location.href = '/login';
                    }
                }
            } catch {
                accessToken = null;
                if (typeof window !== 'undefined') {
                    window.location.href = '/login';
                }
            }
        }

        return response;
    } catch (error: unknown) {
        if (process.env.NODE_ENV === "development") {
            if (error instanceof Error) {
                console.error(`[apiFetch Error] ${error.name}: ${error.message} - Target: ${targetUrl}`);
            } else {
                console.error(`[apiFetch Error] Unknown error - Target: ${targetUrl}`, error);
            }
        }
        throw error;
    }
}
