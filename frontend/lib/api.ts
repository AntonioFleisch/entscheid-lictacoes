import { apiFetch } from './apiClient';

/**
 * SWR fetcher. Uses relative URLs — Next.js proxy rewrites /api/* to backend.
 */
export const fetcher = (url: string) => apiFetch(url).then(r => r.json());

export async function getItem(id: string) {
    const res = await apiFetch(`/api/licitacoes/${id}/details`, { cache: 'no-store' });
    if (!res.ok) throw new Error('Failed to fetch item');
    return res.json();
}

export async function searchItems(params: Record<string, string | number | undefined | null>) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      searchParams.append(k, String(v));
    }
  });
  
  const res = await apiFetch(`/api/licitacoes?${searchParams.toString()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error('Failed to search items');
  return res.json();
}

// --- Admin Organization CRUD ---

export async function createOrganization(name: string, slug: string) {
    const res = await apiFetch('/api/admin/orgs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, slug })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to create organization');
    return data;
}

export async function updateOrganization(id: string, name: string, slug: string, is_active: boolean) {
    const res = await apiFetch(`/api/admin/orgs/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, slug, is_active })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to update organization');
    return data;
}

export async function deleteOrganization(id: string) {
    const res = await apiFetch(`/api/admin/orgs/${id}`, {
        method: 'DELETE'
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to delete organization');
    return data;
}

// --- Admin: Set Manager on Org ---

export async function setOrgManager(orgId: string, email: string) {
    const res = await apiFetch(`/api/admin/orgs/${orgId}/set-manager`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to set manager');
    return data;
}

// --- Organization Member Management ---

export async function listOrgMembers(orgId: string) {
    const res = await apiFetch(`/api/orgs/${orgId}/members`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to list members');
    return data;
}

export async function addOrgMember(orgId: string, email: string, role: string = "USUARIO") {
    const res = await apiFetch(`/api/orgs/${orgId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, role })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || data.error?.message || 'Failed to add member');
    return data;
}

export async function removeOrgMember(orgId: string, membershipId: string) {
    const res = await apiFetch(`/api/orgs/${orgId}/members/${membershipId}`, {
        method: 'DELETE'
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to remove member');
    return data;
}
