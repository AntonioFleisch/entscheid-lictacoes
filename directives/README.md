# Camada 1: Diretrizes (SOPs)

Este diretório contém **Procedimentos Operacionais Padrão (SOPs)** escritos em linguagem natural. Estes arquivos definem a lógica de alto nível, objetivos e restrições para a automação.

## Papel na Arquitetura

As diretrizes fornecem o "know-how" para a camada de Orquestração de IA. Elas garantem que, mesmo que a IA seja probabilística, a lógica de negócio permaneça consistente.

> [!NOTE]
> Para um detalhamento arquitetônico completo, consulte [SETUP.md](../SETUP.md).

## Estrutura

Cada diretriz deve incluir:

- **Objetivo**: O que esta diretriz realiza
- **Entradas**: Quais informações/dados são necessários
- **Ferramentas/Scripts**: Quais scripts de execução usar
- **Saídas**: O que é produzido
- **Processo**: Instruções passo a passo
- **Casos de Borda**: Como lidar com situações incomuns
- **Tratamento de Erros**: Como se recuperar de falhas
- **Notas**: Limites de API, expectativas de tempo, aprendizados

## Criando Novas Diretrizes

1. Copie `_template.md` para um novo arquivo com um nome descritivo
2. Preencha todas as seções baseando-se no seu caso de uso
3. Teste a diretriz fazendo com que a IA a siga
4. Atualize a diretriz conforme você aprende mais

## Documentos Vivos

Diretrizes são **documentos vivos**. Quando você descobrir:

- Restrições de API ou limites de taxa
- Melhores abordagens
- Erros comuns
- Expectativas de tempo

**Atualize a diretriz** para que o sistema fique mais inteligente ao longo do tempo.

## Exemplos

Veja `_template.md` para a estrutura padrão.
