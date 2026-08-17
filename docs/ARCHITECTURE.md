# Arquitetura da pipeline

## Escolha da stack: SU2 + Python + Gmsh + PyVista

| Critério | SU2 | OpenFOAM |
|---|---|---|
| Execução nativa no Windows | Sim (binários oficiais) | Não (exige WSL2/Docker) |
| RANS compressível hipersônico | Sim (SA, SST) | Sim |
| Automação Python paramétrica | Config única `.cfg` + Python API | Casos = árvore de dicionários + script |
| Otimização futura | **Adjoint embutido** (gradiente) | Requer plugins/DAS |
| Curva de aprendizado p/ quem automatiza | Baixa-média | Alta |
| Comunidade em scramjet/inlet | Moderada (VKI, Stanford, NASA) | Alta (mas em combustão/reativo) |

Decisão: **SU2 + Gmsh + PyVista**. Motivos principais:

1. **Ambiente Windows sem WSL**: SU2 distribui binários nativos; OpenFOAM
   seria uma camada extra de virtualização com custo de manutenção alto.
2. **Formato de entrada declarativo** (`.cfg` textual) é trivial de gerar a
   partir de um template Python — ideal para sweep/otimização.
3. **Adjoint nativo** permite evoluir de simulated annealing para
   otimização baseada em gradiente sem trocar de solver.
4. Gmsh (API Python) gera malha paramétrica com refinamento e camada limite
   diretamente ligada aos parâmetros geométricos; PyVista lê os `.vtu` do
   SU2 e extrai as métricas de engenharia.

Trade-off aceito: SU2 tem menos material de referência em combustão
supersônica reativa que OpenFOAM; mitigado pelo roadmap (fases 4-5 podem
migrar a química para `scramjet`/cantera acoplado ou para OpenFOAM se
necessário — a interface da pipeline isola o solver por trás de
`backend.infrastructure.su2`).

## Módulos e responsabilidades

```
configs/        Fontes da verdade: defaults (base.yaml), casos, templates.
backend/        Pacote Python em camadas: domain / application / infrastructure / interfaces.
  domain/        Modelo paramétrico (dataclasses) + construção da geometria pura.
  application/   Pipeline, sweep, mesh study, otimização, pós/engenharia, métricas.
  infrastructure/ Gmsh (malha), decks SU2, executor do solver, VTU, export CSV,
                 viz helpers, accel (CuPy/NumPy p/ pós-processamento em GPU).
  interfaces/    CLI unificado, API (JSON) para GUI, servidor RPC localhost,
                 job worker (subprocess), renderizadores PyVista.
scripts/        Wrappers finos que delegam para backend.interfaces.cli.
docs/           Modelagem, validacao, roadmap.
tests/          Self-tests (geometria, config, metricas com solucao sintetica).
ui/             GUI desktop (Electron + React + TypeScript): editor, cena 3D,
                execução da pipeline, resultados.
```

## Fluxo de dados

```
configs/cases/*.yaml
      │  (inclui configs/base.yaml; overrides via CLI)
      ▼
backend.domain.geometry ──► geometry.json        (pontos, derivados, estacoes)
      │
      ▼
backend.infrastructure.meshing ──► <case>.su2     (fisical groups p/ SU2)
      │
      ▼
backend.infrastructure.casewriter ──► *_stage1_euler.cfg (RESTART_SOL=NO)
                                     *_stage2_rans.cfg  (RESTART_SOL=YES)
      │
      ▼
backend.infrastructure.su2 ──► SU2_CFD ──► run/*.log, *.vtu
      │
      ▼
backend.application.engineering ──► estacoes, campos, PNG, separacao
backend.application.metrics  ──► metrics.json (pressao recovery, thrust proxy, score)
      │
      ▼
backend.infrastructure.export ──► results.csv (sweep/otimizacao/ML)
```

A GUI (Electron) não importa o backend diretamente: fala com
`backend.interfaces.api` por um **servidor RPC localhost** (stdlib) em
`backend/interfaces/server.py`, iniciado pelo processo principal do Electron
com handshake de token gerado em runtime. Métodos longos (`run_case`,
`render_*`) rodam em subprocessos (`backend/interfaces/_jobworker.py`),
polidos via `job_status` com progresso vindo de artefatos reais do workdir +
parse dos logs do SU2.

## Reproducibilidade

* Cada experimento é um diretório autocontido (`runs/<exp>/`) com
  geometria, malha, configs, logs, solução e métricas.
* Tudo derivado de um YAML + overrides: `report.json` registra a cadeia
  completa para auditoria.
* Extensão futura sem refactor: trocar `backend.infrastructure.su2` (SU2 ->
  outro solver) ou `backend.infrastructure.meshing` não toca em
  `backend.application` nem `backend.interfaces`.

## Camadas e regras de dependência

Regra geral: o fluxo de dependências aponta para dentro e para baixo na
camada seguinte:

```
interfaces  (cli, api, visualizacao)   pode importar application, infrastructure, domain
application (pipeline, sweep, otimizacao, engenharia, metricas)
infrastructure (gmsh, su2, casewriter, export, vtu, viz)   pode importar domain
domain      (params, geometry)         sem dependências de infraestrutura
```

* `domain` não importa gmsh / pyvista / SU2.
* `application` orquestra `domain` + `infrastructure`.
* `interfaces` expõe tudo para CLI/scripts/GUI.

## GUI (Electron + React) e aceleração por GPU

* **GUI**: aplicação desktop em `ui/` (Electron + React + TypeScript, bundler
  electron-vite). Apenas consome `backend.interfaces.api` via servidor RPC
  localhost — nunca importa internals do backend.
* **Cena 3D (WebGL2, GLSL3)**: `ui/src/renderer/src/three/gpu.ts` renderiza as
  partículas de escoamento inteiramente na GPU (texturas em vertex shader +
  `gl_VertexID`, sem laço por partícula na CPU). Requer WebGL2; `engine.ts`
  cai para geometria pura quando indisponível.
* **Pós-processamento (CuPy opcional)**: `backend/infrastructure/accel.py` é o
  único módulo que importa CuPy; os kernels aceitam/retornam arrays NumPy e
  usam GPU quando disponível, com fallback NumPy (sem `np.minimum.at`, via
  sort + `reduceat`). O RPC `health` expõe `accel.{backend,gpu}`.
* **Malha 3D grosseira**: o caso 3D usa `mesh.size_scale` (ver README) para
  iterar rápido; a malha plena ~307k células é ociosamente cara em
  single-thread.

Detalhes, mapa de módulos e exemplos de código em `docs/BACKEND.md`.
