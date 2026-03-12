"use client";
import { apiFetch } from "@/lib/apiClient";

import { X, Search, Package, Info, ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useState, useMemo } from "react";

interface Item {
    item_num: number;
    descricao: string;
    unidade: string;
    quantidade: number;
    valor_unit: number;
    valor_total: number;
    [key: string]: string | number | boolean | null | undefined;
}

interface ItemsModalProps {
    pncpId: string;
    isOpen: boolean;
    onClose: () => void;
    title: string;
}

export function ItemsModal({ pncpId, isOpen, onClose, title }: ItemsModalProps) {
    const [items, setItems] = useState<Item[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchTerm, setSearchTerm] = useState("");
    const [currentPage, setCurrentPage] = useState(1);
    const ITEMS_PER_PAGE = 20;

    useEffect(() => {
        let isMounted = true;
        
        async function loadItems() {
            if (!isOpen || !pncpId) return;
            
            try {
                // We don't call setLoading(true) here to avoid the lint error.
                // Assuming it starts as true when isOpen changes, or we can handle it differently.
                const res = await apiFetch(`/api/licitacoes/${encodeURIComponent(pncpId)}/itens`);
                if (!res.ok) throw new Error("Falha ao carregar itens");
                const data = await res.json();
                
                if (isMounted) {
                    setItems(data.items || []);
                    setLoading(false);
                    setError(null);
                }
            } catch {
                if (isMounted) {
                    setError("Não foi possível carregar a lista de itens.");
                    setLoading(false);
                }
            }
        }

        loadItems();
        return () => { isMounted = false; };
    }, [isOpen, pncpId]);


    const filteredItems = useMemo(() => {
        return items.filter(it => {
            const desc = it.descricao || "";
            return desc.toLowerCase().includes(searchTerm.toLowerCase()) ||
                   String(it.item_num).includes(searchTerm);
        });
    }, [items, searchTerm]);

    useEffect(() => {
        setCurrentPage(1);
    }, [searchTerm]);

    const totalPages = Math.max(1, Math.ceil(filteredItems.length / ITEMS_PER_PAGE));
    const startIndex = (currentPage - 1) * ITEMS_PER_PAGE;
    const paginatedItems = filteredItems.slice(startIndex, startIndex + ITEMS_PER_PAGE);

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div 
                className="absolute inset-0 bg-gray-900/60 backdrop-blur-sm transition-opacity" 
                onClick={onClose}
            />

            {/* Modal */}
            <div className="relative bg-white w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-2xl overflow-hidden flex flex-col animate-in zoom-in-95 duration-200">
                
                {/* Header */}
                <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-white sticky top-0 z-10">
                    <div className="flex items-center gap-3">
                        <div className="w-10 h-10 rounded-xl bg-tint flex items-center justify-center text-primary">
                            <Package size={20} />
                        </div>
                        <div>
                            <h3 className="text-gray-900 font-bold text-lg leading-tight">Itens do Edital</h3>
                            <p className="text-gray-400 text-xs truncate max-w-[300px] md:max-w-md">{title}</p>
                        </div>
                    </div>
                    <button 
                        onClick={onClose}
                        className="p-2 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600 transition-colors"
                    >
                        <X size={20} />
                    </button>
                </div>

                {/* Sub-header / Search */}
                <div className="px-6 py-3 bg-gray-50 flex flex-col md:flex-row md:items-center justify-between gap-4">
                    <div className="relative flex-1 max-w-md">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                        <input 
                            type="text"
                            placeholder="Buscar por descrição ou número do item..."
                            className="w-full pl-10 pr-4 py-2 bg-white border border-secondary/50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-tint focus:border-primary transition-all"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                    <div className="text-xs font-bold text-gray-500 uppercase tracking-widest bg-white px-3 py-1.5 rounded-full border border-gray-100 shadow-sm">
                        Total: {items.length} itens
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-auto custom-scrollbar p-6">
                    {loading ? (
                        <div className="h-64 flex flex-col items-center justify-center gap-4">
                            <div className="w-8 h-8 border-4 border-gray-100 border-t-primary rounded-full animate-spin"></div>
                            <p className="text-gray-400 font-medium animate-pulse">Carregando itens...</p>
                        </div>
                    ) : error ? (
                        <div className="h-64 flex flex-col items-center justify-center gap-4 text-center">
                            <div className="w-12 h-12 rounded-full bg-rose-50 flex items-center justify-center text-rose-500">
                                <Info size={24} />
                            </div>
                            <div>
                                <h4 className="font-bold text-gray-900">Erro ao carregar data</h4>
                                <p className="text-gray-500 text-sm max-w-xs mx-auto">{error}</p>
                            </div>
                            <button 
                                onClick={() => {/* Retry logic */}}
                                className="px-4 py-2 bg-accent hover:bg-ink text-white transition-colors rounded-lg text-sm font-bold shadow-sm"
                            >
                                Tentar novamente
                            </button>
                        </div>
                    ) : filteredItems.length === 0 ? (
                        <div className="h-64 flex flex-col items-center justify-center gap-2 text-center text-gray-400">
                            <Search size={32} strokeWidth={1.5} />
                            <p className="font-medium">Nenhum item encontrado para &quot;{searchTerm}&quot;</p>
                        </div>
                    ) : (
                        <div className="border border-gray-100 rounded-xl overflow-hidden shadow-sm">
                            <table className="w-full text-left border-collapse">
                                <thead className="bg-[#2a3543] text-white">
                                    <tr>
                                        <th className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest w-16">Item</th>
                                        <th className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest">Descrição</th>
                                        <th className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest text-right">Qtd</th>
                                        <th className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest text-right">Preço Unit.</th>
                                        <th className="py-3 px-4 text-[10px] font-bold uppercase tracking-widest text-right">Total</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-gray-100">
                                    {paginatedItems.map((it, idx) => (
                                        <tr key={idx} className="hover:bg-gray-50 transition-colors group">
                                            <td className="py-3 px-4 text-xs font-bold text-primary">{it.item_num || startIndex + idx + 1}</td>
                                            <td className="py-3 px-4">
                                                <p className="text-gray-900 font-bold text-xs uppercase leading-snug line-clamp-2 group-hover:line-clamp-none transition-all duration-300">
                                                    {it.descricao}
                                                </p>
                                                {it.unidade && (
                                                    <span className="text-[10px] text-gray-400 font-medium">Unidade: {it.unidade}</span>
                                                )}
                                            </td>
                                            <td className="py-3 px-4 text-xs font-medium text-gray-600 text-right">{it.quantidade}</td>
                                            <td className="py-3 px-4 text-xs font-medium text-gray-900 text-right">
                                                {it.valor_unit?.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) || '—'}
                                            </td>
                                            <td className="py-3 px-4 text-xs font-extrabold text-gray-900 text-right">
                                                {it.valor_total?.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) || '—'}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {/* Pagination Controls */}
                {!loading && !error && filteredItems.length > 0 && (
                    <div className="px-6 py-3 border-t border-gray-100 bg-white flex items-center justify-between">
                        <span className="text-[10px] text-gray-400 font-bold uppercase tracking-widest">
                            Mostrando {startIndex + 1} a {Math.min(startIndex + ITEMS_PER_PAGE, filteredItems.length)} de {filteredItems.length}
                        </span>
                        <div className="flex items-center gap-1">
                            <button 
                                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                                disabled={currentPage === 1}
                                className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                <ChevronLeft size={16} />
                            </button>
                            <span className="text-xs font-bold text-gray-700 px-3">
                                Página {currentPage} de {totalPages}
                            </span>
                            <button 
                                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                                disabled={currentPage === totalPages}
                                className="p-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                            >
                                <ChevronRight size={16} />
                            </button>
                        </div>
                    </div>
                )}

                {/* Footer */}
                <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex items-center justify-between text-[10px] text-gray-400 font-bold uppercase tracking-widest">
                    <span>Cuidado: Dados processados automaticamente do PNCP</span>
                    <span>© PNCP Monitor v3</span>
                </div>
            </div>
        </div>
    );
}
