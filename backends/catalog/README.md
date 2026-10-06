# 供应商的对照表与价目（外层 #266）

数据从 [cc-switch](https://github.com/farion1231/cc-switch)（MIT）搬，一直跟着它维护：

| 文件 | 是什么 | 从 cc-switch 哪里来 | 怎么更新 |
|---|---|---|---|
| `prices.json` | 模型价目：美元 / 百万 token（输入、命中缓存、输出） | `src-tauri/src/database/schema.rs` 的 `seed_model_pricing` | 外层 `python3 scripts/sync-provider-prices.py <cc-switch> --apply`；加模型带 `--add <id>` |
| `codex-deepseek.json` | Codex 接 DeepSeek 时的模型说明（`model_catalog_json`）：工具怎么调、上下文多长、思考档 | `src-tauri/src/resources/codex_deepseek_catalog_template.json`（DeepSeek 官方 models.json 的镜像），原样 | 照搬覆盖 |
| `codex-kimi.json` | Codex 接 Kimi 时的模型说明 | `codex_native_responses_template.json` 填上 `src/config/codexProviderPresets.ts` 里 Kimi 预设的 kimi-k3（1M 窗口、并行工具调用、low / high / max） | 照预设重填 |

各家的接口地址、怎么交 key、有哪些模型在两家适配器的 `PROVIDERS` 里（`backends/claude_code.py`、`backends/codex.py`），照 cc-switch 的 `src/config/claudeProviderPresets.ts`、`codexProviderPresets.ts`。不是 Codex 自家的模型不给模型说明，Codex 就不知道这些模型怎么调工具——所以第三方都带一份。
