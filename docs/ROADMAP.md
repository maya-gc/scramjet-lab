# Roadmap de fidelidade

Evolução incremental; cada fase termina com um checkpoint validável e um
entrega mensurável. As interfaces (`configs/`, `backend/domain/`, `backend/application/pipeline.py`,
`backend/application/metrics.py`, `backend/application/optimizer.py`) foram
desenhadas para não mudar de forma entre fases.

## Fase 1 — Cold-flow 2D (entregue neste repositório)

- [x] Geometria paramétrica 2D (inlet + isolador + combustor/strut + bocal).
- [x] Malha Gmsh com camada limite (y+~1) e refinamento regional.
- [x] SU2 RANS steady (Euler -> RANS restart), gás ideal, SST, Sutherland.
- [x] Pipeline Python end-to-end + sweep + mesh study + SA.
- [x] Métricas: recovery, thrust proxy, mistura, separação, margem.
- [ ] **Checkpoint**: `docs/VALIDATION.md` itens 1-3 concluídos.

## Fase 2 — Cold-flow 3D (em progresso)

- [x] Caso 3D end-to-end no Gmsh + SU2 3D (malha grosseira via
  `size_scale` ~32k células p/ iteração rápida).
- [x] GUI com visualização 3D do canal (partículas de escoamento em WebGL2).
- [ ] Malha 3D plena (~307k células) com camada limite em volumes e
  efeito de sidewall BL.
- [ ] Métricas 3D: captação mássica 3D, espalhamento transversal do trem
  de choques.
- [ ] **Checkpoint**: comparação 2D x 3D (diferença de recovery < 10%).

## Fase 3 — Injeção de combustível (sem reação)

- Escalar a geometria do strut para um injetor (jatos transversais em
  cavidade ou strut) com mistura de espécies passivas.
- SU2 com espécies escalares (ou cantera acoplado); métrica `mixing`
  passa a usar fração de mistura e uma métrica de eficiência de mistura
  (perda de p0 devida ao jato).
- **Checkpoint**: perfil de fração de mistura na saída do combustor.

## Fase 4 — Combustão simplificada (modelo global)

- Química de 1-2 etapas (ex.: hidrogênio/ar global) acoplada ao solver
  RANS; ajuste da parede do combustor para acomodar descolamento térmico
  (thermal choking control).
- **Checkpoint**: distribuição de temperatura a jusante do injetor e
  `thrust_proxy` com liberação de calor (sinal físico correto).

## Fase 5 — Combustão com cinética reduzida / transferência térmica

- Mecanismo reduzido (ex.: 9 espécies / 19 reações H2) via acoplamento
  cantera; BCs térmicas (parede resfriada) e efeito de desvio de entrada.
- **Checkpoint**: ignição e estabilidade de chama em condições de voo.

## Fase 6 — Otimização e exploração de geometria

- Extensão do `optimization/anneal.py` para parametrização mais rica
  (curvas B-spline do bocal, posição/ângulo do injetor, cavidade) e
  exploração de trade-offs (recovery x mixing x thrust).
- Migração opcional para otimização gradiente com o adjoint do SU2.
- **Checkpoint**: pareto recovery x thrust com N>=100 avaliações.

## Alvos de extensão (pós-fase 6)

- FSI (acoplamento térmico-estrutural do revestimento), LES/URANS em
  regiões críticas, e acoplamento aerodinâmico de veículo (força externa
  na cowl/afterbody).
