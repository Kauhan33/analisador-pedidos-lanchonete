# Analisador de Pedidos da Lanchonete

Projeto da disciplina de **Compiladores** (8º período — UNA). Analisa pedidos de
uma lanchonete em linguagem natural, identificando ação, produto e quantidade por
análise léxica e validando o pedido por análise semântica — ver
[enunciado.md](enunciado.md).

**Repositório:** https://github.com/Kauhan33/analisador-pedidos-lanchonete

![Interface gráfica](docs/interface.png)

## Como funciona

1. **Análise léxica** ([lexer.py](lexer.py)): quebra a frase em `Token`s classificados
   em `ACAO`, `PRODUTO`, `QUANTIDADE`, `CONECTIVO` (artigos, preposições) ou
   `DESCONHECIDO`. Reconhece produtos escritos com mais de uma palavra ("batata frita",
   "cachorro quente"), apelidos ("refri", "hot dog", "fritas") e **plurais por regra**
   ("hamburguers", "batatas fritas") — desfaz o sufixo em vez de listar cada forma.
2. **Análise semântica** ([semantic.py](semantic.py)): descobre a qual produto cada
   quantidade se refere, valida o pedido diante do **estado atual** do carrinho e
   calcula os totais.
3. **Cardápio** ([cardapio.py](cardapio.py)): fonte única de produtos, preços e
   apelidos — usada pelo lexer, pela semântica e pela interface.
4. **Execução** ([main.py](main.py)): laço interativo, com um modo `--demo`.
5. **Voz** ([voice.py](voice.py)) *(opcional)*: transcreve o pedido falado e responde em
   áudio, em pt-BR. Só frases com verbo de pedido contam como comando.
6. **Interface gráfica** ([gui.py](gui.py) + [visual.py](visual.py)) *(opcional)*:
   cardápio, microfone animado e pedido atual na mesma tela.

## O que a análise semântica resolve

A fase léxica reconhece as palavras; é a semântica que entende o **significado** da
sequência. Cinco exemplos:

**1. A qual produto cada quantidade pertence**

```
Cliente: pedir 2 hamburguer e 1 refrigerante
Sistema: Adicionado 2x Hambúrguer e 1x Refrigerante ao pedido (R$ 42.00). Total: R$ 42.00.
```

A ordem dos tokens é o que diz quem pertence a quem. Em "2 hambúrguer e refrigerante",
o 2 vale só para o hambúrguer — o refrigerante fica com 1.

**2. Validação diante do estado atual do pedido**

```
Cliente: pedir 2 hamburguer
Cliente: remover 5 hamburguer
Sistema: Removido 2x Hambúrguer (você pediu 5, mas tinha 2). Pedido vazio.
```

Remover o que não foi pedido, ou mais do que existe, não é erro de escrita — é um
pedido que só não faz sentido *naquele contexto*.

**3. Erro de digitação: corrige ou pergunta, conforme a semelhança**

```
Cliente: 2 amburguers
Sistema: Adicionado 2x Hambúrguer ao pedido (R$ 36.00). ... (entendi 'amburguers' como Hambúrguer)

Cliente: quero 3 sucus
Sistema: Não temos 'sucus' (você quis dizer Suco?) no cardápio. Responda 'sim' para confirmar.
Cliente: sim
Sistema: Adicionado 3x Suco ao pedido (R$ 21.00). ...
```

Erro pequeno (semelhança ≥ 0,85) é corrigido na hora, com aviso. Erro maior vira pergunta,
guardada como **pendência**: "sim" executa, "não" descarta, e qualquer outra frase a
esquece. É o único ponto em que a análise semântica considera a frase *anterior*.

**4. Negação inverte o verbo**

```
Cliente: não vou querer o hambúrguer
Sistema: Removido 1x Hambúrguer do pedido. ...
```

"Não" + verbo de pedir = remover. A frase tem os tokens NEGAR e ADICIONAR; é a
semântica que combina os dois.

**5. Palavra estranha no lugar do verbo não vira pedido**

```
Cliente: xablau 2 refris
Sistema: Não conheço o comando 'xablau'. Para pedir, diga 'quero' ou só os itens; ...
```

Só os itens, sem verbo, é um pedido ("2 refris"). Mas com uma palavra desconhecida na
posição do verbo, assumir "pedir" seria perigoso — foi exatamente assim que, numa versão
anterior, "remova 99 refris" *adicionou* 99 refrigerantes.

## Comandos

| Comando | O que faz |
|---|---|
| `pedir <qtd> <produto>` | põe itens no pedido (também: adicionar, quero, coloca) |
| `remover <qtd> <produto>` | tira itens do pedido (também: tirar, excluir, retirar) |
| `mostrar` | mostra o pedido atual (também: ver, listar) |
| `cardapio` | lista produtos e preços (também: menu, precos) |
| `finalizar` | fecha a conta (também: concluir, fechar) |
| `cancelar` | esvazia o pedido (também: limpar) |
| `ajuda` | lista todos os comandos (também: comandos, help) |
| `sair` | encerra o programa |

A quantidade pode ser número (`2`) ou por extenso (`dois`), e vários itens cabem na
mesma frase. Dentro do programa, `ajuda` imprime a lista completa — montada a partir do
vocabulário real do lexer, então ela nunca fica desatualizada.

O programa entende a frase como um cliente fala, não só como um comando:

