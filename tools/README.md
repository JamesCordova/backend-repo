# axial-tools

Herramientas de la tesis, separadas del backend (proyecto `uv` propio, no
agregan dependencias al servicio):

| Modulo | Para que | Plan |
| --- | --- | --- |
| `axial_tools.phantoms` | Volumenes sinteticos con geometria conocida en mm (NIfTI, DICOM, RAW) y sus defectos | C |
| `axial_tools.reference` | Lecturas de referencia **independientes** (nibabel, pydicom, numpy; nunca SimpleITK) | C |
| `axial_tools.run_bench` | Corre la matriz volumen x LOD x modo x configuracion con Playwright en un navegador real | B.4 |
| `axial_tools.ssim` | SSIM de cada captura frente a REF | B.5 |
| `axial_tools.stats` | Tablas 13/14: FPS, carga, SSIM, Friedman + Wilcoxon/Holm, hipotesis | B.5 |

```bash
cd backend-repo/tools
uv sync --extra dev
uv run pytest            # 19 tests: fantasmas leidos de vuelta + estadistica con datos conocidos
uv run ruff check src tests
```

## 1. Fantasmas (C)

```bash
uv run axial-phantoms --out out/phantoms                                   # todo (NIfTI + DICOM + RAW)
uv run axial-phantoms --out ../../volume-renderer-ts/public/phantoms --nifti-only   # para el frontend
```

Las formas se definen en RAS+ (mm) y se rasterizan sobre cualquier grilla, asi
que el mismo objeto sale como NIfTI con distintas orientaciones de
almacenamiento, como serie DICOM (axial o sagital) y como RAW. `manifest.json`
dice para que caso sirve cada archivo y que se espera:

| Archivo | Caso |
| --- | --- |
| `geometrico_aniso.nii.gz` (esfera r = 40 mm, cubo 50 mm, voxel 0,7 x 0,7 x 2,5) | CP-F01, CP-R01 |
| `marcadores_{ras,lps,sagital}.nii.gz` (esfera a la derecha, cubo anterior, cilindro superior) | CP-F10, CP-R02 (las tres deben verse identicas) |
| `nifti_scl.nii.gz` (scl_slope 2, scl_inter -1024) | CP-F03 |
| `nifti_cabecera_danada.nii`, `nifti_truncado.nii.gz` | CP-F02 |
| `dicom/geometrico_axial`, `dicom/marcadores_{axial,sagital}` (sin signo + RescaleIntercept -1024) | CP-F04, CP-F06, CP-F10 |
| `dicom/corte_faltante`, `dicom/espaciado_no_uniforme`, `dicom/cortes_duplicados` | CP-F05 |
| `dicom/mezcla_series`, `dicom/no_ct` | validacion de serie |
| `raw_geometrico_int16_le.raw`, `raw_tamano_incorrecto.raw`, `raw_int16_big_endian.raw` | CP-F07, CP-F08, CP-F09 |
| `torso_{preview,full}.nii.gz` (4 mm / 1 mm, ~24 M voxeles) | probar el arnes sin datos reales (no es anatomico) |

Las salidas van a carpetas ignoradas por git; el script se versiona para que
sean reproducibles. Los tests (`tests/test_phantoms.py`) verifican cada
archivo con las referencias independientes (volumen de la esfera, centroides
de los marcadores en RAS en las tres orientaciones, DICOM == NIfTI voxel a
voxel, defectos realmente presentes).

**Pendiente (E):** convertir los CP-F en tests del monolito
(`tests/validation/test_cp_f*.py`) que corran la canalizacion real sobre estos
fantasmas. Depende de las decisiones abiertas del plan (int16 HU, rechazar o
remuestrear DICOM no uniforme, NIfTI 4D) y de la subida de NIfTI.

## 2. Mediciones (B)

### Requisitos de la maquina

- Frontend servido (`pnpm dev` o `pnpm build && pnpm preview`) y, para
  estudios del backend, el monolito corriendo.
- Navegador **real con ventana** (el script usa `headless=False`). Edge/Chrome
  se usan instalados (`channel`); para Firefox: `uv run playwright install firefox`.
- GPU elegida a mano en *Configuracion > Pantalla > Graficos* de Windows para
  el ejecutable del navegador (perfil A = integrada, B = dedicada). Cada JSON
  guarda `meta.gpu.renderer` (UNMASKED_RENDERER_WEBGL): es la evidencia; el
  script avisa si ve un renderer por software (SwiftShader).
