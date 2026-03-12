# Collect PNCP Licitações

## Goal

Execute a coleta determinística de licitações do PNCP com paginação controlada, substituindo o workflow n8n maduro sem perda de robustez.

## Inputs

- **Window Start Date**: Data inicial da janela temporal (formato: YYYYMMDD)
- **Window End Date**: Data final da janela temporal (formato: YYYYMMDD)
- **Page Size**: Tamanho da página (default: 50)
- **Max Pages**: Número máximo de páginas a coletar (default: 4)
- **API Key**: Chave de autenticação para o backend próprio
- **Backend URL**: URL base do backend (default: http://localhost:8000)

## Tools/Scripts

- **Script**: `execution/collect_pncp_licitacoes.py`
- **Dependencies**: `requests`, `python-dotenv`
- **External APIs**:
  - PNCP API: `https://pncp.gov.br/api/consulta/v1/contratacoes/proposta`
  - Backend próprio: `POST /ingest/pncp/batch`

## Outputs

- **Success Response**: Confirmação de ingestão com contadores (created/updated/failed)
- **Run Log**: Log detalhado em `.tmp/pncp_collect_RUN_ID.log`
- **Raw Data**: Dados brutos salvos em `.tmp/pncp_raw_RUN_ID.json` (para auditoria)
- **Normalized Data**: Dados normalizados em `.tmp/pncp_normalized_RUN_ID.json`

## Process

### 1️⃣ Criar Fonte Única de Verdade (make_window)

- Gerar `run_id` único (UUID4)
- Criar objeto de contexto imutável com:
  - `run_id`
  - `PAGE_SIZE` (fixo)
  - `MAX_PAGES` (fixo)
  - `window_start` (fixo)
  - `window_end` (fixo)
  - `pagina` (inicial = 1)
- **CRÍTICO**: Este objeto nunca é sobrescrito, apenas `pagina` é incrementada

### 2️⃣ Loop de Paginação Controlado

- Implementar loop explícito: `while pagina <= MAX_PAGES`
- Para cada iteração:
  - Ler parâmetros do contexto (nunca inferir)
  - Chamar PNCP API
  - Processar resposta
  - Incrementar `pagina`
- **PROIBIDO**: Inferir página pela resposta, recalcular datas, depender de estado implícito

### 3️⃣ Chamada ao PNCP (HTTP GET)

- Endpoint: `/contratacoes/proposta`
- Query params (sempre do contexto):
  - `dataInicial`: `window_start`
  - `dataFinal`: `window_end`
  - `pagina`: `pagina`
  - `tamanhoPagina`: `PAGE_SIZE`
- Timeout: 30 segundos
- Tratamento de erro HTTP ≠ 200

### 4️⃣ Normalização da Resposta

- Extrair `data[]` de cada página
- Normalizar campos obrigatórios:
  - `numeroControlePNCP`
  - `objetoCompra`
  - `comprador` (cnpj, razaoSocial, esferaId, poderId)
  - `localizacao` (ufSigla, municipioNome, codigoIbge)
  - `modalidade` (id, nome)
  - `modoDisputa` (id, nome)
  - `amparoLegal` (codigo, nome)
  - `valores` (estimado, homologado, srp)
  - `datas` (publicacaoPncp, aberturaProposta, encerramentoProposta, atualizacaoGlobal)
  - `situacao` (id, nome)
  - `links` (sistemaOrigem, processoEletronico)
- **Regra**: Campos ausentes → `null`, nunca lançar erro

### 5️⃣ Agregação Pós-Loop

- Após término do loop, agregar todas as páginas em um único array
- **PROIBIDO**: Deduplicação implícita, reordenação automática
- Formato final:
  ```json
  {
    "run_id": "...",
    "window": {"start": "YYYYMMDD", "end": "YYYYMMDD"},
    "items": [...]
  }
  ```

### 6️⃣ Envio para Backend Próprio

- Um único `POST /ingest/pncp/batch`
- Headers:
  - `X-API-Key`: API key do backend
  - `Idempotency-Key`: `pncp:{run_id}`
- Body: `{"window": {...}, "items": [...]}`
- Se erro: logar, encerrar, não repetir

## Edge Cases

- **PNCP API timeout**: Retry com exponential backoff (max 3 tentativas)
- **PNCP retorna 0 items**: Continuar loop normalmente, agregar array vazio
- **Página parcial**: Aceitar qualquer quantidade de items, não inferir fim
- **Backend indisponível**: Salvar dados normalizados em `.tmp/` para retry manual
- **Campos faltantes na resposta**: Normalizar como `null`, nunca falhar
- **MAX_PAGES atingido**: Encerrar loop normalmente, não buscar mais páginas

## Error Handling

- **PNCP API 4xx/5xx**: Logar erro, retry com backoff, se falhar após 3 tentativas, encerrar
- **Backend 401**: Verificar API_KEY no `.env`
- **Backend 422**: Logar detalhes de validação, encerrar (dados inválidos)
- **Backend 500**: Logar erro, encerrar (não retry automático)
- **Network error**: Retry com backoff, salvar dados em `.tmp/` se falhar

## Notes

- **Idempotência**: Usar `Idempotency-Key: pncp:{run_id}` garante que re-execuções não duplicam dados
- **Auditabilidade**: Cada execução tem `run_id` único, logs e dados salvos em `.tmp/`
- **Timing**: PNCP API tipicamente responde em 1-3 segundos por página
- **Rate Limiting**: PNCP não documenta limites, mas usar delay de 500ms entre páginas é seguro
- **Janela Temporal**: Recomendado usar janelas de 1-7 dias para evitar timeouts
- **MAX_PAGES**: Ajustar conforme necessidade (4 páginas = 200 items com PAGE_SIZE=50)

## Anti-Padrões Proibidos

❌ "Descobrir" página pela resposta  
❌ Recalcular datas a cada iteração  
❌ Misturar resposta com estado de loop  
❌ Fazer POST por página  
❌ Inferir limites sem MAX_PAGES  
❌ Perder dataFinal em iterações

## Scheduling (Automation)

- **Script**: `execution/scheduler.py`
- **Interval**: 1 hour (3600s)
- **Startup**: Run `START_AUTOMATION.ps1` to launch the full suite (Backend + Frontend + Scheduler).

## Learnings

- 2026-01-21: Diretiva criada baseada em workflow n8n maduro e estável
- 2026-01-21: Princípios de fonte única de verdade e loop explícito são inegociáveis
- 2026-01-21: Automated scheduler implemented for 1-hour interval collection using a rolling window.
