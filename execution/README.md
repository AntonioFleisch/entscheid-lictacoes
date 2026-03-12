# Camada 3: Scripts de Execução

Este diretório contém scripts Python determinísticos projetados para realizar tarefas específicas de forma confiável e reproduzível.

## Papel na Arquitetura

Em nossa **Arquitetura de 3 Camadas**, estes scripts são os "executores". Eles lidam com o trabalho pesado, como chamadas de API, operações de banco de dados e processamento de dados.

> [!NOTE]
> Para uma visão geral de como esses scripts se encaixam no sistema, consulte o [SETUP.md](../SETUP.md) principal.

## Uso

## Estrutura do Script

Todo script deve ter:

1. **Entradas claras**: Argumentos de linha de comando, variáveis de ambiente ou arquivos de configuração
2. **Tratamento de erros**: Falha graciosa com mensagens informativas
3. **Logging**: Registro de etapas importantes para depuração
4. **Saídas claras**: Retorno de dados em um formato consistente
5. **Documentação**: Comentários explicando o "o quê" e o "porquê"

Veja `_template.py` para a estrutura padrão.

## Variáveis de Ambiente

Os scripts devem ler dados sensíveis (chaves de API, tokens) a partir de variáveis de ambiente definidas no arquivo `.env`.

## Dependências

Adicione quaisquer pacotes necessários ao arquivo `requirements.txt` na raiz do projeto.

## Testes

Os scripts devem ser testáveis. Considere:

- Testes unitários para funções individuais
- Testes de integração para workflows completos
- Mock de APIs externas durante os testes

## Melhores Práticas

- **Uma responsabilidade**: Cada script deve fazer bem uma única coisa
- **Idempotente**: Executar múltiplas vezes deve ser seguro
- **Documentado**: Docstrings e comentários claros
- **Com Logs**: Use o módulo `logging`, não comandos `print`
- **Robusto**: Lide com casos de borda e erros de forma graciosa
