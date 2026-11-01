# Provider validation

Text audit and TTFT evidence: [model priority](../../reports/model-priority.json), [stream benchmark](../../reports/stream-benchmark.txt). Existing 99 verified text credentials preserved, plus two auxiliary credentials that do not participate in translation.

| Default text order | Model | Text keys | Earlier median TTFT |
|---|---|---:|---:|
| Cloudflare | Llama 3.3 70B FP8 Fast | 1 | 0.338s |
| Cloudflare | Gemma 4 26B | 4 | 0.681s |
| Cloudflare | GLM 4.7 Flash | 18 | 0.818s |
| NVIDIA | Nemotron 3.5 Lightning 30B A3B | 21 | 0.552s |
| Ollama | Gemma4:31b-cloud | 19 | 0.607s |
| Google | Flash Lite / Flash | 3 / 11 | 0.824 / 0.880s |
| OpenRouter | Nemotron 3 Nano Omni :free | 22 | ~3.33s, one timeout |

Provider grouping is deliberate: exhaust keys/models in selected provider before moving on. Last successful verified pair is sticky across restart. Measurements were short samples on one credential per model, not guarantees for all keys.

Vision is a separate verified capability. Initial HTTP success was insufficient: source echo, bilingual output and wrong target were rejected. Revised one-language prompt passed English→Vietnamese, Vietnamese→English and mixed→Vietnamese on **Ollama Gemma4:31b-cloud** and **Cloudflare Gemma4 26B**. One key/model pair each is enabled for vision. Google Flash failed Vietnamese-only direction and is excluded. Median completed outputs favor Ollama; vision order Ollama→Cloudflare. Evidence: [Ollama](../../reports/native-vision-ollama-probe.json), [Cloudflare/Google](../../reports/native-vision-probe.json).

All runtime model requests disable thinking; incomplete/mandatory reasoning output is rejected. OpenRouter runtime permits only `:free`. No automatic paid model fallback. 5-second absolute whole-output budget per attempt, 30 seconds per task including fallback; 429/402 cooldown respects Retry-After and shared account identity where known.

Alt+C now uses **official Azure Translator standard NMT**, after explicit user acceptance of the F0 setup. No web/LLM fallback. Azure credentials are separate from text/vision candidates and bound to region; pending imports are excluded from runtime/export. Dashboard verifies a short synthetic request before save. The user supplied a working global resource key: real EN→VI, VI→EN and mixed→VI now pass (reports/azure-translator-live-verification.json). The key is active and included in the combined verified portable file. The key itself does not confirm pricing tier. Browser resource creation is blocked by a saved portal.azure.com origin permission; no resource/key or paid subscription was created. See azure-translator-setup.txt and reports/azure-translator-status.json. Historical Google/Bing probes describe the replaced default, not the current Alt+C route.

Private portable TXT contains only verified bindings/capabilities and auxiliary credentials. It is not part of the package. Invalid auth credentials remain quarantined in private audit backups, not active runtime export.
