import useSWR from 'swr';
import { fetcher } from './api';

export function useItems(params: Record<string, string | number | undefined | null>) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') {
      searchParams.append(k, String(v));
    }
  });
  
// Switched to new SQL-based endpoint
  const { data, error, isLoading, mutate } = useSWR(
    `/api/licitacoes?${searchParams.toString()}`,
    fetcher
  );
  
  return {
    data,
    isLoading,
    isError: error,
    mutate
  };
}

export function useSidebarCounts(params: Record<string, string | number | undefined | null>) {
  const searchParams = new URLSearchParams();
  // Exclude pagination/sort/segmento/status from counts
  // We want counts to reflect "current filters applied to the whole universe"
  // But spec says: "Atualização dos contadores conforme filtros... exceto paginação"
  // And "sidebar-counts deve compartilhar o mesmo builder de filtros"
  // So we pass q, valor, dates, capag, uf.
  // We explicitly EXCLUDE segmento and status because sidebar shows counts for ALL segments.
  
  const EXCLUDED_PARAMS = ['page', 'page_size', 'order_by'];
  
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && !EXCLUDED_PARAMS.includes(k)) {
      searchParams.append(k, String(v));
    }
  });

  const { data, error, isLoading } = useSWR(
    `/api/licitacoes/sidebar-counts?${searchParams.toString()}`,
    fetcher
  );
  
  return {
    counts: data,
    isLoading,
    isError: error
  };
}

export function useItemDetail(id: string) {
  const { data, error, isLoading } = useSWR(
    id ? `/licitacoes/${id}/details` : null,
    fetcher
  );
  return { data, isLoading, isError: error };
}

export function useSegments() {
  const { data, error, isLoading, mutate } = useSWR(
    '/api/segments',
    fetcher
  );
  // The API returns an array directly: [...]
  // SWR `data` will be undefined while loading, so we ensure an empty array fallback
  return { segments: Array.isArray(data) ? data : [], isLoading, error, mutate };
}

export function useModalidades() {
  const { data, error, isLoading } = useSWR('/api/licitacoes/modalidades', fetcher);
  return { modalidadesData: data, isLoading, error };
}

export function useJobStatus(jobId: string | null) {
  const { data, error, isLoading } = useSWR(
    jobId ? `/api/jobs/${jobId}` : null,
    fetcher,
    { refreshInterval: jobId ? 2000 : 0 } // Poll every 2s if there's a Job ID
  );
  return { job: data, isLoading, error };
}

export function useStats() {
  const { data, error, isLoading, mutate } = useSWR(
    '/api/stats',
    fetcher
  );
  return { stats: data, isLoading, error, mutate };
}

export function useAdminOrgs() {
  const { data, error, isLoading, mutate } = useSWR(
    '/api/admin/orgs',
    fetcher
  );
  return { 
    organizations: data?.organizations || [], 
    isLoading, 
    error, 
    mutate 
  };
}

export function useOrgMembers(orgId: string) {
  const { data, error, isLoading, mutate } = useSWR(
    orgId ? `/api/orgs/${orgId}/members` : null,
    fetcher
  );
  return {
    members: data?.members || [],
    isLoading,
    error,
    mutate
  };
}

