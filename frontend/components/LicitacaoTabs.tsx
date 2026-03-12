"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */

import { useState } from "react";
import { Package, FileText, History, Info, ExternalLink, Download } from "lucide-react";
import Link from "next/link";

interface LicitacaoTabsProps {
  item: any; // Fallback to any for complex nested PNCP payload, but let's keep it consistent
}

export function LicitacaoTabs({ item }: LicitacaoTabsProps) {
  const [activeTab, setActiveTab] = useState("overview");

  const tabs = [
    { id: "overview", label: "Visão Geral", icon: Info },
    { id: "items", label: "Itens", icon: Package },
    { id: "docs", label: "Documentos", icon: FileText },
    { id: "history", label: "Histórico", icon: History },
  ];

  return (
    <div className="space-y-6">
      {/* Tabs Header */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-8" aria-label="Tabs">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  group inline-flex items-center py-4 px-1 border-b-2 font-medium text-sm
                  ${isActive 
                    ? "border-primary text-primary"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"}
                `}
              >
                <Icon size={16} className={`mr-2 ${isActive ? "text-primary" : "text-gray-400 group-hover:text-gray-500"}`} />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tabs Content */}
      <div className="min-h-[400px]">
        
        {/* VIEW: OVERVIEW */}
        {activeTab === "overview" && (
           <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
               <div className="space-y-6">
                   <div className="bg-white rounded-lg p-6 border border-gray-100 shadow-sm">
                       <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wider mb-4">Detalhes da Compra</h3>
                       <dl className="grid grid-cols-1 gap-y-4">
                           <div>
                               <dt className="text-sm font-medium text-gray-500">Unidade Compradora</dt>
                               <dd className="mt-1 text-sm text-gray-900 font-medium">{item.unidade_compradora || item.orgao_nome || "-"}</dd>
                           </div>
                           <div>
                               <dt className="text-sm font-medium text-gray-500">Amparo Legal</dt>
                               <dd className="mt-1 text-sm text-gray-900">{item.amparo_legal || item.payload_publicacao_json?.amparoLegal?.nome || "-"}</dd>
                           </div>
                           <div>
                               <dt className="text-sm font-medium text-gray-500">Modo de Disputa</dt>
                               <dd className="mt-1 text-sm text-gray-900">{item.modo_disputa || item.payload_publicacao_json?.modoDisputaNome || "-"}</dd>
                           </div>
                           <div>
                               <dt className="text-sm font-medium text-gray-500">Critério de Julgamento</dt>
                               <dd className="mt-1 text-sm text-gray-900">{item.payload_publicacao_json?.criterioJulgamentoNome || "-"}</dd>
                           </div>
                       </dl>
                   </div>
               </div>

               <div className="space-y-6">
                   <div className="bg-tint rounded-lg p-6 border border-secondary/50 flex flex-col items-center justify-center text-center">
                       <h3 className="text-base font-semibold text-primary mb-2">Acesso ao PNCP</h3>
                       <p className="text-sm text-gray-600 mb-4 max-w-xs">
                           Visualize a publicação original diretamente no Portal Nacional de Contratações Públicas.
                       </p>
                       {item.url_pncp_detalhe ? (
                           <Link 
                                href={item.url_pncp_detalhe}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-primary hover:bg-ink focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary transition-colors"
                           >
                               Abrir no PNCP <ExternalLink size={16} className="ml-2" />
                           </Link>
                       ) : (
                           <button
                               disabled
                               className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-gray-400 bg-gray-100 cursor-not-allowed"
                               title="Link PNCP indisponível"
                           >
                               Abrir no PNCP <ExternalLink size={16} className="ml-2" />
                           </button>
                       )}
                   </div>
               </div>
           </div>
        )}

        {/* VIEW: ITEMS */}
        {activeTab === "items" && (
            <div className="bg-white rounded-lg border border-gray-100 overflow-hidden">
                {!item.itens || item.itens.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        Nenhum item carregado.
                    </div>
                ) : (
                    <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-gray-50">
                            <tr>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">#</th>
                                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Descrição</th>
                                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Qtd / Unid</th>
                                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Valor Unit.</th>
                                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Total</th>
                            </tr>
                        </thead>
                        <tbody className="bg-white divide-y divide-gray-200">
                            {item.itens.map((it: any) => (
                                <tr key={it.item_key || it.numero} className="hover:bg-gray-50">
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{it.numero}</td>
                                    <td className="px-6 py-4 text-sm text-gray-900 max-w-md truncate" title={it.descricao}>{it.descricao}</td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                                        {Number(it.quantidade).toLocaleString('pt-BR')} <span className="text-xs text-gray-400 ml-1">{it.unidade}</span>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 text-right">
                                        {Number(it.valor_unitario).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 text-right">
                                        {Number(it.valor_total).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        )}

        {/* VIEW: DOCUMENTS */}
        {activeTab === "docs" && (
             <div className="bg-white rounded-lg border border-gray-100">
                 {!item.documentos || item.documentos.length === 0 ? (
                    <div className="p-8 text-center text-gray-500">
                        Nenhum documento disponível.
                    </div>
                 ) : (
                     <ul className="divide-y divide-gray-100">
                         {item.documentos.map((doc: any, idx: number) => (
                             <li key={idx} className="p-4 hover:bg-gray-50 flex items-center justify-between">
                                 <div className="flex items-center">
                                     <div className="flex-shrink-0 h-10 w-10 rounded-lg bg-tint flex items-center justify-center text-primary">
                                         <FileText size={20} />
                                     </div>
                                     <div className="ml-4">
                                         <p className="text-sm font-medium text-gray-900">{doc.doc_nome || "Documento Sem Título"}</p>
                                         <p className="text-xs text-gray-500">{doc.doc_tipo || "PDF"}</p>
                                     </div>
                                 </div>
                                 <a 
                                    href={doc.doc_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="ml-4 inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-xs font-medium rounded text-gray-700 bg-white hover:bg-gray-50 focus:outline-none"
                                 >
                                     <Download size={14} className="mr-1.5" /> Baixar
                                 </a>
                             </li>
                         ))}
                     </ul>
                 )}
             </div>
        )}

        {/* VIEW: HISTORY */}
        {activeTab === "history" && (
             <div className="bg-white rounded-lg border border-gray-100 p-6">
                 {/* Placeholder for history timeline */}
                 <div className="text-center py-8">
                     <History size={48} className="mx-auto text-gray-200 mb-3" />
                     <p className="text-gray-500">Não há histórico de alterações registrado para esta contratação.</p>
                 </div>
             </div>
        )}
      </div>
    </div>
  );
}
