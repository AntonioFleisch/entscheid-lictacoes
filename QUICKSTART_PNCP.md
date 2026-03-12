# Guia de Início Rápido - Coleta PNCP

## Visão Geral

Este guia mostra como usar a automação de coleta de licitações do PNCP que substitui o workflow do n8n.

## Pré-requisitos

1. **Instalar dependências**:

```bash
pip install -r requirements.txt
```

2. **Configurar ambiente** (crie/edite o `.env`):

```bash
# Chave de API do Backend (necessária para ingestão)
API_KEY=sua_chave_de_api_aqui

# URL do Backend (opcional, padrão é http://localhost:8000)
BACKEND_URL=http://localhost:8000
```

## Exemplos de Uso

### Coleta Básica (janela de 1 semana, 4 páginas)

```bash
python execution/collect_pncp_licitacoes.py --start 20260115 --end 20260121
```

### Limite de Páginas Personalizado

```bash
python execution/collect_pncp_licitacoes.py --start 20260115 --end 20260121 --max-pages 10
```

### Tamanho de Página Personalizado

```bash
python execution/collect_pncp_licitacoes.py --start 20260115 --end 20260121 --page-size 100 --max-pages 5
```

### Somente Coleta (Pular Ingestão no Backend)

Útil para testes ou quando o backend está indisponível:

```bash
python execution/collect_pncp_licitacoes.py --start 20260115 --end 20260121 --skip-backend
```

## Arquivos de Saída

Todos os arquivos são salvos no diretório `.tmp/`:

- **Log**: `.tmp/pncp_collect_{RUN_ID}.log` - Log detalhado da execução
- **Dados Brutos**: `.tmp/pncp_raw_{RUN_ID}_page{N}.json` - Respostas brutas da API (por página)
- **Normalizado**: `.tmp/pncp_normalized_{RUN_ID}.json` - Dados normalizados finais

## Garantias da Arquitetura

Esta automação garante:

✅ **Contexto Imutável**: As datas da janela e limites nunca mudam durante a execução  
✅ **Paginação Determinística**: Loop explícito, sem inferência das respostas  
✅ **Fonte Única de Verdade**: Todos os parâmetros do contexto inicial  
✅ **Tratamento de Erros Robusto**: Repetições com recuo exponencial (backoff)  
✅ **Ingestão Idempotente**: Usando `Idempotency-Key: pncp:{run_id}`  
✅ **Auditabilidade Total**: Logs completos e dados brutos salvos

## Solução de Problemas

### "API_KEY not found in environment"

**Solução**: Crie o arquivo `.env` com `API_KEY=sua_chave`

### "Connection failed. Is the backend running?"

**Solução**:

- Inicie o backend: `uvicorn main:app --reload`
- Ou use `--skip-backend` para apenas coletar os dados

### "PNCP API returned status 500"

**Solução**: A API do PNCP está temporariamente fora do ar. O script tentará novamente 3 vezes com backoff.

### "Backend error 422: Validation error"

**Solução**: Verifique os dados normalizados em `.tmp/pncp_normalized_{RUN_ID}.json` em busca de itens inválidos

## Agendamento (Opcional)

### Agendador de Tarefas do Windows

Crie uma tarefa agendada para rodar diariamente:

```powershell
$action = New-ScheduledTaskAction -Execute "python" -Argument "execution/collect_pncp_licitacoes.py --start 20260120 --end 20260121" -WorkingDirectory "C:\Users\User\Desktop\hello_api"
$trigger = New-ScheduledTaskTrigger -Daily -At 2am
Register-ScheduledTask -TaskName "Coleta Diária PNCP" -Action $action -Trigger $trigger
```

### Cron do Linux

Adicione ao crontab:

```bash
0 2 * * * cd /caminho/para/hello_api && python execution/collect_pncp_licitacoes.py --start $(date -d "yesterday" +\%Y\%m\%d) --end $(date +\%Y\%m\%d)
```

## Repetição Manual a Partir de Dados Salvos

Se a ingestão no backend falhou, você pode tentar novamente usando os dados normalizados salvos:

```bash
python execution/ingest_pncp_batch.py .tmp/pncp_normalized_{RUN_ID}.json
```

## Monitoramento

Verifique os logs em `.tmp/` para:

- Total de páginas coletadas
- Total de itens coletados
- Status de ingestão no backend
- Quaisquer erros ou avisos

## Próximos Passos

1. Teste a coleta com uma janela pequena primeiro
2. Verifique os dados no backend
3. Ajuste `--max-pages` com base no volume esperado
4. Configure o agendamento se necessário
5. Monitore os logs regularmente
