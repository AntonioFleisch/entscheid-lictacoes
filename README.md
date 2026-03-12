# Plataforma de Descoberta e Automação PNCP

Um pipeline de alta performance para coleta, enriquecimento e exploração de licitações públicas do **Portal Nacional de Contratações Públicas (PNCP)**. Construído com uma arquitetura robusta de 3 camadas para automação confiável.

---

## 🚀 Início Rápido (Docker)

A maneira mais rápida de colocar a plataforma em funcionamento é usando o Docker Compose.

1.  **Clonar e Configurar**:
    ```bash
    cp .env.example .env
    # Edite o .env e adicione seu DATABASE_URL e chaves de API
    ```

2.  **Iniciar Serviços**:
    ```bash
    docker-compose up -d --build
    ```

3.  **Acessar o Painel**:
    - **Frontend**: [http://localhost:3000](http://localhost:3000)
    - **Backend API**: [http://localhost:8000](http://localhost:8000)
    - **Documentação da API**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🏗️ Arquitetura

Este projeto opera em uma **Arquitetura Inteligente de 3 Camadas** para unir a orquestração de IA com a execução determinística:

1.  **Diretrizes (Lógica)**: SOPs (Procedimentos Operacionais Padrão) em linguagem natural em `directives/` que guiam o fluxo de automação.
2.  **Orquestração (Decisão)**: A camada de IA que lê diretrizes, seleciona ferramentas e gerencia erros.
3.  **Execução (Ação)**: Scripts Python determinísticos em `execution/` que lidam com APIs, operações de banco de dados e processamento de dados.

> [!TIP]
> Leia mais sobre a arquitetura em [SETUP.md](SETUP.md) e [AGENTS.md](AGENTS.md).

---

## 🛠️ Principais Recursos

- **Ingestão PNCP**: Coleta automatizada de licitações via `execution/collect_pncp_licitacoes.py`.
- **Enriquecimento Inteligente**: Pipeline de múltiplos estágios para buscar itens, arquivos e calcular pontuações CAPAG.
- **Busca Avançada**: Mecanismo de busca multitenant com filtragem por segmento (Kit Escolar, Almoxarifado Virtual, Diversos).
- **Stack Moderna**:
  - **Backend**: FastAPI, PostgreSQL (psycopg3), Pydantic v2.
  - **Frontend**: Next.js 15, TailwindCSS, SWR.
  - **Operações**: Docker, scripts PowerShell/Bash para gerenciamento de automação.

---

## 📖 Guias Detalhados

- **[Instalação e Arquitetura](SETUP.md)**: Detalhes de configuração e princípios de arquitetura.
- **[Guia de Automação PNCP](QUICKSTART_PNCP.md)**: Como executar e agendar as ferramentas de coleta.
- **[Desenvolvimento Frontend](frontend/README.md)**: Estrutura de componentes de UI e temas.

---

## 🧪 Desenvolvimento e Testes

### Execução Manual (Python)
Se executado fora do Docker:
```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

### Executar Testes
```bash
pytest
```

---

## 📝 Licença
Proprietário / Desenvolvimento.

---

**Confiabilidade. Clareza. Automação.**
