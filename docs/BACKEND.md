# Backend: camadas, módulos e pontos de entrada

O código Python da pipeline foi reorganizado num único pacote **`backend/`**
em camadas (domain → application → infrastructure → interfaces). O objetivo é
separar a *física/modelo* do *orquestramento* da *infraestrutura pesada*
(Gmsh, SU2, PyVista) e de tudo que é *externo* (CLI, API para GUI), de forma
que cada parte seja testável isoladamente e substituível.

## 1. Mapa de módulos

```
backend/
├── domain/                          # modelo puro, sem dependências pesadas
│   ├── config.py                    # dataclasses (Flow/Geometry/Mesh/Solver),
│   │                                #   load_case(), apply_overrides(), validate()
│   └── geometry.py                  # build_geometry(), station_x(), summary(),
│                                    #   write_geometry_json()  [geometria 2D]
├── application/                     # orquestração + engenharia
│   ├── pipeline.py                  # run_experiment(cfg, workdir, steps, ...)
│   │                                #   geometry -> mesh -> case -> run -> post -> metrics
│   ├── metrics.py                   # compute_case_metrics(), score()  (objetivo)
│   ├── engineering.py               # pós-processamento PyVista: estações, campos,
│   │                                #   separação, snapshots (postprocess_case)
│   ├── sweep.py                     # sweep paramétrico (grid) -> results.csv
│   ├── mesh_study.py                # estudo de independência de malha
│   └── optimizer.py                 # simulated annealing / Metropolis
├── infrastructure/                  # ferramentas "externas", sem lógica de física
│   ├── su2.py                       # find_solver(), run_case_stages(),
│   │                                #   locate_solution_vtu(), resíduos do log
│   ├── meshing.py                   # make_mesh()  [Gmsh -> SU2 .su2]
│   ├── casewriter.py                # render_config()/write_case_configs()  [decks SU2]
│   ├── export.py                    # results_row(), append_rows()  [CSV p/ ML]
│   ├── accel.py                     # kernels pós GPU (CuPy) com fallback NumPy
│   │                                #   cell_extents, min_dist_to_polylines
│   ├── vtu.py                       # (futuro) carregamento/campos derivados de VTU
│   └── viz.py                       # helpers compartilhados de visualização:
│                                    #   _revolve, _annulus_disc, _toroid_band,
│                                    #   _channel_field, _write_gif, R0, RES
└── interfaces/                      # tudo que dá acesso ao mundo exterior
    ├── cli.py                       # CLI unificada (run/sweep/mesh-study/anneal/viz-*)
    ├── api.py                       # API JSON programática p/ GUI/web (facade)
    ├── server.py                    # servidor RPC localhost (stdlib) p/ GUI:
    │                                #   handshake de token, dispatch p/ api.py
    ├── _jobworker.py                # subprocess que executa métodos longos
    │                                #   (run_case, render_*) com progresso
    └── visualization/               # renderizadores PyVista/Matplotlib
        ├── schematic.py             # diagrama de engenharia (lateral, anotado)
        ├── engine3d.py              # renders 3D isométricos estáticos
        ├── ramjet3d.py              # nacela cilíndrica + GIF rotativo
        ├── crosssection.py          # cortes transversais (y-z) + GIF
        ├── anim3d.py                # volume 3D animado (clip/slice) + GIF
        └── vehicle.py               # veículo estilo X-43A / Hyper-X

scripts/                             # wrappers finos -> backend.interfaces.cli
tests/                               # self-tests (sem gmsh/pyvista no test_pipeline)
configs/                             # YAMLs (base.yaml, cases, sweeps) + template .cfg
```

## 2. Regras de dependência

```
interfaces  ──► application ──► infrastructure ──► domain
   │                │                 │
   └───────────────┴─────────────────┴──────────► (todos podem importar domain)
```

* **domain**: nenhuma dependência de gmsh / pyvista / SU2 / numpy*.
* **infrastructure**: encapsula ferramentas externas (Gmsh, SU2, VTU, CSV,
  helpers de visualização); não implementa física nem regra de negócio.
* **application**: orquestra domain + infrastructure; implementa a lógica de
  engenharia e de otimização.
* **interfaces**: CLI, API e renderizadores; é a única camada que o usuário
  (script, shell, GUI) toca.

> \* `domain/geometry.py` usa apenas `math`/`json`; `domain/config.py` usa
> `yaml` (leitura de casos). Nada de matplotlib/pyvista lá.

Bootstrap de import: cada módulo do pacote insere a raiz do repositório em
`sys.path` automaticamente, então os módulos podem ser executados como script
(`python backend/application/mesh_study.py ...`) ou como pacote
(`python -m backend.application.mesh_study`).

## 3. Pontos de entrada

### CLI unificada (`python -m backend.interfaces.cli`)

