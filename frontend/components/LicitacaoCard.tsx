import { apiFetch } from "@/lib/apiClient";
import { Share2, Eye, ChevronDown, ChevronUp, Info, Ban, RotateCcw, FileText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { ItemsModal } from "./ItemsModal";
import { ArquivosModal } from "./ArquivosModal";


export interface LicitacaoItem {
  id?: string;
  pncp_id?: string;
  numeroControlePNCP?: string;
  deadline_at?: string;
  deadline_raw?: string;
  deadline_kind?: 'HAS_DEADLINE' | 'NO_DEADLINE' | 'UNKNOWN';
  modalidade_nome?: string;
  situacao_nome?: string;
  workflow_status?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export interface LicitacaoCardProps {
  item: LicitacaoItem;
  onAction?: (item: LicitacaoItem, action: 'ignore' | 'unignore') => Promise<void>;
}

export function LicitacaoCard({ item, onAction }: LicitacaoCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isRemoved, setIsRemoved] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isArquivosModalOpen, setIsArquivosModalOpen] = useState(false);

  const handleTriagingAction = async (action: 'ignore' | 'unignore') => {
      // If parent handler provided, delegate control
      if (onAction) {
          setIsUpdating(true);
          try {
              await onAction(item, action);
          } catch (e) {
              console.error("Action failed", e);
              setIsUpdating(false); // Only stop updating on error (success means unmount)
          }
          return;
      }

      // Fallback: Internal Logic
      setIsRemoved(true);
      setIsUpdating(true);

      const pncp_id = item.id || item.pncp_id;
      if (!pncp_id) {
          console.error("No ID found for item", item);
          setIsUpdating(false);
          return;
      }
      const encodedId = encodeURIComponent(pncp_id);
      const endpoint = `/api/licitacoes/${encodedId}/${action}`;

      try {
          const res = await apiFetch(endpoint, { method: 'POST' });
          if (!res.ok) {
              const errorText = await res.text();
              throw new Error(`Erro ${res.status}: ${errorText}`);
          }
          
          setIsUpdating(false);
      } catch (e) {
          console.error("Triaging failed", e);
          setIsRemoved(false); // Rollback
          alert(`Falha ao processar ação: ${e instanceof Error ? e.message : String(e)}`);
          setIsUpdating(false);
      }
  };

  if (isRemoved) return null;

  const rawOrgao = item.comprador?.razaoSocial || item.orgao_nome || item.orgao;
  const orgao = rawOrgao || "Órgão não informado no PNCP";

  const muni = item.localizacao?.municipioNome || item.municipio;
  const uf = item.localizacao?.ufSigla || item.uf;

  const rawValor = 
    item.valores?.estimado ?? 
    (item.valor_estimado_centavos ? item.valor_estimado_centavos / 100 : item.valor_total_estimado);
    
  const valorDisplay =
    rawValor != null && rawValor > 0
      ? Number(rawValor).toLocaleString("pt-BR", {
          style: "currency",
          currency: "BRL",
        })
      : "Valor não informado";

  // Segment & Workflow logic
  const segmentId = item.segmento_principal || item.segment_id || "unclassified";
  const segmentLabel = item.segment_label || segmentId;
  const workflowStatus = item.workflow_status || "ACTIVE";

  // Mapping Workflow Status to Display
  const statusConfig: Record<string, { label: string, color: string, dot: string }> = {
      ACTIVE: { label: 'Ativa', color: 'bg-tint text-primary border-secondary/50', dot: 'bg-accent' },
      IGNORED: { label: 'Ignorada', color: 'bg-gray-50 text-gray-400 border-gray-100', dot: 'bg-gray-300' }
  };
  const status = statusConfig[workflowStatus] || statusConfig.ACTIVE;

  // Classification Reasoning (Extraction from segmentos_json)
  let evidence = null;
  try {
     evidence = typeof item.segmentos_json === 'string' ? JSON.parse(item.segmentos_json) : item.segmentos_json;
  } catch {
      // Ignore parse errors
  }

  // Items Enrichment Logic (Part G & Phase 9)
  const itens = item.itens || { count: 0, preview: [], status: 'NOT_FETCHED' };
  const itemCount = itens.count;
  const itensStatus = itens.status;
  const previewItems = itens.preview || [];

  const arquivos = item.arquivos || { count: 0, status: 'NOT_FETCHED', preview: [], has_more: false };
  const arquivosPreview = arquivos.preview || [];

  return (
    <div className={`bg-white rounded-xl shadow-sm border border-gray-100 hover:border-secondary/60 hover:shadow-md transition-all relative overflow-hidden group ${isUpdating ? 'opacity-50 pointer-events-none' : ''}`}>
      
      {/* Top Bar / Badges */}
      <div className="px-6 pt-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
            segmentId === 'almoxarifado_virtual' 
              ? 'bg-primary text-white border-primary' 
              : segmentId === 'kit_escolar'
              ? 'bg-secondary text-ink border-secondary'
              : segmentId === 'diversos'
              ? 'bg-tint text-ink border-secondary'
              : segmentId === 'unclassified'
              ? 'bg-gray-50 text-gray-500 border-gray-200'
              : 'bg-tint text-primary border-secondary/50'
          }`}>
            {segmentLabel}
          </span>
          <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide border ${status.color}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${status.dot}`}></span>
            {status.label}
          </span>
        </div>
        
        <div className="flex items-center gap-2">
            <button 
                onClick={() => navigator.clipboard.writeText(item.pncp_id || item.numeroControlePNCP || "")}
                className="text-gray-400 hover:text-primary transition-colors p-1"
                title="Copiar Código Edital"
            >
                <Share2 size={14} />
            </button>
            <input
                type="checkbox"
                className="w-4 h-4 rounded border-gray-300 text-primary focus:ring-primary cursor-pointer"
            />
        </div>
      </div>

      <div className="px-6 py-4">
        {/* Organ and Title */}
        <div className="mb-4">
          <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-1 truncate">
            {orgao}
          </p>
          <div className="flex justify-between items-start gap-4">
            <div className="flex-1">
                <div className="text-[11px] font-medium text-gray-500 mb-1 flex items-center gap-2">
                    Edital {item.numeroControlePNCP?.split("-")[0] || item.pncp_id?.split("-")[0]}
                    {item.situacao_nome && (
                        <span className="text-gray-300">• {item.situacao_nome}</span>
                    )}
                </div>
                <h2 className="text-gray-900 text-base font-bold leading-tight line-clamp-2">
                    {item.objetoCompra || item.objeto}
                </h2>
            </div>
          </div>
        </div>

        {/* Metadata Grid (4 Cols) */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 py-4 border-y border-gray-50">
          <div className="space-y-0.5">
            <p className="text-[9px] font-bold text-gray-400 uppercase tracking-tight">Valor Global</p>
            <p className={`text-xs font-bold ${valorDisplay === 'Valor não informado' ? 'text-gray-400 font-medium' : 'text-gray-900'}`}>{valorDisplay}</p>
          </div>
          {(uf || muni) && (
            <div className="space-y-0.5">
              <p className="text-[9px] font-bold text-gray-400 uppercase tracking-tight">Localização</p>
              <p className="text-xs font-medium text-gray-700 truncate">
                {muni}{muni && uf ? ', ' : ''}{uf}
              </p>
            </div>
          )}
          {item.modalidade_nome && (
            <div className="space-y-0.5">
              <p className="text-[9px] font-bold text-gray-400 uppercase tracking-tight">Modalidade</p>
              <p className="text-xs font-medium text-gray-700 truncate">{item.modalidade_nome}</p>
            </div>
          )}
          <div className="space-y-0.5">
            <p className="text-[9px] font-bold text-gray-400 uppercase tracking-tight">
                {workflowStatus === 'IGNORED' ? 'Status' : 'Prazo Final'}
            </p>
            <p className={`text-xs font-bold ${
                workflowStatus === 'IGNORED' ? 'text-gray-400' : 
                item.deadline_kind === 'NO_DEADLINE' ? 'text-gray-500' :
                item.deadline_kind === 'HAS_DEADLINE' ? 'text-accent' : 
                'text-amber-600'
            }`}>
              {(() => {
                if (workflowStatus === 'IGNORED') return 'Ignorada';

                // New Logic Phase 41
                const kind = item.deadline_kind;
                
                if (kind === 'NO_DEADLINE') {
                    return 'Sem prazo (contratação direta)';
                }
                
                if (kind === 'HAS_DEADLINE') {
                     const raw = item.deadline_at || item.deadline_raw;
                     if (!raw) return 'Data inválida';
                     
                     const match = String(raw).match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?/);
                     if (!match) return raw;
                     const [, y, m, d, hh, mm] = match;
                     const datePart = `${d}/${m}/${y}`;
                     return hh && mm ? `${datePart} ${hh}:${mm}` : datePart;
                }
                
                // UNKNOWN or Fallback
                return 'Prazo não informado';
              })()}
            </p>
          </div>
        </div>

        {/* Action Bar */}
        <div className="mt-5 flex items-center justify-between">
          <div className="flex items-center gap-2">
            {item.url_pncp_detalhe ? (
                <Link
                href={item.url_pncp_detalhe}
                target="_blank"
                rel="noopener noreferrer"
                className="bg-primary hover:bg-ink text-white text-[11px] font-bold px-4 py-2 rounded-lg transition-colors flex items-center gap-2 shadow-sm"
                >
                <Eye size={14} />
                Portal PNCP
                </Link>
            ) : (
                <button
                    disabled
                    className="bg-gray-100 text-gray-400 text-[11px] font-bold px-4 py-2 rounded-lg flex items-center gap-2 cursor-not-allowed"
                    title="Link PNCP indisponível"
                >
                    <Eye size={14} />
                    Portal PNCP
                </button>
            )}
            {workflowStatus === 'ACTIVE' ? (
                <button 
                    onClick={() => handleTriagingAction('ignore')}
                    className="p-2 border border-secondary/50 hover:bg-tint rounded-lg text-primary hover:text-ink transition-colors flex items-center gap-2"
                    title="Ignorar Licitação"
                >
                    <Ban size={16} />
                    <span className="text-[10px] font-bold uppercase">Ignorar</span>
                </button>
            ) : (
                <button 
                    onClick={() => handleTriagingAction('unignore')}
                    className="p-2 border border-secondary/50 hover:bg-tint rounded-lg text-primary hover:text-ink transition-colors flex items-center gap-2"
                    title="Restaurar Licitação"
                >
                    <RotateCcw size={16} />
                    <span className="text-[10px] font-bold uppercase">Restaurar</span>
                </button>
            )}
          </div>
          
          <button 
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-gray-400 hover:text-gray-600 flex items-center gap-1.5 transition-colors p-1"
          >
            <div className="flex flex-col items-end">
                <span className="text-[11px] font-bold uppercase tracking-wide">Itens: {itemCount}</span>
                {itensStatus !== 'COMPLETED' && itensStatus !== 'NOT_FETCHED' && (
                    <span className="text-[8px] font-medium text-amber-500 uppercase tracking-tight -mt-0.5">
                        {itensStatus === 'FETCHING' ? 'Buscando...' : 'Erro na busca'}
                    </span>
                )}
            </div>
            {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {/* Expanded Content (Transparency & Audit) */}
        {isExpanded && (
          <div className="mt-4 pt-4 border-t border-gray-50 bg-gray-50/50 -mx-6 px-6 pb-4 animate-in fade-in slide-in-from-top-1 duration-200">
            {/* Reasoning */}
            {evidence && evidence.matches && evidence.matches.length > 0 && (
                <div className="mb-4 bg-white p-3 rounded-lg border border-secondary/50 shadow-sm">
                    <div className="flex items-center gap-2 text-primary mb-2">
                        <Info size={14} />
                        <span className="text-[10px] font-bold uppercase tracking-wider">Por que foi classificada?</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                        {evidence.matches.map((m: string, i: number) => (
                            <span key={i} className="bg-tint text-primary px-2 py-0.5 rounded text-[9px] font-medium border border-secondary/50">
                                {m}
                            </span>
                        ))}
                    </div>
                </div>
            )}

            {/* Arquivos (Documents) Section */}
            <div className="mt-4 overflow-hidden bg-white rounded-lg border border-gray-100 mb-4">
              <div className="bg-gray-50 border-b border-gray-100 px-3 py-2 flex items-center justify-between">
                <span className="text-[9px] font-bold text-gray-400 uppercase">Documentos e Anexos</span>
                <span className="text-[10px] font-medium text-gray-500">{arquivos.count} arquivos</span>
              </div>
              <div className="divide-y divide-gray-50">
                {arquivos.status === 'COMPLETED' ? (
                  <>
                    {arquivosPreview.length > 0 && (
                        <div className="divide-y divide-gray-50">
                            {arquivosPreview.map((file: { titulo?: string, tipo_documento_nome?: string, url?: string }, idx: number) => (
                                <a 
                                    key={idx}
                                    href={file.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center justify-between px-4 py-2 hover:bg-gray-25 transition-colors group"
                                >
                                    <div className="flex-1 min-w-0 pr-4">
                                        <p className="text-[11px] font-medium text-gray-700 truncate group-hover:text-primary">
                                            {file.titulo || "Documento sem título"}
                                        </p>
                                        <p className="text-[9px] font-bold text-gray-400 uppercase tracking-widest mt-0.5">
                                            {file.tipo_documento_nome || "ANEXO"}
                                        </p>
                                    </div>
                                    <FileText size={14} className="text-gray-300 group-hover:text-primary shrink-0" />
                                </a>
                            ))}
                        </div>
                    )}
                    
                    {(arquivos.has_more || arquivosPreview.length === 0) && arquivos.count > 0 && (
                        <div className="p-2 border-t border-gray-50 bg-gray-50/50 flex justify-center">
                            <button 
                                onClick={() => setIsArquivosModalOpen(true)}
                                className="text-[10px] font-bold text-primary hover:underline uppercase tracking-widest py-1"
                            >
                                Ver todos os {arquivos.count} documentos
                            </button>
                        </div>
                    )}
                  </>
                ) : (
                  <div className="py-4 text-center text-[10px] text-gray-400 italic">
                    {(() => {
                        switch(arquivos.status) {
                            case 'FETCHING': return 'Buscando documentos...';
                            case 'FAILED_TEMP': return 'Falha temporária';
                            case 'FAILED': return 'Falha ao recuperar documentos.';
                            case 'NOT_FETCHED': return 'Documentos não coletados';
                            case 'NOT_AVAILABLE': return 'Sem documentos para este edital.';
                            default: return 'Documentos não disponíveis.';
                        }
                    })()}
                  </div>
                )}
              </div>
            </div>

            {/* Items Table */}
            <div className="overflow-hidden bg-white rounded-lg border border-gray-100">
              <table className="w-full text-left">
                <thead className="bg-gray-50 border-b border-gray-100">
                  <tr>
                    <th className="py-2 px-3 text-[9px] font-bold text-gray-400 uppercase">Descrição do Item</th>
                    <th className="py-2 px-3 text-[9px] font-bold text-gray-400 uppercase text-right">Qtd</th>
                    <th className="py-2 px-3 text-[9px] font-bold text-gray-400 uppercase text-right">Total</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {itensStatus === 'COMPLETED' && previewItems.length > 0 ? (
                    previewItems.map((it: { descricao?: string; quantidade?: number; valor_total?: number }, idx: number) => (
                      <tr key={idx} className="hover:bg-gray-25 transition-colors">
                        <td className="py-2 px-3 text-[11px] text-gray-600 leading-tight">
                            <span className="line-clamp-2">{it.descricao}</span>
                        </td>
                        <td className="py-2 px-3 text-[11px] text-gray-500 text-right font-medium">{it.quantidade}</td>
                        <td className="py-2 px-3 text-[11px] text-gray-900 text-right font-bold">
                            {it.valor_total != null ? 
                                it.valor_total.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }) : 
                                '—'}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                        <td colSpan={3} className="py-4 text-center text-[10px] text-gray-400 italic">
                            {(() => {
                                switch(itensStatus) {
                                    case 'FETCHING': return 'Coletando itens...';
                                    case 'FAILED_TEMP': return 'Falha temporária';
                                    case 'FAILED': return 'Falha ao recuperar itens.';
                                    case 'NOT_FETCHED': return 'Itens não coletados';
                                    case 'NOT_AVAILABLE': return 'Itens não informados para este edital.';
                                    default: return 'Dados dos itens não disponíveis.';
                                }
                            })()}
                        </td>
                    </tr>
                  )}
                </tbody>
              </table>

              {itensStatus === 'COMPLETED' && itens.has_more && (
                <div className="p-2 bg-gray-50/50 border-t border-gray-100 flex justify-center">
                    <button 
                        onClick={() => setIsModalOpen(true)}
                        className="text-[10px] font-bold text-primary hover:underline uppercase tracking-widest py-1"
                    >
                        Ver todos os {itemCount} itens
                    </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      <ItemsModal 
        isOpen={isModalOpen} 
        onClose={() => setIsModalOpen(false)} 
        pncpId={item.pncp_id || item.id || ""} 
        title={item.objetoCompra || item.objeto || ""}
      />

      <ArquivosModal
        isOpen={isArquivosModalOpen}
        onClose={() => setIsArquivosModalOpen(false)}
        pncpId={item.pncp_id || item.id || ""}
        title={item.objetoCompra || item.objeto || ""}
      />
    </div>
  );
}