| Frase | Entendido como |
|---|---|
| `2 hamburguers e dois refrigerantes` | pedir (sem verbo, o pedido é implícito) |
| `quero pedir 2 pizzas` | pedir (dois verbos da mesma ação não é conflito) |
| `me vê um x-burguer` | pedir 1 hambúrguer |
| `fecha a conta` | finalizar |
| `quanto custa o hamburguer` | "Hambúrguer custa R$ 18.00." |
| `eu vou querer 2 aguas` | pedir 2 águas (sem sobrar "não temos 'eu'") |
| `remover todas as águas` | tira todas as unidades do item |
| `tire metade dos refris` | tira metade do que há (mínimo 1) |
| `adicione um de cada` | 1 de cada produto do cardápio |
| `remova um de cada` | 1 de cada item que está no carrinho |
| `tire tudo` | esvazia o pedido |
| `quiero 2 refris`, `adissione uma pizza` | verbo transcrito errado, aceito por semelhança |

"Todas", "metade" e "de cada" são o que a análise semântica chama de quantidade
*simbólica*: o lexer as marca, mas o número só existe diante do carrinho (ou do cardápio),
e é lá que ele é resolvido.

## Como executar

```bash
python main.py            # modo interativo (digitado)
python main.py --gui      # interface gráfica (ou: python gui.py)
python main.py --demo     # roda pedidos de exemplo, incluindo erros propositais
```

Para usar voz, instale as dependências extras:

```bash
pip install -r requirements.txt
```

## Interface gráfica

Feita só com **tkinter**, da biblioteca padrão. A tela mostra as três coisas que
importam num balcão ao mesmo tempo: o **cardápio** com os preços, o **microfone** e o
**pedido atual** com o total, que se atualiza a cada comando.

- O **círculo central** gira continuamente e funciona como botão: clicar liga o
  microfone, clicar de novo desliga.
- As **barras ao redor** mostram o volume real captado — cada barra é um instante do
  histórico recente, então o anel é a forma de onda do que o microfone ouviu.
- **`+`** ao lado de cada item do cardápio adiciona uma unidade; **`−`** e **`×`** ao
  lado de cada item do pedido tiram uma unidade ou o item inteiro; **Limpar pedido**
  esvazia tudo.

Os botões **não mexem no pedido diretamente**: cada clique gera o comando em texto que
ele representa ("quero 1 pizza", "remova todas as pizzas", "cancelar pedido") e o manda
pelo mesmo pipeline léxico/semântico da voz e do texto. É por isso que o clique aparece
no histórico como `Cliente (botão): quero 1 pizza` — e por isso botão, texto e voz fazem
exatamente a mesma coisa, com uma análise só.

## Voz

- **Falando**, só frases com um **verbo de pedido** contam como comando — "quero dois
  hambúrgueres", "me vê um suco", "adicione uma água", "remova o refri". Com o microfone
  aberto num balcão, quase tudo que se capta é conversa; o verbo é o que separa pedido
  de conversa. "Dois hambúrgueres" dito à mesa é ignorado; "quero dois hambúrgueres" é
  pedido. A resposta sai em áudio.
- **Digitando**, basta os itens ("2 hambúrgueres") e a resposta sai só na tela.

Os verbos são reconhecidos pelo **radical** ("adicion-", "remov-", "retir-", "cancel-"),
então qualquer conjugação serve: adicione, adicionar, adicionando, remova, removendo...
E, como o reconhecimento de fala erra o verbo tanto quanto o produto, um verbo
transcrito errado ("quiero", "adissione", "remuva") é aceito por **semelhança**
(≥ 0,8, só para palavras de 4+ letras — as curtas casariam com qualquer coisa).

A resposta em áudio tenta primeiro uma voz pt-BR instalada no sistema e, se não houver,
usa o Google Text-to-Speech — assim sai em português mesmo em máquina sem voz instalada.

## Funciona em qualquer computador?

Sim. O núcleo do exercício (análise léxica + semântica + cardápio) usa **apenas a
biblioteca padrão do Python**. Sem microfone, sem as bibliotecas de voz, sem internet ou
sem tkinter, o programa avisa e continua funcionando pelo teclado.

## Executável (Windows)

Cada [release](../../releases) traz um **`Lanchonete.exe`** — um arquivo só, sem precisar de
Python nem de `pip install`. É a interface gráfica, com voz incluída. Basta baixar e
abrir (na primeira execução demora alguns segundos: o Windows descompacta o conteúdo).

`Lanchonete.exe --diagnostico` mostra o que a máquina tem disponível para voz (microfone,
vozes instaladas, motor online) — útil para checar o ambiente antes de testar.

Para gerar o executável a partir do código:

```bash
pip install -r requirements.txt pyinstaller
python build_exe.py        # resultado em dist/Lanchonete.exe
```

O Windows Defender às vezes marca executáveis gerados pelo PyInstaller como suspeitos
(falso positivo comum); se acontecer, "Mais informações → Executar assim mesmo".

## Testes

```bash
python -m unittest discover -p "test_*.py" -v
```

São 119 testes:

| Arquivo | Cobre |
|---|---|
| `test_lanchonete.py` | lexer, associação de quantidades, validações, consultas e cardápio |
| `test_linguagem_natural.py` | plural, pedido sem verbo, conjugações, negação, sugestões com "sim"/"não", quantidades simbólicas, verbos por semelhança, sessões reais de uso |
| `test_voz_e_interface.py` | filtro de voz por verbo, síntese, a janela e os botões |
