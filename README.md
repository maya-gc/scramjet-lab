# scramjet-lab

Pipeline de CFD reproduzível para um **scramjet cold-flow** (compressível,
supersônico, 2D e 3D) com arquitetura pronta para extensão a combustão,
injeção de combustível e otimização paramétrica. Inclui uma **GUI desktop**
(Electron + React) com visualização 3D e acelerador de pós-processamento via
GPU (opcional).

**Stack:** SU2 (RANS) + Python + Gmsh (malha paramétrica) + PyVista (pós) +
Electron/React/TypeScript (GUI). Justificativa em `docs/ARCHITECTURE.md`.

## Funcionalidades

- Geometria paramétrica 2D e 3D (inlet + isolador + combustor/strut + bocal).
- Malha Gmsh com camada limite anisotrópica (y+ ~ 1) e refinamento regional.
- Solver SU2: stage 1 Euler (warm start) → stage 2 RANS (SST), gás ideal.
- Métricas de engenharia: recuperação de pressão total, thrust proxy, mistura,
  separação, margem de operação (unstart) e score composto.
- Sweep paramétrico, estudo de independência de malha e otimização
  (simulated annealing) — todos com exportação CSV para ML.
- GUI desktop: editor de parâmetros com validação em tempo real, visualização
  3D com partículas de escoamento em GPU (WebGL2), progresso da simulação por
  estágio, métricas/gauges/gráficos axiais e comparação entre execuções.
- Pós-processamento acelerado por GPU opcional (CuPy, com fallback NumPy).

## Requisitos

- **Python 3.10+** no `PATH` (dependências em `requirements.txt`).
- **SU2 (opcional, recomendado)**: binário `SU2_CFD` na página oficial
  <https://su2code.github.io/downloads.html>, com a pasta `bin` no `PATH`
  ou a variável de ambiente `SU2_CFD` apontando para o executável.
  *Sem o SU2 instalado, a GUI ainda funciona em modo **Preview***
  (geometria + malha + caso, sem resolver o escoamento).
- **Node.js 18+** (somente para construir/rodar a GUI).
- **CUDA (opcional)**: apenas para o acelerador CuPy de pós-processamento
  (`cupy-cuda12x` etc.); a GUI 3D usa WebGL2 e não precisa de CUDA.

## Instalação

```powershell
# 1. Backend (Python)
pip install -r requirements.txt

# 2. Verificar o solver (opcional)
SU2_CFD -h

# 3. GUI (da pasta ui/)
cd ui
npm.cmd install     # primeira vez; .npmrc aprova os postinstall scripts
npm.cmd run dev     # modo desenvolvimento (HMR)
```

> No Windows, use `npm.cmd` (o `npm.ps1` é bloqueado pela Execution Policy).

## Rodar uma simulação (CLI)

```powershell
# pipeline completa (geometria -> malha -> caso -> SU2 -> pós -> métricas)
python run_sim.py --case configs/cases/scramjet_coldflow.yaml

# somente geometria + malha (sem solver)
python run_sim.py --steps geometry,mesh

# caso 3D (malha grosseira de preview, ~5-8x mais rápida)
python run_sim.py --case configs/cases/scramjet_coldflow_3d.yaml

# sobrescrever parâmetros da linha de comando
python run_sim.py --overrides flow.mach=5.0 geometry.isolator_length=0.30

# diretório de experimento customizado
python run_sim.py --workdir runs/exp_m6
```

Cada experimento gera `runs/<case>/` com:

```
geometry/geometry.json      parametros derivados (H_iso, L_inlet, x_total, ...)
mesh/<case>.su2             malha SU2 ascii (gerada via Gmsh)
case/config/*.cfg           decks stage1 (Euler) e stage2 (RANS)
run/*.log                   historico do solver
run/*.vtu                   solucao (ParaView / PyVista)
post/*.png                  campos de Mach/pressao, pressao de parede
post/stations.json          integrais por estacao
metrics.json                vetor de metricas completo
report.json                 relatorio consolidado
```

## Interface gráfica (GUI)

A GUI controla a pipeline completa: **Parametrizar → Preview (3D) → Rodar →
Resultados**. A comunicação com o backend usa um servidor RPC localhost
(stdlib) iniciado automaticamente pelo processo principal do Electron, com
handshake de token gerado em runtime (nada de segredos versionados).

```powershell
# da pasta ui/
npm.cmd run dev        # desenvolvimento (HMR)
npm.cmd run build      # build de produção -> ui/out
npm.cmd run typecheck  # checagem de tipos (main/preload + renderer)
```

Uso rápido:

1. Abra a GUI, escolha um caso em **Configs** e edite os parâmetros.
2. Clique em **Preview** para gerar geometria + malha + caso e explorar o
   modelo 3D (sem precisar de SU2).
3. Clique em **Run** para resolver (progresso por estágio: geometry → mesh →
   case → solver → post → metrics).
4. Acompanhe em **Results** as métricas/gauges, em **Charts** o perfil axial
   (Mach, pressão, temperatura, estagnação, velocidade) e compare execuções.

> Campo **SU2 solver exe**: deixe vazio para usar o solver descoberto
> automaticamente. Só preencha se tiver um executável customizado.

## Varrer parâmetros (sweep)

```powershell
python scripts/sweep.py --config configs/sweeps/sweep_isolator.yaml
python run_sim.py --overrides geometry.isolator_length=0.50 flow.mach=5.5 --workdir runs/alt
```

O resultado acumula em `runs/sweep_isolator/results.csv` (features de entrada
`in_*` + métricas `out_*`, pronto para ML).

## Independência de malha

```powershell
python scripts/mesh_study.py --case configs/cases/scramjet_coldflow.yaml
```

## Otimização (simulated annealing / Metropolis)

```powershell
python scripts/anneal.py --case configs/cases/scramjet_coldflow.yaml `
    --params geometry.isolator_length=0.2:0.6 geometry.intake_angle_deg=3.0:8.0 `
    --iters 40 --workdir runs/anneal
```

## Malha 3D grosseira (`size_scale`)

O caso 3D usa malha deliberadamente grosseira para iteração rápida:
`configs/cases/scramjet_coldflow_3d.yaml` define `mesh.size_scale: 2.2`, que
escala todos os tamanhos de célula isotrópicos (`h_*`, `h_far`,
`bl_thickness`) e produz ~32k células (vs. ~307k na malha plena), acelerando
~5-8x os estágios RANS. O caso 2D usa `size_scale: 1.0`.

## Testes (sem SU2)

```powershell
python tests/test_pipeline.py
python tests/test_postprocess_synthetic.py   # requer pyvista
```

## Documentação

| Arquivo | Conteúdo |
|---|---|
| `docs/ARCHITECTURE.md` | arquitetura, módulos e justificativa da stack |
| `docs/BACKEND.md` | mapa do pacote `backend/`, camadas, CLI e API |
| `docs/MODELING.md` | modelo físico, geometria, malha, condições de contorno |
| `docs/VALIDATION.md` | checklist de validação e benchmarks |
| `docs/ROADMAP.md` | evolução em fases (2D -> 3D -> combustão -> otimização) |

## Publicar no GitHub

Este repositório é limpo para publicação: nenhum caminho local, credencial ou
artefato de runtime é versionado. O `.gitignore` cobre ambientes virtuais,
`node_modules/`, builds, `runs/` (experimentos), logs, malhas/soluções
geradas e arquivos de ambiente/secrets. O token RPC é gerado em runtime e
nunca é persistido.