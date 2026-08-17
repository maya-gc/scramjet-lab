# Checklist de validação

O objetivo é estabelecer confiança em cada nível antes de confiar nas
métricas da pipeline. Marque cada item quando satisfeito e registre o
resultado em `runs/validation/`.

## 1. Verificação numérica

- [ ] **Onda de choque oblíqua** — caso solo (ramp plana, sem domínio):
  comparar ângulo do choque com teoria (M∞, theta) para M=6, erro < 1°.
- [ ] **Recuperação de pressão em expansão isentrópica** — escoamento de
  tubo convergente-divergente: p0 constante, erro < 0.5%.
- [ ] **Continuidade mássica** — `continuity_error` < 0.5% num caso
  convergido (a pipeline reporta a métrica).
- [ ] **Simetria do escoamento** — campo espelhado em geometria simétrica
  reproduz métricas a < 0.1%.

## 2. Malha

- [ ] **y+ < 1 na primeira célula** em paredes (body, cowl, strut).
- [ ] **Qualidade de célula** — razão de aspecto / skewness dentro dos
  limites para Delaunay (ângulo mínimo > 20° no grosso das células).
- [ ] **Independência de malha** — `python -m backend.interfaces.cli mesh-study`:
  pressure_recovery e thrust_proxy variam < 1-2% entre as duas malhas
  mais finas.
- [ ] Sem células negativas/sobrepostas na camada limite do strut
  (Gmsh reporta "invalid" se houver).

## 3. Física cold-flow

- [ ] **Inlet iniciado** — sem unstart: M ponderado no isolador > 1,
  `unstart_risk = false`.
- [ ] **Trem de choques** visível no isolador (campo de Mach) com padrão
  de reflexão característico de ducto reto.
- [ ] **Recuperação de pressão total** na faixa plausível para inlet M=6
  com CR=2.5 (típico 0.3-0.7; registre o valor do caso).
- [ ] **Expansão no bocal** — M_exit > 1 e pressão de saída ~ p∞
  (condição de saída plenamente supersônica).
- [ ] **Wake do strut** — zona de recirculação imediatamente a jusante
  (proxy: `sep_fraction > 0` apenas na região do strut).
- [ ] **Sensibilidade a CFL** — caso estável para CFL 0.5-2.0 sem mudar o
  resultado estacionário (> 3 casas em recovery).

## 4. Benchmark (quando disponível)

- [ ] **HyShot-2 / SCHOLAR (NASA Langley)** — comparar pressão de parede
  no isolador/combustor com dados de túnel (ordem de grandeza e posição
  do pico de pressão).
- [ ] Comparação com **CFD publicada** (mesmas condições M, p, T): recovery,
  localização do primeiro choque, momento axial.

## 5. Pipeline / reprodutibilidade

- [ ] Dois runs idênticos produzem `metrics.json` bit-identico (bitwise)
  para métricas flutuantes (< 1e-12 de diferença).
- [ ] `run_sim.py --steps geometry,mesh` roda sem solver instalado.
- [ ] Sweep de 1 parâmetro com 3 valores completa e grava `results.csv`.
- [ ] `tests/test_pipeline.py` e `tests/test_postprocess_synthetic.py` passam.

## 6. Caso 3D (preview grosseiro)

- [ ] `scramjet_coldflow_3d.yaml` (size_scale 2.2) completa
  geometry → mesh → case → run → post → metrics.
- [ ] Continuidade mássica do 3D dentro da mesma tolerância do 2D
  (a malha grosseira degrada resolução, não conservação).
- [ ] Indicadores globais (recovery, thrust proxy, M_exit) coerentes com o
  caso 2D (diferença < ~10%, esperada pela resolução).
- [ ] **GPU no pós**: `health` reporta `accel.backend=GPU` quando CuPy
  disponível; kernels `cell_extents`/`min_dist_to_polylines` devolvem os
  mesmos resultados que o fallback NumPy (tolerância < 1e-9).
- [ ] **Viz 3D na GUI**: modo WebGL2 renderiza partículas sem fallback;
  fallback geometry-only não quebra a cena em WebGL1.

## Registro

Para cada item, grave um comentário em `docs/VALIDATION.md` (ou num
`runs/validation/log.md`) com o valor numérico e a data.
