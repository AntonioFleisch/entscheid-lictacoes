# Guia de Instalação da Arquitetura de 3 Camadas

Este projeto segue uma arquitetura de 3 camadas projetada para maximizar a confiabilidade através da separação de responsabilidades.

## Visão Geral da Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│ Camada 1: DIRETRIZES (O que fazer)                          │
│ - SOPs em linguagem natural em directives/                  │
│ - Definem objetivos, entradas, ferramentas, saídas, erros   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Camada 2: ORQUESTRAÇÃO (Tomada de decisão)                  │
│ - Agente de IA toma decisões inteligentes de roteamento     │
│ - Lê diretrizes, chama scripts de execução, gerencia erros  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Camada 3: EXECUÇÃO (Fazendo o trabalho)                     │
│ - Scripts Python determinísticos em execution/               │
│ - Lidam com APIs, processamento de dados, banco de dados    │
└─────────────────────────────────────────────────────────────┘
```

## Estrutura de Diretórios

```
hello_api/
├── directives/          # SOPs e instruções (Camada 1)
│   ├── README.md
│   └── _template.md
├── execution/           # Scripts Python (Camada 3)
│   ├── README.md
│   └── _template.py
├── .tmp/               # Arquivos temporários (nunca commit)
├── .env                # Variáveis de ambiente e chaves de API
├── .env.example        # Template para variáveis de ambiente
├── .gitignore          # Regras do Git ignore
├── AGENTS.md           # Este guia de arquitetura
└── requirements.txt    # Dependências Python
```

## Instruções de Instalação

### 1. Instalar Dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar Ambiente

```bash
# Copie o arquivo de exemplo de ambiente
cp .env.example .env

# Edite o .env e adicione suas chaves de API e credenciais
```

### 3. Adicionar Google OAuth (se necessário)

Se estiver usando Google Sheets/Slides:

1. Coloque o arquivo `credentials.json` na raiz do projeto
2. Execute seu primeiro script - ele gerará o `token.json`

## Como Usar Este Sistema

### Para Agentes de IA (Camada de Orquestração)

1. **Leia a diretriz** para a tarefa que você precisa realizar
2. **Verifique execution/** para scripts existentes antes de criar novos
3. **Chame o script apropriado** com as entradas corretas
4. **Gerencie erros** e atualize as diretrizes com os aprendizados
5. **Auto-correção (Self-anneal)**: Quando algo quebrar, corrija o script, teste-o e atualize a diretriz

### Para Humanos (Criando Novos Fluxos)

1. **Crie uma diretriz** em `directives/` descrevendo o que fazer
2. **Crie script(s) de execução** em `execution/` para realizar o trabalho
3. **Teste o workflow** fazendo com que a IA siga a diretriz
4. **Itere e melhore** com base no que você aprender

## Princípios Operacionais

### 1. Verifique Ferramentas Primeiro

Antes de escrever um novo script, verifique `execution/` de acordo com sua diretriz. Crie novos scripts apenas se nenhum existir.

### 2. Auto-correção Quando Algo Quebrar

- Leia a mensagem de erro e o rastreamento da pilha (stack trace)
- Corrija o script e teste-o novamente
- Atualize a diretriz com o que você aprendeu
- O sistema está agora mais forte

### 3. Atualize as Diretrizes Conforme Aprende

As diretrizes são documentos vivos. Quando você descobrir restrições de API, abordagens melhores, erros comuns ou expectativas de tempo — atualize a diretriz.

## Organização de Arquivos

### Entregáveis vs Intermediários

- **Entregáveis**: Google Sheets, Google Slides ou outras saídas na nuvem que o usuário possa acessar
- **Intermediários**: Arquivos temporários necessários durante o processamento (vão para `.tmp/`)

**Princípio chave**: Arquivos locais são apenas para processamento. Os entregáveis vivem em serviços de nuvem onde o usuário pode acessá-los. Tudo em `.tmp/` pode ser deletado e regenerado.

## Por Que Isso Funciona

**O Problema**: LLMs são probabilísticos. 90% de precisão por etapa = 59% de sucesso em 5 etapas.

**A Solução**: Empurre a complexidade para o código determinístico. A IA se concentra na tomada de decisões, não no trabalho manual.

## Ciclo de Auto-correção (Self-Annealing)

Erros são oportunidades de aprendizado:

1. Corrija
2. Atualize a ferramenta
3. Teste a ferramenta
4. Atualize a diretriz para incluir o novo fluxo
5. O sistema está agora mais forte

## Próximos Passos

1. Revise os templates em `directives/_template.md` e `execution/_template.py`
2. Crie sua primeira diretriz para uma tarefa específica
3. Crie o script de execução correspondente
4. Teste o workflow
5. Itere e melhore

---

**Seja pragmático. Seja confiável. Auto-corrija (Self-anneal).**
