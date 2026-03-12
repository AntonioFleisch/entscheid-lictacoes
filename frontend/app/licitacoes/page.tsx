"use client";
import { apiFetch } from "@/lib/apiClient";

import { useItems } from "@/lib/hooks";
import { Search, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react"; // Added RefreshCw
import { Sidebar, FilterState } from "@/components/Sidebar";
import { LicitacaoCard } from "@/components/LicitacaoCard";
import type { LicitacaoItem } from "@/components/LicitacaoCard";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useEffect, useCallback, useMemo, Suspense } from "react";
import { CustomSelect } from "@/components/CustomSelect";

// Simple debounce hook
function useDebounceValue(value: string, delay: number) {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

function LicitacoesContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  
  // 1. Parse State from URL
  const page = Number(searchParams.get("page")) || 1;
  const q = searchParams.get("q") || "";
  const sort = searchParams.get("sort") || "default";
  
  // Filters
  const filters: FilterState = useMemo(() => ({
      segmento: searchParams.get("segmento") || "",
      valor_min: searchParams.get("valor_min") || "",
      valor_max: searchParams.get("valor_max") || "",
      capag: searchParams.get("capag") || "",
      pub_from: searchParams.get("pub_from") || "",
      pub_to: searchParams.get("pub_to") || "",
      prazo_from: searchParams.get("prazo_from") || "",
      prazo_to: searchParams.get("prazo_to") || "",
      expira_em_dias: searchParams.get("expira_em_dias") || "",
      uf: searchParams.get("uf") || "",
      status: searchParams.get("status") || "",
      modalidades: searchParams.get("modalidades") || "",
  }), [searchParams]);

  // Local state for search input
  const [searchTerm, setSearchTerm] = useState(q);
  const debouncedSearch = useDebounceValue(searchTerm, 500);

  // 2. Navigation / Updates
  const updateFilter = useCallback((key: keyof FilterState | 'page' | 'q' | 'sort', value: string) => {
    const params = new URLSearchParams(searchParams.toString());
    
    if (value) {
        params.set(String(key), value);
    } else {
        params.delete(String(key));
    }
    
    // Reset page on ANY filter change (except page itself)
    if (key !== "page") {
        params.set("page", "1");
    }
    
    router.push(`/licitacoes?${params.toString()}`);
  }, [searchParams, router]); 

  const resetFilters = () => {
      // Keep only 'q' if user wants? Or clear everything? 
      // User said "Refresh restaura estado" (browser refresh), "Limpar" implies clearing all filters.
      // We will clear all filters but keep search if desired, or clear search too.
      // Usually "Limpar Filtros" implies filters, not search query.
      const params = new URLSearchParams();
      if (q) params.set("q", q); // Keep search query
      router.push(`/licitacoes?${params.toString()}`);
  };

  // Sync debounce search to URL
  useEffect(() => {
    // Only update if it changed and it's not the initial sync
    if (debouncedSearch !== q) {
        updateFilter("q", debouncedSearch);
    }
  }, [debouncedSearch, q, updateFilter]); 

  // 3. Data Fetching
  const { data, isLoading, mutate } = useItems({
    page,
    page_size: 20, // Default 20
    q,
    order_by: sort,
    ...filters
  });

  // 4. Local Optimistic Items (for ignore/unignore)
  const [localItems, setLocalItems] = useState<LicitacaoItem[] | null>(null);
  
  // Sync SWR -> Local
  useEffect(() => {
    if (data?.results) {
        setLocalItems(data.results);
    }
  }, [data]);

   const displayItems = localItems ?? data?.results ?? [];

  // 5. Actions (Ignore/Unignore)
  const handleAction = useCallback(async (item: LicitacaoItem, action: 'ignore' | 'unignore') => {
    const pncp_id = item.id || item.pncp_id;
    if (!pncp_id) return;
    
    // Optimistic UI Update
    setLocalItems(prev => {
        if (!prev) return prev;
        return prev.filter(i => (i.id || i.pncp_id) !== pncp_id);
    });

    try {
        const encodedId = encodeURIComponent(pncp_id);
        const endpoint = `/api/licitacoes/${encodedId}/${action}`;
        const res = await apiFetch(endpoint, { method: 'POST' });
        if (!res.ok) throw new Error('Failed to update status');
        
        // We don't refill in this new simplified version unless strictly requested.
        // The user asked to "Simplificar". Complex refilling logic causes bugs.
        // Just revalidating SWR is safer.
        mutate(); 
        
    } catch (err) {
        console.error(err);
        // Rollback? Or just re-fetch
        mutate();
    }
  }, [mutate]);

  // 6. Pagination Logic
  const totalPages = data ? data.total_pages : 0; // Using total_pages from API
  const totalResults = data ? data.total : 0;

  // No jumpPage state needed

  const renderPageNumbers = () => {
    if (totalPages <= 1) return null;
    
    // Simple logic: Start, End, Current
    // Always show first, last, current, +/- 1
    const pages = [];
    
    const start = Math.max(1, page - 2);
    const end = Math.min(totalPages, page + 2);
    
    if (start > 1) pages.push(1);
    if (start > 2) pages.push('...');
    
    for (let i = start; i <= end; i++) {
        pages.push(i);
    }
    
    if (end < totalPages - 1) pages.push('...');
    if (end < totalPages) pages.push(totalPages);

    return (
        <div className="flex items-center gap-1">
            {pages.map((p, idx) => (
                typeof p === 'number' ? (
                    <button
                        key={idx}
                        onClick={() => updateFilter("page", String(p))}
                        className={`w-8 h-8 flex items-center justify-center rounded text-xs font-bold transition-colors ${
                            page === p 
                            ? "bg-primary text-white border border-primary shadow-sm" 
                            : "bg-white border border-secondary text-primary hover:bg-tint"
                        }`}
                    >
                        {p}
                    </button>
                ) : (
                    <span key={idx} className="text-secondary font-bold text-xs px-1">...</span>
                )
            ))}
        </div>
    );
  };

  return (
    <div className="flex h-full overflow-hidden bg-[#F0F2F5]">
      
      {/* Sidebar (Fixed width) */}
      <div className="w-[280px] border-r border-gray-200 bg-white p-3 overflow-y-auto custom-scrollbar left-scrollbar flex flex-col gap-6">
           <Sidebar 
               filters={filters} 
               onUpdate={updateFilter}
               onReset={resetFilters}
           />
      </div>

      {/* Main Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
         <div className="max-w-6xl mx-auto flex flex-col gap-6">
            
            {/* Top Bar */}
            <div className="bg-white p-3 rounded-xl border border-secondary/50 shadow-sm flex flex-col md:flex-row items-center justify-between gap-4 sticky top-0 z-10 w-full">
                
                {/* Search */}
                <div className="relative flex-1 w-full">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-primary opacity-60" size={16} />
                    <input 
                        type="text"
                        placeholder="Busque por objeto, órgão, ID..."
                        className="input-base w-full pl-9"
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                    />
                </div>

                {/* Sort */}
                <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-ink uppercase">Ordenar por:</span>
                    <CustomSelect
                        value={sort}
                        onChange={(val) => updateFilter("sort", val)}
                        options={[
                            { value: "default", label: "Padrão" },
                            { value: "valor_desc", label: "Maior Valor" },
                            { value: "created_desc", label: "Mais Recentes" },
                            { value: "prazo_asc", label: "Menor Prazo" },
                        ]}
                        className="w-40"
                    />
                </div>

                <button 
                    onClick={() => mutate()} 
                    className="p-2 text-primary hover:text-ink hover:bg-tint rounded-lg transition-colors"
                    title="Atualizar lista"
                >
                    <RefreshCw size={16} />
                </button>

            </div>

             {/* Results Header */}
             <div className="flex items-center justify-between">
                 <h1 className="text-xl font-bold text-ink flex items-center gap-2">
                     Resultados 
                     <span className="text-sm bg-tint text-ink px-2 py-0.5 rounded-full font-bold border border-secondary shadow-sm">
                         {totalResults}
                     </span>
                 </h1>
                 
                 {/* Simple Pagination Controls (Top) */}
                 <div className="flex items-center gap-3">
                     <button 
                         disabled={page <= 1}
                         onClick={() => updateFilter("page", String(page - 1))}
                         className="px-3 py-1.5 rounded-lg border border-secondary text-primary disabled:bg-tint disabled:text-secondary disabled:border-secondary hover:bg-tint hover:text-primary transition-colors text-xs font-bold"
                     >
                         Anterior
                     </button>
                     <span className="text-xs font-bold text-ink">
                        {page} <span className="text-secondary px-0.5">/</span> {totalPages}
                     </span>
                     <button 
                         disabled={page >= totalPages}
                         onClick={() => updateFilter("page", String(page + 1))}
                         className="px-3 py-1.5 rounded-lg bg-primary text-white border border-primary disabled:bg-tint disabled:text-secondary disabled:border-secondary hover:bg-ink transition-colors text-xs font-bold"
                     >
                         Próxima
                     </button>
                 </div>
             </div>

             {/* Items Grid */}
             <div className="flex flex-col gap-3 pb-10">
                 {isLoading ? (
                     <div className="py-20 text-center text-gray-400 animate-pulse">
                         Carregando...
                     </div>
                 ) : displayItems.length > 0 ? (
                     displayItems.map((item: LicitacaoItem) => (
                         <LicitacaoCard 
                             key={item.id || item.pncp_id || `temp-${Math.random()}`} 
                             item={item} 
                             onAction={handleAction} 
                         />
                     ))
                 ) : (
                     <div className="py-20 text-center border-2 border-dashed border-gray-200 rounded-xl bg-gray-50">
                         <p className="text-gray-500 font-medium">Nenhuma licitação encontrada.</p>
                         <p className="text-xs text-gray-400 mt-1">Tente remover alguns filtros.</p>
                     </div>
                 )}
             </div>
             
              {/* Bottom Pagination */}
             {totalPages > 1 && (
                  <div className="flex justify-center pb-10">
                      <div className="flex items-center gap-2 bg-white p-2 rounded-xl shadow-sm border border-gray-100">
                             <button 
                                disabled={page <= 1}
                                onClick={() => updateFilter("page", String(page - 1))}
                                className="w-8 h-8 flex items-center justify-center rounded hover:bg-tint text-primary disabled:text-secondary disabled:hover:bg-transparent"
                            >
                                <ChevronLeft size={16} />
                            </button>
                            
                            {renderPageNumbers()}
                            
                            <button 
                                disabled={page >= totalPages}
                                onClick={() => updateFilter("page", String(page + 1))}
                                className="w-8 h-8 flex items-center justify-center rounded hover:bg-tint text-primary disabled:text-secondary disabled:hover:bg-transparent"
                            >
                                <ChevronRight size={16} />
                            </button>
                      </div>
                  </div>
             )}

         </div>
      </div>
      
    </div>
  );
}

export default function LicitacoesPage() {
    return (
        <Suspense fallback={<div className="h-screen flex items-center justify-center text-gray-400">Carregando...</div>}>
            <LicitacoesContent />
        </Suspense>
    );
}
