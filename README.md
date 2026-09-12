# Analisador de Pedidos da Lanchonete

Projeto da disciplina de **Compiladores** (8º período — UNA). Analisa pedidos de
uma lanchonete em linguagem natural, identificando ação, produto e quantidade por
análise léxica e validando o pedido por análise semântica — ver
[enunciado.md](enunciado.md).

**Repositório:** https://github.com/Kauhan33/projeto-python-compiladores

## Como funciona

1. **Análise léxica** ([lexer.py](lexer.py)): quebra a frase digitada em `Token`s
   classificados em `ACAO`, `PRODUTO`, `QUANTIDADE`, `CONECTIVO` (artigos, preposições)
   ou `DESCONHECIDO` (palavra fora do cardápio/vocabulário).
2. **Análise semântica** ([semantic.py](semantic.py)): valida o pedido (produto existe
   no cardápio, quantidade é válida, item realmente está no carrinho antes de remover)
   e mantém o estado do pedido atual (`Pedido`), calculando subtotal e total.
3. **Execução** ([main.py](main.py)): laço interativo que lê pedidos do cliente e mostra
   a resposta do sistema; também tem um modo `--demo` com comandos de exemplo.

## Vocabulário reconhecido

- **Ações:** pedir/adicionar/quero, remover/tirar, cancelar, finalizar, mostrar/ver,
  ajuda
- **Cardápio:** hambúrguer, refrigerante, batata frita, suco, pizza, sorvete,
  cachorro-quente, água, milkshake, salada
- **Quantidade:** número (`2`) ou por extenso (`dois`); padrão é `1` quando omitida

## Como executar

```bash
python main.py            # modo interativo
python main.py --demo     # roda comandos de exemplo, incluindo erros propositais
```

Exemplo de sessão:

```
Cliente: Pedir Hamburguer
Sistema: Adicionado 1x Hamburguer ao pedido. Subtotal do item: R$ 18.00.

Cliente: Remover Refrigerante
Sistema: Você não tem Refrigerante no pedido para remover.

Cliente: Finalizar pedido
Sistema: Pedido finalizado -> 1x Hamburguer (R$ 18.00) | Total: R$ 18.00.
```

## Testes

```bash
python -m unittest test_lanchonete.py -v
```
