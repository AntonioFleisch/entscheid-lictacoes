# 📚 Índice de Documentação

Guia de navegação rápida para o projeto de arquitetura de 3 camadas.

## 🚀 Como Começar

| Documento                                            | Descrição                                         |
| ---------------------------------------------------- | ------------------------------------------------- |
| **[Início com Um Comando]**                          | Execute `npm start` no diretório raiz             |
| [CONFIGURATION_SUMMARY.md](CONFIGURATION_SUMMARY.md) | **COMECE AQUI** - Visão geral do que foi configurado |
| [SETUP.md](SETUP.md)                                 | Guia abrangente de arquitetura                    |
| [QUICKSTART_PNCP.md](QUICKSTART_PNCP.md)             | Início rápido para coleta do PNCP                 |

## 📖 Documentação Principal

| Documento               | Propósito                                |
| ----------------------- | ---------------------------------------- |
| [AGENTS.md](AGENTS.md) | Princípios fundamentais da arquitetura de 3 camadas |
| [README.md](README.md) | README traduzido do projeto              |

## 📁 Documentação das Camadas

### Camada 1: Diretrizes (O que fazer)

| Documento                                                                       | Propósito                             |
| ------------------------------------------------------------------------------ | ------------------------------------- |
| [directives/README.md](directives/README.md)                                   | Como criar e usar diretrizes          |
| [directives/\_template.md](directives/_template.md)                            | Template para novas diretrizes        |
| [directives/collect_pncp_licitacoes.md](directives/collect_pncp_licitacoes.md) | SOP de coleta do PNCP                 |
| [directives/ingest_pncp_data.md](directives/ingest_pncp_data.md)               | SOP de ingestão do PNCP               |

### Camada 3: Execução (Fazendo o trabalho)

| Documento                                                                     | Propósito                             |
| ---------------------------------------------------------------------------- | ------------------------------------- |
| [execution/README.md](execution/README.md)                                   | Como criar scripts de execução        |
| [execution/\_template.py](execution/_template.py)                            | Template para novos scripts           |
| [execution/collect_pncp_licitacoes.py](execution/collect_pncp_licitacoes.py) | Coletor PNCP (substituto do n8n)      |
| [execution/ingest_pncp_batch.py](execution/ingest_pncp_batch.py)             | Ingestão em lote do PNCP              |
| [execution/validate_config.py](execution/validate_config.py)                 | Validador de configuração             |

## 🔧 Arquivos de Configuração

| Arquivo                              | Propósito                                                  |
| ------------------------------------ | ---------------------------------------------------------- |
| [.env.example](.env.example)         | Template de variáveis de ambiente                          |
| [.env](.env)                         | Sua configuração de ambiente (crie a partir do .env.example) |
| [.gitignore](.gitignore)             | Regras do Git ignore                                       |
| [requirements.txt](requirements.txt) | Dependências Python                                        |

## 🎯 Tarefas Comuns

### Validar Configuração

```bash
python execution/validate_config.py
```

### Coletar Dados do PNCP

```bash
python execution/collect_pncp_licitacoes.py --start 20260115 --end 20260121
```

### Ingerir Dados em Lote

```bash
python execution/ingest_pncp_batch.py dados.json
```

### Instalar Dependências

```bash
pip install -r requirements.txt
```

## 📂 Estrutura de Diretórios

```
hello_api/
├── 📁 directives/          # Camada 1: SOPs e instruções
├── 📁 execution/           # Camada 3: Scripts determinísticos
├── 📁 .tmp/               # Arquivos temporários (nunca commit)
├── 📁 frontend/           # Aplicação frontend
├── 📁 tests/              # Arquivos de teste
├── 📄 AGENTS.md           # Princípios de arquitetura
├── 📄 SETUP.md            # Guia de instalação
├── 📄 QUICKSTART_PNCP.md  # Início rápido PNCP
├── 📄 CONFIGURATION_SUMMARY.md  # Resumo de configuração
├── 📄 INDEX.md            # Este arquivo
├── 📄 .env.example        # Template de ambiente
├── 📄 .gitignore          # Git ignore
└── 📄 requirements.txt    # Dependências
```

## 🎓 Trilha de Aprendizado

1. **Entenda a Arquitetura**: Leia [AGENTS.md](AGENTS.md)
2. **Veja o que está configurado**: Leia [CONFIGURATION_SUMMARY.md](CONFIGURATION_SUMMARY.md)
3. **Aprenda a Usar**: Leia [SETUP.md](SETUP.md)
4. **Experimente a Coleta PNCP**: Siga o [QUICKSTART_PNCP.md](QUICKSTART_PNCP.md)
5. **Crie os seus próprios**:
   - Leia [directives/README.md](directives/README.md)
   - Leia [execution/README.md](execution/README.md)
   - Use os templates para criar novos workflows

## 🔍 Referência Rápida

### Camadas da Arquitetura

1. **Diretrizes** (Camada 1): SOPs em linguagem natural definindo o que fazer
2. **Orquestração** (Camada 2): Agente de IA tomando decisões inteligentes
3. **Execução** (Camada 3): Scripts Python determinísticos fazendo o trabalho

### Princípios Operacionais

- ✅ Verifique se há ferramentas antes de criar novas
- ✅ "Self-anneal" quando as coisas quebrarem (corrigir → testar → atualizar diretriz)
- ✅ Atualize as diretrizes conforme aprende
- ✅ Mantenha entregáveis na nuvem, intermediários em `.tmp/`

### Anti-padrões

- ❌ Não deixe a IA fazer trabalho determinístico manualmente
- ❌ Não crie scripts sem diretrizes
- ❌ Não commite arquivos em `.tmp/`
- ❌ Não coloque credenciais no código (use `.env`)

## 💡 Dicas

- **Logs**: Verifique `.tmp/` para logs de execução
- **Depuração**: Use `--skip-backend` para testar apenas a coleta
- **Validação**: Execute `validate_config.py` para checar a instalação
- **Templates**: Comece sempre a partir de `_template.md` ou `_template.py`

---

**Precisa de ajuda?** Verifique os arquivos README em cada diretório para orientação detalhada.
