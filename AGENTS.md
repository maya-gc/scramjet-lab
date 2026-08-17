# scramjet-lab — agent guidance

## Repo layout
- `backend/` — Python CFD toolkit. IMPORTANT: the Electron UI only talks to it
  through `backend/interfaces/api.py` over the localhost RPC server
  `backend/interfaces/server.py`. Do not import backend internals from the UI.
- `ui/` — Electron + React + TypeScript desktop app (control panel).
- `configs/cases/*.yaml` — test cases; the UI lists these via `list_cases`.

## Commands

Backend (no SOLVER needed — SU2 optional):
```powershell
python run_sim.py --case configs/cases/scramjet_coldflow.yaml --steps geometry,mesh
python tests/test_pipeline.py
```

Electron UI (from `ui/`):
```powershell
npm.cmd install        # first time; .npmrc auto-approves postinstall scripts
npm.cmd run dev        # electron-vite dev server (HMR)
npm.cmd run typecheck  # tsc for main/preload + renderer
npm.cmd run build      # electron-vite production build -> ui/out
```
Note: use `npm.cmd` (npm.ps1 is blocked by the PowerShell execution policy).
On Windows, PowerShell + `Start-Process` smoke-launches best with
`taskkill /PID <pid> /T /F` to clean up the python child server.

## Backend RPC server
- Run manually: `python -m backend.interfaces.server` (127.0.0.1, prints
  `SCRAMJET_SERVER_URL=` and `SCRAMJET_TOKEN=` to stdout).
- The Electron main process spawns it; repo root is discovered by walking up
  from the ui dir for a folder containing both `backend/` and `configs/`
  (or env `SCRAMJET_HOME`).
- Long methods (`run_case`, `render_*`) are subprocess jobs polled via
  `job_status`; progress comes from real workdir artifacts + SU2 log parsing.

## Validation contract (authoritative)
`backend/domain/config.py::validate` enforces: contraction_ratio > 1;
intake_angle_deg in (1,20); isolator/combustor/nozzle lengths > 0;
nozzle_expansion_ratio >= 1; mach > 1; strut_height < capture_height/CR.
The UI mirrors these via `validate` RPC — never hardcode different bounds.

## Editor conventions
- Param metadata lives in `ui/src/renderer/src/lib/paramMeta.ts`; bounds set
  there are UI suggestions for sliders only — backend validation wins.
- Design system: tokens in `ui/src/renderer/src/styles/tokens.css`,
  components.css (primitives), app.css (shell). Dark engineering theme,
  accent cyan; micro-interactions via framer-motion; respect reduced motion.
- 3D scene (`ui/src/renderer/src/three/`): two view modes —
  `extruded` (current duct builder/flow) and `annular`
  (`annular.ts`, replicates `crosssection_vectors.gif`: axisymmetric
  cowl/centerbody/plug/rings revolned around the nacelle axis). The annular
  annulus radius constant is `ANNUAR_R0 = 0.05` m — keep it identical to
  `backend/infrastructure/viz.py::R0`; marker rings sit at the derived keys
  `x_inlet_end`, `x_strut`, `x_combustor_end` (same positions the gif uses).

## CUDA / GPU acceleration (both sides)
- **3D viz (WebGL2, GLSL3)**: `ui/src/renderer/src/three/gpu.ts` renders the
  flow particles entirely on the GPU (vertex-shader textures + `gl_VertexID`,
  no per-frame CPU particle loops). Requires WebGL2 — `engine.ts` falls back
  to geometry-only when `renderer.capabilities.isWebGL2` is false. three.js
  GLSL3 auto-injects `#version 300 es`/precision/`position`; never redeclare
  them in the shader strings. Shared interpolant code: `three/interp.ts`.
- **Backend post-processing (CuPy optional, numpy fallback)**:
  `backend/infrastructure/accel.py` owns the only cupy import. Kernels
  (`cell_extents` for station integrals, `min_dist_to_polylines` for
  wall/separation metrics) accept/return numpy arrays and prefer a GPU
  scatter when `import cupy` works. The numpy fallback avoids `np.minimum.at`
  (sort + `reduceat`) — keep that. Health RPC (`health`) exposes
  `accel.{backend,gpu}`; the Header shows a GPU/CPU badge from it.
- **SU2 CUDA solver**: SU2 must be built with CUDA separately (upstream
  `meson`/CMake build with `-Denable-cuda=true`). The UI's Header has a
  "SU2 solver exe (CUDA build)" field — persisted in localStorage as
  `scramjet.solverExe`, forwarded as `solver_exe` through `run_case` →
  `_jobworker` → `run_experiment`/`run_case_stages`. Leave blank to let
  `su2.find_solver` discover the default solver.
- **3D solver is deliberately coarse**: the full-fidelity 3D mesh (~307k
  cells) runs at ~0.21 s/iter single-threaded and takes ~30+ min for 5000
  iters. `configs/cases/scramjet_coldflow_3d.yaml` sets `mesh.size_scale:
  2.2`, which scales every isotropic size field (`h_*`, `h_far`,
  `bl_thickness`) and yields a ~32k-cell preview mesh (~5-8x faster,
  ~8 min for both RANS stages). Keep `size_scale` in the 3D case; the 2D
  case stays at the default `1.0`. `size_scale` lives on `MeshParams`
  (`backend/domain/config.py`) and is applied in
  `backend/infrastructure/meshing.py::_apply_fields_2d/3d`.
- **SU2-CUDA is BROKEN — do not use**: we built SU2 8.5.0 with CUDA 13.1
  (MSVC 19.44, `sm_120`). With `ENABLE_CUDA= YES` the RANS case diverges
  (NaN) after ~30 iters with both ILU and JACOBI preconditioners, and EULER
  converges but at ~21 s/iter (no GPU speedup; SU2's CUDA is immature on
  Windows/Blackwell — see su2code/SU2 discussion #1409). The default CPU
  solver (resolved by `su2.find_solver`, e.g. `%SU2_HOME%\bin\SU2_CFD.exe`)
  is reliable. Do not point the UI solver-exe field at a CUDA-built
  `SU2_CFD.exe`.
- **MSVC OpenMP note**: SU2's `-Dwith-omp=true` fails on MSVC 19.4x
  (`C3016`: `omp for` loop indices must be signed; SU2 uses `unsigned
  long`). A multi-threaded SU2 would need clang-cl (LLVM) as the host
  compiler.