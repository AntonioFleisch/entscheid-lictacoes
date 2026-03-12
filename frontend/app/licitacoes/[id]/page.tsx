import { getItem, searchItems } from "@/lib/api";
import Link from "next/link";
import { ArrowLeft, Building2, MapPin, Clock } from "lucide-react";
import { notFound } from "next/navigation";
import { LicitacaoTabs } from "@/components/LicitacaoTabs";

export default async function LicitacaoDetailPage({ params }: { params: { id: string } }) {
  const { id } = params;
  
  let item;
  const decodedId = decodeURIComponent(id);
  
  try {
      item = await getItem(decodedId);
  } catch (e) {
      // Fallback: Try searching, assuming id might be numeroControlePNCP
      try {
        const searchRes = await searchItems({ q: decodedId, page_size: 1 });
        if (searchRes?.items?.length > 0) {
            item = searchRes.items[0];
            // If we found it via search, we might want to fetch full details again using its canonical ID
            // But for now let's just use what we have, or try to fetch details if we have a better ID
            if (item.canonical_id) {
                 try {
                     item = await getItem(item.canonical_id);
                 } catch (inner) {
                     // ignore
                 }
            }
        } else {
            notFound();
        }
      } catch (err) {
          notFound();
      }
  }

  // Ensure item exists
  if (!item) notFound();

  // Defensive coding for fields
  const orgao = item.orgao || item.comprador?.razaoSocial || "Órgão não informado";
  const objeto = item.objetoCompra || item.objeto || "Objeto não informado";
  const modalidade = item.modalidade?.nome || item.modalidade || "N/A";
  const valor = item.valor_total_estimado != null ? item.valor_total_estimado : item.valores?.estimado;
  
  return (
    <div className="max-w-5xl mx-auto space-y-6 p-6">
      <Link href="/licitacoes" className="inline-flex items-center text-sm text-gray-500 hover:text-blue-600 mb-4 transition-colors">
        <ArrowLeft size={16} className="mr-1" /> Voltar para lista
      </Link>

      {/* Header Summary */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-8">
        <div className="flex flex-col md:flex-row justify-between items-start gap-4">
            <div className="space-y-4 flex-1">
                <div>
                    <span className="inline-block px-3 py-1 bg-blue-50 text-blue-700 rounded-full text-xs font-semibold uppercase tracking-wide mb-3">
                        {modalidade}
                    </span>
                    <h1 className="text-2xl font-bold text-gray-900 leading-tight">
                        {objeto}
                    </h1>
                </div>
                
                <div className="flex flex-wrap items-center gap-4 text-gray-500 text-sm">
                    <span className="font-mono bg-gray-100 px-2 py-0.5 rounded text-gray-600">
                        {item.pncp_id || item.numeroControlePNCP}
                    </span>
                    <div className="flex items-center gap-1">
                        <Building2 size={14} /> {orgao}
                    </div>
                    {item.uf && (
                        <div className="flex items-center gap-1">
                            <MapPin size={14} /> {item.municipio ? `${item.municipio}/` : ''}{item.uf}
                        </div>
                    )}
                </div>
            </div>

            {valor != null && (
                 <div className="text-left md:text-right whitespace-nowrap bg-gray-50 p-4 rounded-lg md:bg-transparent md:p-0">
                    <p className="text-sm text-gray-500 mb-1">Valor Estimado</p>
                    <p className="text-2xl font-bold text-blue-600">
                        {Number(valor).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
                    </p>
                </div>
            )}
        </div>
      </div>

      {/* Main Content Tabs */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-6 min-h-[500px]">
          <LicitacaoTabs item={item} />
      </div>
    </div>
  );
}
