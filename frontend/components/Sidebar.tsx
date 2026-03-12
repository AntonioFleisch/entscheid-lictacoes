import { Trash2, X, Settings, DollarSign, Calendar, MapPin, ShieldCheck, Tags, Filter } from "lucide-react";
import { useSidebarCounts, useSegments, useModalidades } from "@/lib/hooks";
import { CustomSelect } from "./CustomSelect";
import { useState } from "react";
import { SegmentManager } from "./SegmentManager";

export interface FilterState {
    segmento: string;
    valor_min: string;
    valor_max: string;
    capag: string;
    pub_from: string;
    pub_to: string;
    prazo_from: string;
    prazo_to: string;
    expira_em_dias: string;
    uf: string;
    status: string;
    [key: string]: string | number | undefined | null;
}

interface SidebarProps {
    filters: FilterState;
    onUpdate: (key: keyof FilterState, value: string) => void;
    onReset: () => void;
}

export function Sidebar({ filters, onUpdate, onReset }: SidebarProps) {
    const [managerOpen, setManagerOpen] = useState(false);
    const [modalExamplesOpen, setModalExamplesOpen] = useState(false);

    const handleChange = (key: keyof FilterState) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
        onUpdate(key, e.target.value);
    };

    const { counts } = useSidebarCounts(filters);
    const { segments, isLoading: loadingSegs } = useSegments();
    const { modalidadesData } = useModalidades();
    
    const unknownTotal = modalidadesData?.unknown_total || 0;
    const selectedModalidades = typeof filters.modalidades === 'string' && filters.modalidades ? filters.modalidades.split(',') : [];
    const selectedSegmentos = typeof filters.segmento === 'string' && filters.segmento ? filters.segmento.split(',') : [];

    const handleModalidadeToggle = (key: string) => {
        let newSelected = [...selectedModalidades];
        if (newSelected.includes(key)) {
            newSelected = newSelected.filter(k => k !== key);
        } else {
            newSelected.push(key);
        }
        onUpdate('modalidades', newSelected.join(','));
    };

    const handleSegmentoToggle = (slug: string) => {
        let newSelected = [...selectedSegmentos];
        if (newSelected.includes(slug)) {
            newSelected = newSelected.filter(k => k !== slug);
        } else {
            newSelected.push(slug);
        }
        onUpdate('segmento', newSelected.join(','));
        if (filters.status) onUpdate('status', '');
    };

    const activeFiltersCount = Object.values(filters).filter(v => v !== '').length;

    return (
        <>
        <aside className="w-full flex-shrink-0 flex flex-col gap-6 text-sm">

            {/* Header / Clear */}
            <div className="flex items-center justify-between px-1">
                <h2 className="text-xs font-bold text-ink uppercase tracking-widest flex items-center gap-2">
                    Filtros
                    <button onClick={() => setManagerOpen(true)} className="text-secondary hover:text-primary transition-colors" title="Gerenciar Segmentos">
                        <Settings size={14} />
                    </button>
                </h2>
                {activeFiltersCount > 0 && (
                    <button onClick={onReset} className="flex items-center gap-1 text-[10px] text-accent font-bold uppercase hover:bg-tint px-2 py-1 rounded transition-colors">
                        <X size={12} />
                        Limpar
                    </button>
                )}
            </div>

            {/* Segment Selection */}
            <FilterSection title="Segmentos" icon={<Tags size={13} />}>
                <div className="space-y-1">
                    {loadingSegs ? (
                        <div className="text-[12px] text-primary px-3 py-2 italic animate-pulse">Carregando segmentos...</div>
                    ) : (
                        (segments || []).filter((s: { id: string, name: string, is_active: boolean, slug: string }) => 
                            s.is_active && ['diversos', 'kit_escolar', 'almoxarifado_virtual'].includes(s.slug)
                        ).map((seg: { id: string, name: string, slug: string }) => {
                            const isSelected = selectedSegmentos.includes(seg.slug);
                            return (
                                <button
                                    key={seg.id}
                                    onClick={() => handleSegmentoToggle(seg.slug)}
                                    className={`w-full flex items-center justify-between px-3 py-2 transition-colors text-[13px] ${isSelected
                                            ? 'bg-tint text-ink font-semibold border-l-4 border-accent rounded-r-lg'
                                            : 'text-ink hover:bg-tint hover:text-primary rounded-lg border-l-4 border-transparent'
                                        }`}
                                >
                                    <span>{seg.name}</span>
                                    {counts?.segments?.find((s: {slug: string, count: number}) => s.slug === seg.slug)?.count !== undefined && (
                                        <span className={`text-[10px] py-0.5 px-1.5 rounded-full ${isSelected ? 'bg-primary text-white' : 'bg-gray-100 text-primary border border-secondary/30'
                                            }`}>
                                            {counts.segments.find((s: {slug: string, count: number}) => s.slug === seg.slug)?.count}
                                        </span>
                                    )}
                                </button>
                            );
                        })
                    )}
                    


                    {/* Ignoradas Button (Integrated) */}
                    <button
                        onClick={() => {
                            // Set status=ignored, clear segment
                            if (filters.status === 'ignored') {
                                onUpdate('status', '');
                            } else {
                                onUpdate('status', 'ignored');
                                onUpdate('segmento', '');
                            }
                        }}
                        className={`w-full flex items-center justify-between px-3 py-2 transition-colors text-[13px] ${filters.status === 'ignored'
                                ? 'bg-tint text-ink font-semibold border-l-4 border-accent rounded-r-lg'
                                : 'text-ink hover:bg-tint hover:text-primary rounded-lg border-l-4 border-transparent'
                            }`}
                    >
                        <span className="flex items-center gap-2">
                            <Trash2 size={13} />
                            Ignoradas
                        </span>
                        {counts?.ignoradas !== undefined && (
                            <span className={`text-[10px] py-0.5 px-1.5 rounded-full ${filters.status === 'ignored' ? 'bg-primary text-white' : 'bg-gray-100 text-primary border border-secondary/30'
                                }`}>
                                {counts.ignoradas}
                            </span>
                        )}
                    </button>
                </div>
            </FilterSection>

            {/* NEW: Valor (R$) */}
            <FilterSection title="Valor Total" icon={<DollarSign size={13} />}>
                <div className="flex gap-2 items-center">
                    <div className="relative w-full">
                        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs"></span>
                        <input
                            type="number"
                            placeholder="Mínimo"
                            value={filters.valor_min}
                            onChange={handleChange("valor_min")}
                            className="input-base w-full !px-2 !py-2 text-center"
                        />
                    </div>
                    <div className="relative w-full">
                        <span className="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 text-xs"></span>
                        <input
                            type="number"
                            placeholder="Máximo"
                            value={filters.valor_max}
                            onChange={handleChange("valor_max")}
                            className="input-base w-full !px-2 !py-2 text-center"
                        />
                    </div>
                </div>
            </FilterSection>

            {/* NEW: Modalidade */}
            <FilterSection title="Modalidade" icon={<Filter size={13} />}>
                <div className="space-y-1 max-h-48 overflow-y-auto custom-scrollbar pr-1">
                    {counts?.modalidades?.map((mod: {key: string, label: string, count: number}) => {
                        const isSelected = selectedModalidades.includes(mod.key);
                        return (
                            <button
                                key={mod.key}
                                onClick={() => handleModalidadeToggle(mod.key)}
                                className={`w-full flex items-center justify-between px-2 py-1.5 transition-colors text-xs ${isSelected
                                        ? 'bg-tint text-ink font-semibold border-l-4 border-accent rounded-r-md'
                                        : 'text-ink hover:bg-tint hover:text-primary rounded-md border-l-4 border-transparent'
                                    }`}
                            >
                                <span>{mod.label}</span>
                                {mod.count !== undefined && (
                                    <span className={`text-[10px] py-0.5 px-1.5 rounded-full ${isSelected ? 'bg-primary text-white' : 'bg-gray-100 text-primary border border-secondary/30'}`}>
                                        {mod.count}
                                    </span>
                                )}
                            </button>
                        );
                    })}
                    
                    {selectedModalidades.length > 0 && (
                        <button onClick={() => onUpdate('modalidades', '')} className="text-[10px] text-accent uppercase font-bold mt-2 pt-2 border-t border-secondary/30 w-full text-left">
                            Limpar Modalidades
                        </button>
                    )}
                </div>
                
                {unknownTotal > 0 && (
                    <div className="mt-2 pt-2 border-t border-secondary/30">
                        <button onClick={() => setModalExamplesOpen(true)} className="text-[10px] text-blue-900 font-bold uppercase underline hover:text-blue-950 w-full text-left transition-colors">
                            Não mapeadas
                        </button>
                    </div>
                )}
            </FilterSection>

            {/* NEW: Datas e Prazos */}
            <FilterSection title="Datas e Prazos" icon={<Calendar size={13} />}>
                 <div className="flex flex-col gap-3">

                    {/* Expira em */}
                    <div className="space-y-1">
                        <label className="text-[10px] font-semibold text-gray-500 uppercase">Expira em</label>
                        <CustomSelect
                            value={filters.expira_em_dias}
                            onChange={(val) => onUpdate("expira_em_dias", val)}
                            options={[
                                { value: "", label: "Qualquer data" },
                                { value: "7", label: "Próximos 7 dias" },
                                { value: "15", label: "Próximos 15 dias" },
                                { value: "30", label: "Próximos 30 dias" },
                            ]}
                            placeholder="Qualquer data"
                        />
                    </div>
                </div>
            </FilterSection>

            {/* NEW: CAPAG */}
            <FilterSection title="CAPAG" icon={<ShieldCheck size={13} />}>
                <div className="flex flex-col gap-1">
                    <CustomSelect
                        value={filters.capag}
                        onChange={(val) => onUpdate("capag", val)}
                        options={[
                            { value: "", label: "Todas as notas" },
                            { value: "A", label: "Nota A" },
                            { value: "B", label: "Nota B" },
                            { value: "C", label: "Nota C" },
                            { value: "D", label: "Nota D" },
                        ]}
                        placeholder="Todas as notas"
                    />
                    <p className="text-[10px] text-primary opacity-60 px-1 leading-tight mt-1">
                        Indicador externo do ente. Pode não estar disponível para todos.
                    </p>
                </div>
            </FilterSection>

            {/* NEW: Localização (UF) */}
            <FilterSection title="Localização (UF)" icon={<MapPin size={13} />}>
                <CustomSelect
                    value={filters.uf}
                    onChange={(val) => onUpdate("uf", val)}
                    options={[
                        { value: "", label: "Brasil (Todos)" },
                        ...['AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT', 'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO'].map(uf => ({ value: uf, label: uf }))
                    ]}
                    placeholder="Brasil (Todos)"
                />
            </FilterSection>

            <div className="h-20" /> {/* Spacer for bottom dropdowns */}
        </aside>
        <SegmentManager isOpen={managerOpen} onClose={() => setManagerOpen(false)} />
        
        {/* Modalities Examples Modal */}
        {modalExamplesOpen && (
            <div className="fixed inset-0 bg-ink/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                <div className="bg-white rounded-2xl w-full max-w-lg overflow-hidden shadow-2xl flex flex-col">
                    <div className="px-6 py-4 bg-tint/30 border-b border-secondary/30 flex justify-between items-center">
                        <h2 className="text-sm font-bold text-ink uppercase tracking-wider flex items-center gap-2">
                            <Filter size={16} className="text-primary" />
                            Modalidades Não Mapeadas
                        </h2>
                        <button onClick={() => setModalExamplesOpen(false)} className="text-secondary hover:text-accent transition-colors">
                            <X size={20} />
                        </button>
                    </div>
                    
                    <div className="p-6 overflow-y-auto max-h-[70vh]">
                        <p className="text-sm text-gray-600 mb-4">
                            Estas são as modalidades que o sistema encontrou nos dados, mas que ainda não possuem um mapeamento canônico no filtro.
                        </p>
                        
                        {(modalidadesData?.unknown_by_code?.length > 0 || modalidadesData?.unknown_by_name?.length > 0) ? (
                            <div className="space-y-4">
                                {modalidadesData?.unknown_by_code?.length > 0 && (
                                    <div>
                                        <h3 className="text-xs font-bold text-primary mb-2 uppercase">Com Código PNCP</h3>
                                        <div className="space-y-2">
                                            {modalidadesData.unknown_by_code.map((u: {code: number, label: string, count: number}, idx: number) => (
                                                <div key={idx} className="flex justify-between items-center text-xs bg-gray-50 p-2 rounded border border-gray-100">
                                                    <span><span className="font-mono text-gray-500 mr-2">[{u.code}]</span> {u.label}</span>
                                                    <span className="font-bold text-gray-500">{u.count} itens</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                
                                {modalidadesData?.unknown_by_name?.length > 0 && (
                                    <div>
                                        <h3 className="text-xs font-bold text-primary mb-2 uppercase">Sem Código (Só Texto)</h3>
                                        <div className="space-y-2">
                                            {modalidadesData.unknown_by_name.map((u: {name: string, count: number}, idx: number) => (
                                                <div key={idx} className="flex justify-between items-center text-xs bg-gray-50 p-2 rounded border border-gray-100">
                                                    <span>{u.name}</span>
                                                    <span className="font-bold text-gray-500">{u.count} itens</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                
                                {modalidadesData?.examples?.length > 0 && (
                                    <div className="mt-4 pt-4 border-t border-gray-100">
                                        <h3 className="text-xs font-bold text-primary mb-2 uppercase">Exemplos de Licitações</h3>
                                        <ul className="text-xs space-y-1 list-disc pl-4 text-gray-600">
                                            {modalidadesData.examples.map((ex: {pncp_id: string, modalidade_codigo: number, modalidade_nome: string}, idx: number) => (
                                                <li key={idx}>
                                                    PNCP ID: <a href={`https://pncp.gov.br/app/editais?q=${ex.pncp_id}`} target="_blank" rel="noreferrer" className="text-primary hover:underline">{ex.pncp_id}</a>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        ) : (
                            <div className="text-center py-8 text-gray-400 italic">
                                Sem modalidades adicionais no momento.
                            </div>
                        )}
                    </div>
                </div>
            </div>
        )}
        </>
    );
}

function FilterSection({ title, icon, children }: { title: string, icon?: React.ReactNode, children: React.ReactNode }) {
    return (
        <div className="border border-secondary/30 rounded-xl bg-white shadow-sm">
            <div className="px-3 py-2 bg-tint/30 border-b border-secondary/30 rounded-t-xl">
                <div className="text-[11px] font-bold text-primary uppercase tracking-tight flex items-center gap-1.5 focus:outline-none select-none">
                    {icon} {title}
                </div>
            </div>

            <div className="px-3 pb-3 pt-3">
                {children}
            </div>
        </div>
    )
}
