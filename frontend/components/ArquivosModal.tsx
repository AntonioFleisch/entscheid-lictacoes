"use client";
import { apiFetch } from "@/lib/apiClient";

import { useState } from "react";
import { ChevronDown, Eye, Download, FileText } from "lucide-react";

interface Arquivo {
    doc_seq: number;
    titulo: string;
    url: string;
    tipo_documento_id?: number;
    tipo_documento_nome: string;
    created_at: string;
}

interface ArquivosModalProps {
    isOpen: boolean;
    onClose: () => void;
    pncpId: string;
    title: string;
}

export function ArquivosModal({ isOpen, onClose, pncpId, title }: ArquivosModalProps) {
    const [files, setFiles] = useState<Arquivo[]>([]);
    const [loading, setLoading] = useState(false);

    const loadFiles = async () => {
        setLoading(true);
        try {
            const encodedId = encodeURIComponent(pncpId);
            const res = await apiFetch(`/api/licitacoes/${encodedId}/arquivos`);
            if (!res.ok) throw new Error("Failed to load");
            const data = await res.json();
            setFiles(data.files || []);
        } catch (e) {
            console.error("Failed to load arquivos", e);
        } finally {
            setLoading(false);
        }
    };

    // Use a simple effect-like logic since we are in a functional component
    // but the component might be unmounted/remounted.
    // However, since it's controlled by isOpen, we can trigger on open.
    if (isOpen && files.length === 0 && !loading) {
        loadFiles();
    }

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-md z-[100] flex items-center justify-center p-4">
            <div className="bg-white rounded-3xl w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden border border-gray-100 animate-in zoom-in-95 duration-200">
                
                {/* Header */}
                <div className="p-8 border-b border-gray-100 flex items-center justify-between bg-gradient-to-br from-gray-50 to-white">
                    <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-2xl bg-tint flex items-center justify-center text-primary shadow-inner">
                            <FileText size={24} />
                        </div>
                        <div>
                            <h3 className="text-xl font-bold text-gray-900 line-clamp-1">{title}</h3>
                            <div className="flex items-center gap-2 mt-1">
                                <span className="text-[10px] bg-gray-900 text-white px-2 py-0.5 rounded font-bold uppercase tracking-wider">PNCP</span>
                                <p className="text-xs text-gray-500 font-bold tracking-tight">{pncpId}</p>
                            </div>
                        </div>
                    </div>
                    <button 
                        onClick={onClose} 
                        className="p-2.5 hover:bg-gray-200 rounded-full transition-all hover:rotate-90"
                    >
                        <ChevronDown className="rotate-180 text-gray-400" size={28} />
                    </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-8 bg-gray-50/30">
                    {loading ? (
                        <div className="flex flex-col items-center justify-center py-24 gap-6">
                            <div className="relative">
                                <div className="w-16 h-16 border-4 border-secondary/30 rounded-full"></div>
                                <div className="absolute top-0 left-0 w-16 h-16 border-4 border-t-primary rounded-full animate-spin"></div>
                            </div>
                            <p className="text-sm font-bold text-gray-400 uppercase tracking-widest animate-pulse">
                                Indexando Documentos...
                            </p>
                        </div>
                    ) : (
                        <div className="grid gap-4">
                            {files.length > 0 ? (
                                files.map((file, idx) => (
                                    <a 
                                        key={idx} 
                                        href={file.url} 
                                        target="_blank" 
                                        rel="noopener noreferrer" 
                                        className="group bg-white flex items-center justify-between p-5 rounded-2xl border border-gray-100 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5 transition-all active:scale-[0.99]"
                                    >
                                        <div className="flex items-center gap-5">
                                            <div className="w-12 h-12 rounded-xl bg-gray-50 flex items-center justify-center text-gray-400 group-hover:bg-tint group-hover:text-primary transition-all">
                                                <Eye size={22} />
                                            </div>
                                            <div>
                                                <p className="text-sm font-bold text-gray-900 group-hover:text-primary transition-colors line-clamp-1">
                                                    {file.titulo || `Documento Sequencial ${file.doc_seq}`}
                                                </p>
                                                <div className="flex items-center gap-3 mt-1">
                                                    <span className="text-[9px] font-black text-primary uppercase tracking-widest">{file.tipo_documento_nome || 'ANEXO'}</span>
                                                    {file.created_at && (
                                                        <span className="text-[10px] text-gray-400 font-medium italic">
                                                            {new Date(file.created_at).toLocaleDateString('pt-BR')}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-2 px-5 py-2.5 bg-primary group-hover:bg-ink text-white text-[11px] font-black uppercase tracking-widest rounded-xl shadow-md transition-all">
                                            <Download size={14} className="mr-1" />
                                            Baixar
                                        </div>
                                    </a>
                                ))
                            ) : (
                                <div className="flex flex-col items-center justify-center py-20 bg-white rounded-2xl border border-dashed border-gray-200">
                                    <FileText size={48} className="text-gray-200 mb-4" />
                                    <p className="text-gray-400 font-bold uppercase tracking-widest text-sm">Nenhum documento disponível</p>
                                    <p className="text-xs text-gray-400 mt-2">Os arquivos podem não ter sido publicados no PNCP para este edital.</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Footer Advice */}
                <div className="p-6 bg-white border-t border-gray-100">
                    <div className="flex items-center gap-3 p-4 bg-tint rounded-2xl border border-secondary text-ink">
                        <div className="p-2 bg-white rounded-lg shadow-sm">
                            <Download size={18} className="text-primary" />
                        </div>
                        <p className="text-[11px] font-medium leading-relaxed">
                            <strong>Dica Antigravity:</strong> O Edital e o Termo de Referência costumam ser os documentos mais importantes para análise técnica.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}