- Corriente conectada, modo de alto rendimiento, sin otras aplicaciones.

### Plan y corrida

```jsonc
// bench_plan.json
{
  "base_url": "http://localhost:5173/",
  "api_url": "http://localhost:8000",
  "volumes": [
    {"key": "cabeza", "study": "<uuid>", "lods": ["preview", "full"]},
    {"key": "torax",  "study": "<uuid>", "lods": ["preview", "full"]},
    {"key": "abdomen", "study": "<uuid>", "lods": ["preview", "full"]}
  ],
  "modes": ["load", "fps", "capture"],
  "fps_configs": ["C0", "C1", "C2", "C3", "C4", "C3@1", "C3@2"],
  "fps_reps": 5,
  "load_visits": 10,
  "load_warm": 1,
  "capture_configs": "REF,C0,C1,C2,C3,C4,C3@1,C3@2"
}
```

```bash
uv run axial-bench bench_plan.json --browser msedge --profile A --out results/2026-12-01 \
    --email profe@unsa.edu.pe --password ...      # o --token / AXIAL_TOKEN
uv run axial-bench bench_plan.json --browser chrome --profile A --out results/2026-12-01 --only-mode fps
uv run axial-stats results/2026-12-01             # -> results/2026-12-01/analisis/*.csv
```

`--skip-existing` permite retomar una corrida cortada. Para volumenes locales
(sin backend) usar `{"key": ..., "url": "phantoms/x.nii.gz", "lod": "preview"}`.

### Que mide exactamente

- **Carga**: marcas `solicitud -> descargado -> parseado -> textura_subida ->
  primer_fotograma` (el ultimo con sincronizacion de GPU). Cada visita es una
  pagina nueva con 1 carga en frio (`cache: 'no-store'`) + `load_warm` en
  caliente; el analisis descarta la primera visita de cada condicion.
  `bytes` = tamano del `.nii.gz` recibido (es el cuerpo codificado, porque el
  backend sirve el archivo tal cual). `transferSize` de Resource Timing solo
  es distinto de 0 si el backend envia `Timing-Allow-Origin` (origen cruzado).
- **FPS**: trayectoria determinista por tiempo (360° en 20 s + acercamiento y
  alejamiento en 10 s), canvas 1280 x 720 con `pixelRatio` 1, fondo negro,
  2 s de calentamiento descartados tras compilar. **Cada fotograma se
  sincroniza con la GPU** (`readPixels` de 1 pixel): sin vsync, el navegador
  encola fotogramas sin esperar a la GPU, el "FPS" pasa a medir solo el envio
  de comandos (~1000 FPS falsos) y la cola termina en un TDR (contexto WebGL
  perdido) -- verificado en Edge con GPU Intel. Durante la trayectoria la app
  se considera "interactuando" (C4 usa Δs = 2).
- **SSIM**: 3 vistas fijas (`volume-renderer-ts/public/bench/views.json`),
  render 1024 x 1024 en reposo (C4 con Δs = 0,5) a un render target, en
  mosaicos de 256 x 256 con sincronizacion por mosaico (la referencia con
  Δs = 0,25 no dispara el TDR). SSIM sobre RGB, ventana uniforme 7 x 7,
  `data_range` 255 (decision fija).

### Estadistica (`axial_tools.stats`)

- Por condicion (volumen x lod x navegador x perfil x config): FPS medio
  (fotogramas / tiempo total), **mediana de FPS** (de los FPS por fotograma,
  juntando las repeticiones; es la que usa la hipotesis), percentil 1 de FPS y
  percentil 99 del tiempo de fotograma (`fps_p1` ≈ 1000 / `frame_ms_p99`),
  minimo, y la mediana/RIC/IC 95 % (bootstrap percentil, 10 000 remuestreos,
  semilla fija) de las medianas por repeticion. Cambio % de la mediana frente
  a C0 de la misma condicion.
- Friedman entre C0..C4 con bloques = (volumen, lod, navegador, perfil,
  repeticion) -- global y por (lod, perfil); Wilcoxon por pares con Holm
  (alfa 0,05). Igual entre navegadores (bloques = volumen, lod, perfil,
  config, repeticion). Con 5 repeticiones el analisis es exploratorio.
- `hipotesis.csv`: mediana FPS de C4 >= 30 en (preview, perfil A) y (full,
  perfil B), y SSIM de C4 >= 0,85 en todas las vistas.
