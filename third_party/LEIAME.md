# `third_party/dynarmic` — o `dynarmic` 0.1.3 com o monitor exclusivo

Cópia do crate **`dynarmic` 0.1.3** (crates.io), com **uma** mudança. Ele entra na árvore por
`[patch.crates-io]` no `Cargo.toml` da raiz, e é assim que a CI e qualquer dev pegam o conserto
pelo `Cargo.lock` — não há receita local de build, e não há variável de ambiente a exportar.

## Por que existe

O emulador configura o JIT A32 sem `global_monitor`, e o crate **não tinha como preencher**: em
`src/a32.rs`, `Config::new` fazia `global_monitor: unsafe { std::mem::zeroed() }, // todo`, e não
existe setter público. O campo chegava nulo ao Dynarmic C++.

Nulo não é inofensivo: o emissor x64 exige o monitor **no momento da tradução** do bloco.

```
dynarmic/src/dynarmic/backend/x64/emit_x64_memory.cpp.inc:224
    ASSERT(conf.global_monitor != nullptr);
```

Logo, qualquer bloco do guest com `LDREX`/`STREX` — 40 dos 62 `.mod` do acervo têm o padrão em
algum lugar — abortava o processo **antes** de as asserções serem lidas. Medido em 24/09/2026, no
teste `src/cpu/dynarmic.rs::a_instrucao_exclusiva_nao_derruba_o_processo`:

```
running 1 test
assertion failed: conf.global_monitor != nullptr
Message:(none)terminate called without an active exception
error: test failed, to rerun pass `-p zeebx --lib`
  process didn't exit successfully: ... (signal: 6, SIGABRT: process abort signal)
```

Não havia opção de flag: `OptimizationFlag::UNSAFE_IGNORE_GLOBALMONITOR` existe no enum Rust, mas o
C++ vendorizado no crate **não conhece** esse sinal (zero ocorrências em `dynarmic/src`), e o
`ASSERT` está no caminho de emissão, não no de execução.

## Por que vendorizar, e não subir de versão

`0.1.3` é a **última** versão publicada do crate (índice do crates.io: `0.1.0` yanked, `0.1.1`,
`0.1.2`, `0.1.2-eden`, `0.1.3`). Não existe versão mais nova que exponha o monitor, então a
alternativa (a) não existe e o conserto é este.

## O que mudou em relação ao 0.1.3

Um único acréscimo, em `src/a32.rs`: o método público abaixo, ao lado dos outros construtores de
`Config`. Nada mais foi tocado — o diff completo contra o crate do registry é este bloco.

```rust
    pub fn global_monitor(&mut self, monitor: &mut crate::ExclusiveMonitor) -> &mut Self {
        self.config.global_monitor = monitor;

        self
    }
```

O `DynarmicConfig` da A32 (com `#[repr(C)]`) já tinha o campo na posição que o
`Dynarmic::A32::UserConfig` do C++ espera — os `static_assert` de tamanho em `src/wrapper.hpp` já
concordavam (368 bytes) —, então nenhuma linha de C++ precisou mudar.

Quem usa, em `src/cpu/dynarmic.rs`: a CPU guarda um `Box<ExclusiveMonitor>` (`Box` porque o JIT
guarda o **ponteiro**, não uma cópia, e um campo que se move deixaria o ponteiro pendurado) e passa
`config.global_monitor(&mut self.monitor)` em `reset`, antes de `config.init`. O monitor é criado com
**um** processador: o Zeebo tem um núcleo.

## Como atualizar este vendor

```sh
cp -a ~/.cargo/registry/src/index.crates.io-*/dynarmic-0.1.3/. third_party/dynarmic/
# reaplique o bloco `global_monitor` em third_party/dynarmic/src/a32.rs
```

Se o crate for publicado numa versão com o setter, **apague este diretório** e retire o
`[patch.crates-io]` do `Cargo.toml`: o vendor existe só até a dependência resolver o problema.

## Licença e atribuição

O invólucro Rust é **0BSD** (`LICENSE.txt`), e o Dynarmic C++ que ele compila está em
`dynarmic/LICENSE.txt` (**Apache-2.0 com LLVM Exception**), com os `externals/` que o crate já
empacotava (biscuit, fmt, mcl, oaknut, xbyak, zydis, catch e outros), cada um com a licença própria.
Os textos originais foram preservados junto do código, e esta cópia não acrescenta licença nenhuma.

- Origem: <https://github.com/exverge-0/dynarmic-rs> (invólucro) e
  <https://github.com/exverge-0/dynarmic> (o C++ empacotado)
- Versão: `0.1.3`, sem alteração de número — é o mesmo pacote mais o setter, o que é o que o
  `[patch.crates-io]` exige para casar com a exigência `dynarmic = "0.1.3"` do `Cargo.toml`.
- Arquivos de estado do registry (`.cargo-ok`, `Cargo.lock` do próprio crate) foram deixados fora.
