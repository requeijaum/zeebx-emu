# 32 — Perfilamento: onde o guest gasta as instruções

Dois instrumentos vivem na biblioteca e respondem perguntas diferentes. A amostragem de PC responde
*qual código está quente*; o log de draws responde *por que um desenho que chegou ao rasterizador
não apareceu*. Os dois ficam desligados até uma variável de ambiente pedir, e nenhum deles custa
nada numa execução normal.

## Amostragem de PC

```
ZEEBX_PCSAMPLE=20000 ZEEBX_PCSAMPLE_OUT=perfil.txt \
  zeebx run jogo.mod --seconds=80
```

`ZEEBX_PCSAMPLE=N` faz o interpretador parar o guest a cada N instruções em vez de correr até o
orçamento, e anota o PC em que parou. `ZEEBX_PCSAMPLE_OUT` é onde o histograma sai. O arquivo é
reescrito a cada 2000 amostras, então uma execução interrompida ainda deixa um perfil utilizável.

Cada linha tem quatro colunas hexa: `pc lr saved count`. `lr` é o endereço de retorno, e `saved` é a
palavra em `sp + 16`, o slot onde o prólogo ARM costuma guardar o `lr` do chamador: é uma
heurística de "um frame acima", não uma desmontagem garantida. A terceira coluna existe por causa do
soft-float: o ARM11 do Zeebo não tem VFP, então toda operação de `float` é uma
chamada ao libgcc, e uma amostra que cai lá só interessa pela função que a pediu.

`tools/pcsample_report.py` transforma o histograma num perfil por símbolo:

```
python3 tools/pcsample_report.py perfil.txt --elf build/sa1g.elf --base 0x10200
```

`--base` é o deslocamento de carga: o applet é ligado para `0x0` e roda de onde o carregador o pôs,
e isso é a diferença entre os dois (o port do Sonic Adventure, por exemplo, carrega em `0x10200`).
Com `--nm simb.txt` o script usa uma listagem de `arm-none-eabi-nm -n` em vez do ELF. Por padrão ele
achata os auxiliares de soft-float no chamador e os soma como "soft-float"; `--no-flatten` os conta
onde estão, que é como se mede o tamanho da conta do soft-float.

No port do Sonic Adventure, no primeiro chefe, 80 segundos e 652 mil amostras:

```
amostras 652000  soft-float 63.7%
  7.7%  sa_ftrv
  7.3%  sprite_view
  5.4%  f__njInvertMatrix
  3.8%  draw_meshset_gl.isra.0
  3.8%  sqrtf
  3.7%  f__polygon_find_heights
```

O perfil é uma aproximação, e é honesto sobre isso: a amostra é onde o interpretador parou dentro da
fatia, então uma função chamada poucas vezes mas demorada aparece super-representada do mesmo jeito
que num amostrador de tempo de parede. Código cheio de desvios é contado por instrução, não por
tempo — os dois concordam só quando a memória não é o gargalo, que é o caso aqui.

## Log de draws

```
ZEEBX_DRAWLOG=120000:3 zeebx run jogo.mod --seconds=20
```

`ZEEBX_DRAWLOG=primeiro:quantos` imprime uma linha por draw cujo índice cai na janela, com o que o
estágio de vértices manteve e o que o estágio de fragmentos vai aplicar:

```
[draw 120001] mode=5 verts=4 tris=2 tex=59 blend=true 1+771 depth=true 515 atest=false 519
```

`verts` é quantos vértices sobreviveram à transformação, `tris` quantos triângulos o modo produziu
depois do corte do plano próximo, e os números depois de `blend` e `depth` são os enums de GL em
vigor. Um draw com `tris=0` nunca chega a um fragmento: a geometria ou a matriz está errada. Um draw
com `tris>0` e nada na tela é a outra metade do problema, e o estado diz qual teste o rejeitou —
`GL_LEQUAL` contra um depth buffer que ainda guarda a cena 3D, um teste de alfa com uma referência
que o alfa do painel não passa, ou uma mistura cujos fatores se cancelam.

A janela importa porque um quadro manda centenas de draws: `ZEEBX_DRAWLOG=0:2` imprime os primeiros
da execução, e o índice se acha por bisseção. O contador é por rasterizador e reinicia com a sessão.

## O que os dois não fazem

Nenhum dos dois mede tempo no rasterizador: no caminho de software os fragmentos são trabalho do
host, e nenhum instrumento do guest vê isso. `--dump-surfaces` e o contador de quadros do log cobrem
a imagem; o custo de um draw só aparece na placa (`--gpu`) ou com um profiler de host ligado ao
processo do emulador.
