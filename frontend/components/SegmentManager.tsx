import { useState, useEffect } from "react";
import { X, Plus, Trash2, Edit2, Play, AlertTriangle } from "lucide-react";
import { useSegments, useJobStatus } from "@/lib/hooks";
import { apiFetch } from "@/lib/apiClient";
import { CustomSelect } from "./CustomSelect";

interface SegmentManagerProps {
    isOpen: boolean;
    onClose: () => void;
}

export function SegmentManager({ isOpen, onClose }: SegmentManagerProps) {
    const { segments, mutate: mutateSegments } = useSegments();
    const [selectedSegId, setSelectedSegId] = useState<string | null>(null);
    const [jobId, setJobId] = useState<string | null>(() => {
        if (typeof window !== 'undefined') return localStorage.getItem('reclassify_job_id');
        return null;
    });

    const { job } = useJobStatus(jobId);

    // Form states
    const [isEditing, setIsEditing] = useState(false);
    const [formData, setFormData] = useState({ slug: '', name: '', priority: 0, match_mode: 'ANY', min_hits: 1 });
    const [newTerm, setNewTerm] = useState({ term: '', term_type: 'include', group_id: '' });
    const [formErrors, setFormErrors] = useState<Record<string, string>>({});

    // Job persistence
    useEffect(() => {
        if (jobId) localStorage.setItem('reclassify_job_id', jobId);
        else localStorage.removeItem('reclassify_job_id');
    }, [jobId]);

    // Clear job if done or error
    useEffect(() => {
        if (job && (job.status === 'done' || job.status === 'error')) {
            mutateSegments();
            setTimeout(() => setJobId(null), 5000); // Clear after 5s
        }
    }, [job, mutateSegments]);

    if (!isOpen) return null;

    const isJobRunning = job?.status === 'pending' || job?.status === 'running';
    const selectedSeg = segments?.find((s: { id: string, name: string, slug: string, priority: number, match_mode: string, terms?: { id: string, term: string, term_type: string, group_id?: string }[] }) => s.id === selectedSegId);

    const handleSaveSegment = async () => {
        const errors: Record<string, string> = {};
        if (!formData.name.trim()) errors.name = "Nome é obrigatório.";
        if (!selectedSegId) {
            if (!formData.slug.trim()) errors.slug = "Slug é obrigatório.";
            else if (!/^[a-z0-9_]+$/.test(formData.slug)) errors.slug = "Use letras minúsculas, números e underscore.";
        }
        if (formData.min_hits < 1) errors.min_hits = "Deve ser no mínimo 1.";
        
        if (Object.keys(errors).length > 0) {
            setFormErrors(errors);
            return;
        }
        setFormErrors({});

        const url = isEditing && selectedSegId ? `/api/segments/${selectedSegId}` : '/api/segments';
        const method = isEditing && selectedSegId ? 'PATCH' : 'POST';
        
        const res = await fetch(url, {
            method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(formData)
        });
        if (res.ok) {
            mutateSegments();
            setIsEditing(false);
            if (!isEditing) setSelectedSegId(null);
        } else {
            alert('Erro ao salvar segmento.');
        }
    };

    const handleDeleteSegment = async (id: string) => {
        const slugToDelete = segments?.find((s: { id: string, slug: string }) => s.id === id)?.slug;
        if (slugToDelete === 'diversos') {
            alert('Não é possível excluir o segmento padrão (Diversos).');
            return;
        }
        if (!confirm('Excluir este segmento?')) return;
        const res = await apiFetch(`/api/segments/${id}`, { method: 'DELETE' });
        if (res.ok) {
            mutateSegments();
            if (selectedSegId === id) setSelectedSegId(null);
        }
    };

    const handleAddTerm = async () => {
        if (!selectedSegId || !newTerm.term.trim()) return;
        const res = await fetch(`/api/segments/${selectedSegId}/terms`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newTerm)
        });
        if (res.ok) {
            mutateSegments();
            setNewTerm({ term: '', term_type: 'include', group_id: '' });
        }
    };

    const handleDeleteTerm = async (termId: string) => {
        const res = await apiFetch(`/api/segments/${selectedSegId}/terms/${termId}`, { method: 'DELETE' });
        if (res.ok) mutateSegments();
    };    

    const handleReclassify = async () => {
        if (!confirm('Iniciar reclassificação? Isso aplicará as regras geradas a todos os itens não-ignorados do banco. Operação pode demorar.')) return;
        const res = await apiFetch('/api/segments/reclassify', { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            setJobId(data.job_id);
        } else {
            alert(res.status === 409 ? 'Job já em andamento.' : 'Erro ao iniciar job.');
        }
    };

    return (
        <div className="fixed inset-0 z-[100] flex justify-end bg-black/30 backdrop-blur-sm">
            <div className="w-full max-w-[960px] sm:w-[92vw] h-full bg-white shadow-2xl flex flex-col animate-in slide-in-from-right-8 duration-300 overflow-x-hidden">
                {/* Header */}
                <div className="flex items-center justify-between p-4 border-b">
                    <h2 className="text-lg font-bold text-gray-800">Gerenciar Segmentos</h2>
                    <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-full transition text-gray-500">
                        <X size={20} />
                    </button>
                </div>

                {/* Job Warning Area */}
                <div className="p-4 border-b bg-gray-50 flex items-center justify-between">
                    {isJobRunning ? (
                    <div className="flex items-center gap-3 text-accent bg-tint px-4 py-3 rounded-lg w-full border border-secondary/50">
                            <AlertTriangle size={20} className="animate-pulse" />
                            <div className="flex flex-col flex-1">
                                <span className="font-bold text-sm">Reclassificação em Andamento</span>
                                <span className="text-[11px]">A edição de regras está bloqueada. Processados: {job?.processed || 0} (Erros: {job?.errors || 0})</span>
                            </div>
                        </div>
                    ) : (
                        <div className="flex items-center justify-between w-full">
                            <span className="text-xs text-gray-500 max-w-[280px]">
                                Use este painel para editar regras de segmentação. As mudanças só valem após reclassificar.
                            </span>
                            <button 
                                onClick={handleReclassify} 
                                className="flex items-center gap-2 bg-primary hover:bg-ink text-white px-4 py-2 rounded-lg text-[13px] font-semibold transition"
                            >
                                <Play size={14} />
                                Reclassificar Base
                            </button>
                        </div>
                    )}
                </div>

                <div className="flex-1 overflow-auto flex">
                    {/* Left Sidebar: Segment List */}
                    <div className="w-1/3 border-r bg-gray-50/50 flex flex-col h-full">
                        <div className="p-3">
                            <button 
                                disabled={isJobRunning}
                                onClick={() => { setIsEditing(true); setSelectedSegId(null); setFormData({ slug: '', name: '', priority: 0, match_mode: 'ANY', min_hits: 1 }); setFormErrors({}); }}
                                className="w-full py-2 bg-gray-800 text-white border shadow-sm rounded-lg text-xs font-semibold hover:bg-gray-900 flex items-center justify-center gap-2 disabled:opacity-50 transition-colors"
                            >
                                <Plus size={14} /> Novo Segmento
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto overflow-x-hidden">
                            {(segments || []).map((seg: { id: string, name: string, slug: string, priority: number, terms?: { id: string, term: string, term_type: string, group_id?: string }[] }) => (
                                <div 
                                    key={seg.id} 
                                    className={`px-4 py-3 border-b cursor-pointer transition ${selectedSegId === seg.id ? 'bg-tint border-l-4 border-l-accent' : 'hover:bg-gray-100 border-l-4 border-l-transparent'} ${seg.slug === 'diversos' ? 'opacity-70' : ''}`}
                                    onClick={() => { setSelectedSegId(seg.id); setIsEditing(false); setFormErrors({}); }}
                                >
                                    <div className="font-medium text-sm text-gray-800">{seg.name}</div>
                                    <div className="text-[10px] text-gray-500 py-1">{seg.terms?.length || 0} termos • Pri: {seg.priority}</div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Right Panel: Segment Details & Form */}
                    <div className="flex-1 flex flex-col relative h-full bg-white min-w-0">
                        {isJobRunning && <div className="absolute inset-0 bg-white/50 backdrop-blur-[1px] z-10" />}

                        {!selectedSegId && !isEditing ? (
                            <div className="flex-1 flex items-center justify-center text-gray-400 text-sm italic">
                                Selecione um segmento ou crie um novo
                            </div>
                        ) : isEditing ? (
                            <div className="p-6 space-y-5">
                                <h3 className="font-bold text-slate-900 border-b pb-2 mb-4">{selectedSegId ? 'Editar Segmento' : 'Novo Segmento'}</h3>
                                <div>
                                    <label className="block text-xs font-bold text-slate-800 mb-1">Nome <span className="text-red-500">*</span></label>
                                    <input 
                                        value={formData.name} 
                                        onChange={e => {
                                            const val = e.target.value;
                                            if (!selectedSegId) {
                                                const slugify = (text: string) => text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\s+/g, '_').replace(/[^\w_]/g, '');
                                                const currentSlug = formData.slug;
                                                const expectedSlug = slugify(formData.name);
                                                if (!currentSlug || currentSlug === expectedSlug) {
                                                    setFormData({ ...formData, name: val, slug: slugify(val) });
                                                    setFormErrors({ ...formErrors, name: '', slug: '' });
                                                    return;
                                                }
                                            }
                                            setFormData({ ...formData, name: val });
                                            setFormErrors({ ...formErrors, name: '' });
                                        }} 
                                        className={`w-full border ${formErrors.name ? 'border-red-500' : 'border-gray-300'} rounded p-2 text-sm placeholder:text-slate-400`} 
                                        placeholder="Ex: Informática" 
                                    />
                                    {formErrors.name && <div className="text-[10px] text-red-500 mt-1">{formErrors.name}</div>}
                                </div>
                                {!selectedSegId && (
                                    <div>
                                        <label className="block text-xs font-bold text-slate-800 mb-1">Slug (único) <span className="text-red-500">*</span></label>
                                        <input value={formData.slug} onChange={e => {setFormData({...formData, slug: e.target.value}); setFormErrors({...formErrors, slug: ''})}} className={`w-full border ${formErrors.slug ? 'border-red-500' : 'border-gray-300'} rounded p-2 text-sm placeholder:text-slate-400`} placeholder="Ex: informatica" />
                                        {formErrors.slug && <div className="text-[10px] text-red-500 mt-1">{formErrors.slug}</div>}
                                    </div>
                                )}
                                <div>
                                    <label className="block text-xs font-bold text-slate-800 mb-1">Prioridade</label>
                                    <input type="number" value={formData.priority} onChange={e => setFormData({...formData, priority: parseInt(e.target.value) || 0})} className="w-full border-gray-300 border rounded p-2 text-sm placeholder:text-slate-400" />
                                    <span className="text-[11px] text-slate-600">Valores maiores são avaliados primeiro (0-100).</span>
                                </div>
                                <div>
                                    <div className="flex items-center gap-1 mb-1">
                                        <label className="block text-xs font-bold text-slate-800">Modo de Combinação</label>
                                        <span className="text-slate-500 cursor-help" title="ANY: Basta um termo bater. ALL: Todos os termos devem bater (útil para exclusão/obrigatórios).">ⓘ</span>
                                    </div>
                                    <CustomSelect
                                        value={formData.match_mode}
                                        onChange={(val) => setFormData({...formData, match_mode: val})}
                                        options={[
                                            { value: "ANY", label: "QUALQUER termo (ANY)" },
                                            { value: "ALL", label: "TODOS os termos (ALL)" }
                                        ]}
                                    />
                                </div>
                                <div>
                                    <div className="flex items-center gap-1 mb-1">
                                        <label className="block text-xs font-bold text-slate-800">Mínimo de termos para classificar (min_hits)</label>
                                        <span className="text-slate-500 cursor-help" title="Ex.: 2 = precisa identificar pelo menos 2 termos deste segmento nos itens da licitação.">ⓘ</span>
                                    </div>
                                    <input type="number" min="1" value={formData.min_hits || 1} onChange={e => {setFormData({...formData, min_hits: parseInt(e.target.value) || 1}); setFormErrors({...formErrors, min_hits: ''})}} className={`w-full border ${formErrors.min_hits ? 'border-red-500' : 'border-gray-300'} rounded p-2 text-sm placeholder:text-slate-400`} />
                                    {formErrors.min_hits && <div className="text-[10px] text-red-500 mt-1">{formErrors.min_hits}</div>}
                                </div>
                                <div className="pt-4 border-t mt-6">
                                    <div className="text-[11px] text-accent font-medium mb-3">
                                        As alterações só valem após reclassificar a base.
                                    </div>
                                    <div className="flex gap-2">
                                        <button onClick={handleSaveSegment} className="bg-accent hover:bg-ink text-white px-5 py-2 rounded text-sm font-semibold transition shadow-sm">Salvar</button>
                                        <button onClick={() => { setIsEditing(false); if (!selectedSegId) setSelectedSegId(null); setFormErrors({}); }} className="border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 px-5 py-2 rounded text-sm font-semibold transition">Cancelar</button>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            <div className="flex flex-col h-full">
                                <div className="p-5 border-b bg-gray-50 shrink-0">
                                    <div className="grid grid-cols-[1fr_auto] gap-3 items-center">
                                        <div className="min-w-0">
                                            <h3 className="font-bold text-lg text-gray-800 truncate">{selectedSeg?.name}</h3>
                                            <div className="text-xs text-gray-500 mt-1 truncate">Slug: {selectedSeg?.slug} • Pri: {selectedSeg?.priority} • Modo: {selectedSeg?.match_mode}</div>
                                        </div>
                                        <div className="flex gap-2 flex-wrap justify-end">
                                            <button onClick={() => { setFormData({ slug: selectedSeg?.slug, name: selectedSeg?.name, priority: selectedSeg?.priority, match_mode: selectedSeg?.match_mode, min_hits: selectedSeg?.min_hits || 1 }); setIsEditing(true); setFormErrors({}); }} className="p-1.5 text-gray-500 hover:text-primary bg-white rounded border shadow-sm"><Edit2 size={14}/></button>
                                            <button onClick={() => handleDeleteSegment(selectedSeg?.id)} className="p-1.5 text-red-500 hover:bg-red-50 bg-white rounded border shadow-sm" disabled={selectedSeg?.slug === 'diversos'} title={selectedSeg?.slug === 'diversos' ? "Não é possível apagar este segmento padrão" : "Excluir segmento"}><Trash2 size={14}/></button>
                                        </div>
                                    </div>
                                </div>

                                {/* Terms List */}
                                <div className="flex-1 p-5 overflow-y-auto overflow-x-hidden min-h-0">
                                    <h4 className="text-[11px] font-bold tracking-widest uppercase text-gray-400 mb-3 border-b pb-1">Regras ({selectedSeg?.terms?.length || 0})</h4>
                                    
                                    <div className="space-y-2 mb-6">
                                        {(selectedSeg?.terms || []).map((t: { id: string, term: string, term_type: string, group_id?: string }) => (
                                            <div key={t.id} className="flex flex-wrap sm:flex-nowrap items-center justify-between p-2.5 bg-white border border-gray-100 rounded-lg shadow-sm text-sm group gap-2">
                                                <div className="flex flex-wrap items-center gap-2 min-w-0">
                                                    <span className={`text-[10px] uppercase font-bold px-1.5 py-0.5 rounded shrink-0 ${t.term_type === 'include' ? 'bg-tint text-primary border border-secondary/50' : t.term_type === 'exclude' ? 'bg-accent text-white border border-accent' : 'bg-primary text-white border border-primary'}`}>
                                                        {t.term_type}
                                                    </span>
                                                    <span className="font-mono text-gray-800 break-all">{t.term}</span>
                                                    {t.group_id && <span className="text-[10px] text-gray-400 border px-1 rounded shrink-0">Grupo: {t.group_id}</span>}
                                                </div>
                                                <button onClick={() => handleDeleteTerm(t.id)} className="text-gray-400 hover:text-red-500 transition sm:opacity-0 group-hover:opacity-100 shrink-0 p-1"><Trash2 size={16}/></button>
                                            </div>
                                        ))}
                                        {(!selectedSeg?.terms || selectedSeg.terms.length === 0) && (
                                            <div className="text-center text-gray-400 text-sm italic py-4">Nenhum termo associado.</div>
                                        )}
                                    </div>

                                    {/* Add Term Form */}
                                    <div className="bg-gray-50 p-3 rounded-lg border border-gray-200 mt-auto shrink-0">
                                        <div className="text-xs font-semibold text-gray-600 mb-2">Adicionar Regra</div>
                                        <div className="flex flex-wrap gap-2 items-center">
                                            <input 
                                                value={newTerm.term} 
                                                onChange={e => setNewTerm({...newTerm, term: e.target.value})} 
                                                onKeyDown={e => e.key === 'Enter' && handleAddTerm()}
                                                placeholder="Expressão exata (ex: resma)" 
                                                className="flex-1 min-w-[200px] border rounded px-2 py-1.5 text-sm" 
                                            />
                                            <div className="w-full sm:w-[130px]">
                                                <CustomSelect
                                                    value={newTerm.term_type}
                                                    onChange={(val) => setNewTerm({...newTerm, term_type: val})}
                                                    options={[
                                                        { value: "include", label: "INCLUIR" },
                                                        { value: "exclude", label: "EXCLUIR" },
                                                        { value: "required", label: "OBRIGATÓRIO" }
                                                    ]}
                                                    className="text-xs shrink-0"
                                                    labelClassName="py-1.5"
                                                />
                                            </div>
                                            <input 
                                                value={newTerm.group_id} 
                                                onChange={e => setNewTerm({...newTerm, group_id: e.target.value})} 
                                                onKeyDown={e => e.key === 'Enter' && handleAddTerm()}
                                                placeholder="Grupo (A/B)" 
                                                className="w-full sm:w-[100px] border rounded px-2 py-1.5 text-xs" 
                                            />
                                            <button 
                                                onClick={handleAddTerm}
                                                disabled={!newTerm.term.trim()}
                                                className="bg-primary w-full sm:w-auto text-white px-4 py-1.5 border border-transparent hover:bg-ink disabled:bg-secondary disabled:cursor-not-allowed rounded text-sm transition font-medium flex items-center justify-center gap-1"
                                            >
                                                <Plus size={16}/>
                                                <span className="sm:hidden">Adicionar</span>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
