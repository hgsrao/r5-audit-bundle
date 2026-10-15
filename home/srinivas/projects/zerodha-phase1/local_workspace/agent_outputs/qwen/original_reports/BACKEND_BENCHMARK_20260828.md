# Ollama Backend Benchmark — 2026-08-28

## Standardized workload

- File selection: `DIR_SPEC.md:1-80` (the file contained 25 lines, so both runs ingested the identical `DIR_SPEC.md#L1-L25` content)
- Input SHA-256: `c69d519ea5d146cb526f971d616c4fc563ebc3a20e0e996fbd234553d939c642`
- Task: exactly five concise numbered findings, without introduction or conclusion
- Runner settings: 16,384 context, temperature 0.1, maximum 2,048 generated tokens
- Execution order: desktop first, Razer second

## Results

| Backend | Model | Wall time | Prompt tokens/s | Output tokens/s | Prompt tokens | Output tokens |
|---|---|---:|---:|---:|---:|---:|
| desktop | `qwen3-coder:30b` Q4_K_M | 24.34 s | 137.68 | **29.76** | 445 | 141 |
| razer | `codellama:13b-instruct` Q4_0 | 201.66 s | 133.03 | **2.32** | 622 | 335 |
| razer | `qwen3-coder:30b` Q4_K_M | 212.26 s | 4.07 | **8.91** | 445 | 140 |

Prompt/output token counts are tokenizer-dependent and therefore are not expected to match across model families. The file bytes, task text, context setting, temperature, and output ceiling were identical.

## Processor-placement verification

Placement was queried from each server's `/api/ps` endpoint with the model loaded at a 16,384-token context.

| Backend | Loaded allocation | Reported VRAM | Approximate VRAM share | Full VRAM offload verified? |
|---|---:|---:|---:|---|
| desktop | 20.44 GB | 15.12 GB | 74.0% | **No** |
| razer | 21.39 GB | 4.29 GB | 20.0% | **No** |
| razer (Qwen) | 20.44 GB | 4.37 GB | 21.4% | **No** |

The allocation figures include model/runtime context allocation and are not the on-disk model sizes. Ollama's reported `size_vram` is the evidence used here; no inference about GPU placement is made from model file size alone.

## Engineering decision

- Keep `desktop` as the default backend for substantive project review.
- Do not automatically route heavyweight work to `razer` under the present configuration. Razer Qwen was about **3.34 times slower** than desktop Qwen (`29.76 / 8.91`), while Razer CodeLlama was about **12.8 times slower** than desktop Qwen (`29.76 / 2.32`).
- Treat the Razer backend as available but experimental until its GPU backend/driver configuration is corrected and `/api/ps` reports full placement.
- Re-run this exact benchmark after any Razer GPU configuration change. Record a new dated result rather than overwriting this baseline.

Source reports:

- Desktop: `review_report_20260828_174430.md`
- Razer: `review_report_20260828_174757.md`
- Razer Qwen: `review_report_20260828_182138.md`
