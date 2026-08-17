# Modelagem física (cold-flow 2D/3D)

> v1 = cold-flow 2D (entregue). Desde então, um caso **3D** (malha grosseira,
> `size_scale`) e a GUI com visualização 3D também estão disponíveis — ver
> README. As decisões de fidelidade abaixo são o núcleo válido para ambos.

## Decisões de fidelidade

| Item | Escolha v1 | Justificativa |
|---|---|---|
| Dimensionalidade | **2D planar** (3D disponível como preview grosseiro) | Escoamento interno de scramjet é quase 2D no plano central; custo baixo permite sweep/otimização. O caso 3D usa malha deliberadamente grosseira p/ iterar rápido (efeitos de sidewall BL ficam para malha plena). |
| Tempo | **Steady RANS** | Cold-flow: o interesse é o estado médio (recuperação, thrust, margem de operação). Transiente só faz sentido com combustão/instabilidade (fase 4+). |
| Compressibilidade | **Compressível (RANS)** | M > 1 em todo o domínio (M∞=6 -> M~3 no combustor). Incompressível é inadmissível. |
| Química | **Cold-flow (sem reação)** | Estabelece a base numérica/malha/BC; combustão adiciona acoplamento químico-térmico (fases 3-5). |
| Equações | **Favre-média Navier-Stokes + energia**, gás ideal caloricamente perfeito (gamma=1.4, R=287.058) | Hipotermia/estado 30 km ISA; transições fortes exigem solver de choque-robusto. |
| Viscosidade | **Sutherland** | mu(T) físico para T de 226 K (entrada) a ~600-900 K (pós-choque). |
| Turbulência | **k-omega SST** | Robusto em separação/choque-camada limite (isolator + wake do strut); melhor que SA para gradientes adversos. |
| Paredes | No-slip adiabáticas (MARKER_HEATFLUX) | Cold-flow: sem fluxo térmico prescrito; transferência térmica entra na fase 5. |

### Condições de contorno (caso de referência)

* **Entrada (supersônica):** M∞ = 6.0, p∞ = 1188 Pa, T∞ = 226.5 K
  (~30 km ISA, ISA), Tu = 0.1%, escala de turbulência 1 mm.
* **Saída (supersônica):** extrapolação característica (exige M_exit > 1,
  garantido pelo bocal com ER=2.0).
* **Paredes:** no-slip adiabáticas (body, cowl, strut).
* **Condição inicial:** campo uniforme = freestream; stage 1 em Euler
  cria um campo de choque razoável e o stage 2 (RANS, restart) converge
  mais rápido e com mais robustez.

## Geometria (parâmetros default)

```
cowl  y=H=0.10 m  ───────────────────────────────────────────────►
        |<-- L_inlet -->|<-- L_iso=0.40 -->|<--L_comb=0.25-->|<- L_noz=0.60 ->|
      O ────────────────┴─── isolador ──────┴─── [strut] ──────┴── \\  O  (H_exit=0.08)
        ramp 6 deg           (H_iso=0.04)                           noz. single-sided
```

* Compressão interna 2.5:1 (ramp de 6°), isolador constante (10·H_iso),
  combustor com leve divergência (1°) + strut simétrico (10 mm x 100 mm)
  gerando wake/recirculação representativa de injetor, bocal de expansão
  simples ER=2.0. Parâmetros completos em `configs/base.yaml`.

## Malha

* Não-estruturada Delaunay com **camada limite anisotrópica** (Gmsh
  `BoundaryLayer` field) nas paredes: primeira célula `h_wall_n = 1e-5 m`
  para `y+ ~ 1` (necessário para SST sem wall-model).
* Caixas de refinamento: inlet (2.5 mm), isolador (1.5 mm — trem de
  choques), combustor/strut (1.2 mm — wake/recirculação), bocal (2.5 mm);
  fundo `h_far = 4 mm`. ~165k células no caso de referência 2D.
* **Malha 3D grosseira**: `mesh.size_scale` (default 1.0) escala todos os
  tamanhos de célula isotrópicos (`h_*`, `h_far`, `bl_thickness`). O caso
  `scramjet_coldflow_3d.yaml` usa `size_scale: 2.2` → ~32k células (vs.
  ~307k plenas), ~5-8x mais rápido nos estágios RANS. O 2D fica em `1.0`.
* **Qualidade:** primeira célula a 1e-5 m (y+~1), malha msh 2.2 ascii com
  physical groups nomeados como os markers do SU2 (inflow, outflow, body,
  cowl, strut, fluid).
* **Independência de malha:** `python -m backend.interfaces.cli mesh-study`
  (ou `scripts/mesh_study.py`) roda escalas [1.0, 0.75, 0.5, 0.35] mantendo a
  primeira célula fixa e compara `pressure_recovery` e `thrust_proxy` (aceite
  mudança < ~1-2%).

## Método numérico (SU2)

* ROE + MUSCL (limitador Venkatakrishnan) para escoamento; EULER_IMPLICIT;
  FGMRES/ILU; CFL=1.0 (reduzir p/ 0.5 se divergir); critério
  `CONV_RESIDUAL_MIN=1e-9` em RMS density, máx. 5000 iterações.
* Convergência avaliada por resíduo + invariantes (continuidade de vazão
  mássica, monotonicidade de p0, estabilidade do monitor).

## Métricas (resumo; detalhes em `backend/application/metrics.py`)

* `pressure_recovery` = p0_exit / p0_capture (ponderado por vazão mássica).
* `thrust_proxy` = -[ (ṁ·Vx + p·A)_exit - (ṁ·Vx + p·A)_capture ] (N/m de
  envergadura). Proxy de força axial nos internos; **não** inclui o
  empuxo/captação externa da cowl (fase 2+).
* `mixing_uniformity` = 1 - std(Mach)/mean(Mach) na saída do combustor
  (proxy cold-flow de mistura; na fase 3 vira métrica de injeção).
* `sep_fraction` = fração de células adjacentes à parede com retrofluxo.
* `operating_margin` = mínimo M ponderado no isolador (alerta de unstart).
* `score` = combinação linear ponderada (0.40·recovery + 0.30·thrust +
  0.15·mixing - 0.10·sep - 0.05·continuity - 0.25·unstart) — objetivo do
  otimizador.