| Comando | Descrição | Equivalente antigo |
|---|---|---|
| `run` | pipeline completa de um caso | `run_sim.py` |
| `sweep` | sweep paramétrico | `run/sweep.py` |
| `mesh-study` | estudo de independência de malha | `run/mesh_study.py` |
| `anneal` | otimização simulated annealing | `optimization/anneal.py` |
| `mesh` | gerar malha de um caso | `mesh/make_mesh.py` |
| `case` | escrever decks SU2 | `cases/build_case.py` |
| `postprocess` | extrair grandezas de um caso resolvido | `post/postprocess.py` |
| `viz-schematic` | diagrama lateral anotado | `post/schematic.py` |
| `viz-engine` | renders 3D estáticos | `post/engine3d.py` |
| `viz-ramjet` | nacela cilíndrica + GIF | `post/ramjet3d.py` |
| `viz-crosssection` | cortes y-z + GIF | `post/crosssection.py` |
| `viz-anim` | animação 3D + GIF | `post/anim3d.py` |
| `viz-vehicle` | veículo X-43A | `post/vehicle.py` |

Cada subcomando aceita `-h`. Os `scripts/*.py` são wrappers de uma linha que
delegam para o mesmo CLI.

### API programática (`backend.interfaces.api`)

Retorna apenas dicionários JSON-serializáveis e `str` de caminhos:

```python
from backend.interfaces import api

desc = api.describe_case("configs/cases/scramjet_coldflow.yaml")   # editor de params
report = api.run_case("configs/cases/scramjet_coldflow.yaml",
                      "runs/exp_m6", steps=["geometry", "mesh"])
metrics = api.load_metrics("runs/exp_m6")                          # dict ou None
stations = api.load_stations("runs/exp_m6")
outputs = api.load_outputs("runs/exp_m6")                          # arquivos p/ navegar
runs = api.list_runs("runs")                                       # resumo p/ lista
pngs = api.render_schematic("configs/cases/scramjet_coldflow_3d.yaml", "runs/meu3d")
```

### Servidor RPC localhost (GUI)

`backend/interfaces/server.py` expõe a mesma `api` por JSON sobre HTTP/stdio
na máquina local (127.0.0.1), com handshake de token gerado em runtime. O
processo principal do Electron o inicia e descobre a raiz do repositório
(subindo a árvore a partir de `ui/` até encontrar `backend/` + `configs/`, ou
via `SCRAMJET_HOME`). Métodos longos são delegados a um subprocess
(`_jobworker.py`) e polidos com `job_status`; o progresso vem de artefatos do
workdir + parse dos logs do SU2. O token é efêmero — nunca é persistido em
disco nem versionado.

```powershell
python -m backend.interfaces.server   # inicia e imprime SCRAMJET_SERVER_URL / SCRAMJET_TOKEN
```

## 4. Mapeamento antigo → novo (para quem migra código)

| Antes | Agora |
|---|---|
| `geometry/params.py` | `backend.domain.config` |
| `geometry/make_geometry.py` | `backend.domain.geometry` |
| `mesh/make_mesh.py` | `backend.infrastructure.meshing` |
| `cases/build_case.py` | `backend.infrastructure.casewriter` |
| `run/run_solver.py` | `backend.infrastructure.su2` |
| `run/pipeline.py` | `backend.application.pipeline` |
| `run/sweep.py` | `backend.application.sweep` |
| `run/mesh_study.py` | `backend.application.mesh_study` |
| `post/metrics.py` | `backend.application.metrics` |
| `post/postprocess.py` | `backend.application.engineering` |
| `post/export_tables.py` | `backend.infrastructure.export` |
| `optimization/anneal.py` | `backend.application.optimizer` |
| `post/ramjet3d.py` | `backend.interfaces.visualization.ramjet3d` |
| `post/crosssection.py` | `backend.interfaces.visualization.crosssection` |
| `post/anim3d.py` | `backend.interfaces.visualization.anim3d` |
| `post/schematic.py` | `backend.interfaces.visualization.schematic` |
| `post/engine3d.py` | `backend.interfaces.visualization.engine3d` |
| `post/vehicle.py` | `backend.interfaces.visualization.vehicle` |

Os nomes de função/módulo internos não mudaram (ex.: `run_experiment`,
`make_mesh`, `build_geometry`, `compute_case_metrics`), então a migração é
apenas de prefixos de import.

## 5. Guia rápido de extensão

* **Novo parâmetro de caso**: editar o dataclass em `backend/domain/config.py`
  (default técnico) e o YAML correspondente em `configs/`.
* **Nova métrica**: adicionar em `backend/application/metrics.py` e
  incorporar no `score()`.
* **Trocar o solver**: reimplementar as funções de `backend.infrastructure.su2`
  mantendo a assinatura; `pipeline.py` não muda.
* **Novo renderizador**: colocar em `backend/interfaces/visualization/`,
  registrar em `backend/interfaces/cli.py` (SUBCOMMANDS) e em
  `backend/interfaces/api.py` (render_all) e criar o wrapper em `scripts/`.
* **GUI**: consumir `backend.interfaces.api` (descrever caso → editar
  parâmetros → `run_case` → `load_*` → `render_*`).
