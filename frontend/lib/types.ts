/* eslint-disable @typescript-eslint/no-explicit-any */
export interface PNCPItem {
  id: string; // idempotency_key
  numeroControlePNCP?: string;
  objetoCompra: string;
  idempotency_key: string;
  created_at: string;
  updated_at: string;
  valores: {
    estimado?: number;
    srp?: boolean;
    [key: string]: any;
  };
  datas: {
    encerramentoProposta?: string;
    atualizacaoGlobal?: string;
    [key: string]: any;
  };
  localizacao: {
    uf?: string;
    municipio?: string;
    [key: string]: any;
  };
  comprador: {
    razaoSocial?: string;
    [key: string]: any;
  };
  situacao?: {
    nome?: string;
    [key: string]: any;
  };
  modalidade?: {
    nome?: string;
    [key: string]: any;
  };
  [key: string]: any;
}

export interface PaginatedResponse {
  page: number;
  page_size: number;
  total: number;
  items: PNCPItem[];
}


