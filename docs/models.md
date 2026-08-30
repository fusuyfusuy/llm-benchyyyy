# Master Model List & Harness Configuration Guide

This document lists supported model identifiers, provider mappings, and reasoning/effort configuration flags across all supported benchmark harnesses.

---

## 1. Antigravity Harness (`antigravity`)

* **CLI Command**: `agy -p "{prompt}" --output-format json --dangerously-skip-permissions`
* **Model Flag**: `--model {model}`
* **Effort Flag**: `--effort <low|medium|high>` (also selectable directly via model IDs)
* **Configuration File**: [`engine/harness/configs.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/configs.py#L63-L74)

### Available Models (`agy models`)
| Model Identifier | Display Name | Built-in Effort Level |
| :--- | :--- | :--- |
| `gemini-3.7-flash-high` | Gemini 3.7 Flash (High) | High |
| `gemini-3.7-flash-medium` | Gemini 3.7 Flash (Medium) | Medium |
| `gemini-3.7-flash-low` | Gemini 3.7 Flash (Low) | Low |
| `gemini-3.6-flash-high` | Gemini 3.6 Flash (High) | High |
| `gemini-3.6-flash-medium` | Gemini 3.6 Flash (Medium) | Medium |
| `gemini-3.6-flash-low` | Gemini 3.6 Flash (Low) | Low |
| `gemini-3.5-flash-high` | Gemini 3.5 Flash (High) | High |
| `gemini-3.5-flash-medium` | Gemini 3.5 Flash (Medium) | Medium |
| `gemini-3.5-flash-low` | Gemini 3.5 Flash (Low) | Low |
| `gemini-3.1-pro-high` | Gemini 3.1 Pro (High) | High |
| `gemini-3.1-pro-low` | Gemini 3.1 Pro (Low) | Low |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 (Thinking) | Adaptive |
| `claude-opus-4-6-thinking` | Claude Opus 4.6 (Thinking) | Adaptive |
| `gpt-oss-120b-medium` | GPT-OSS 120B (Medium) | Medium |

---

## 2. Claude Code Harness (`claude-code`)

* **CLI Command**: `claude -p "{prompt}" --output-format json --dangerously-skip-permissions`
* **Model Flag**: `--model {model}`
* **Effort Flag**: `--effort <low|medium|high|xhigh|max>`
* **Configuration File**: [`engine/harness/configs.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/configs.py#L37-L48)

> **Important Domain Gotcha**: Use canonical model IDs like `claude-sonnet-5` or aliases. Do **not** use date suffixes such as `claude-sonnet-5-20260115`.

### Available Models & Aliases
| Model Identifier | Alias | Description |
| :--- | :--- | :--- |
| `claude-sonnet-5` | `sonnet` | Claude Sonnet 5 (Recommended general agent) |
| `claude-opus-5` | `opus` | Claude Opus 5 (Deep reasoning agent) |
| `claude-fable-5` | `fable` | Claude Fable 5 |
| `claude-haiku-4.5` | `haiku` | Claude Haiku 4.5 (High throughput) |

---

## 3. Pi Agent Harness (`pi-agent`)

* **CLI Command**: `pi -p "{prompt}" --mode json --no-session`
* **Model Flag**: `--model {model}`
* **Thinking / Effort Settings**:
  * Shorthand Suffix: `{model}:{level}` (e.g. `x-preview-f-free:high`, `sonnet:medium`)
  * CLI Flag: `--thinking <off|minimal|low|medium|high|xhigh>`
* **Configuration File**: [`engine/harness/configs.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/configs.py#L76-L95)

### Key Provider Models in Registry (`~/.pi/agent/models-store.json`)

#### OpenCode Provider
* `x-preview-f-free` (Ox Alpha Free / Unlimited)
* `hy3-free` (Hy3 Free)
* `mimo-v2.5-free` (MiMo V2.5 Free)
* `muse-spark-1.2-contributor-free` (Muse Spark 1.2 Free)
* `nemotron-3-ultra-free` (Nemotron 3 Ultra Free)
* `nemotron-3.5-lightning-free` (Nemotron 3.5 Lightning Free)
* `gpt-5.1-codex-max` (GPT-5.1 Codex Max)
* `gpt-5.1-codex-mini` (GPT-5.1 Codex Mini)
* `minimax-m2.5`, `minimax-m2.7`, `minimax-m3`
* `claude-sonnet-5`, `claude-opus-5`, `claude-fable-5`

#### OpenCode-Go Provider
* `ox-alpha-free` (Ox Alpha Free Unlimited)
* `deepseek-v4-flash` (DeepSeek V4 Flash)
* `deepseek-v4-pro` (DeepSeek V4 Pro)
* `glm-5.1`, `glm-5.2`, `glm-5.3`
* `gpt-5.6-luna`
* `kimi-k2.6`, `kimi-k2.7-code`, `kimi-k3`

#### OpenRouter Provider (Free & Key Endpoints)
* `openrouter/free` (Free Models Router)
* `openai/gpt-oss-20b:free`
* `cohere/north-mini-code:free`
* `dots-studio/dots-3-note-preview:free`
* `google/gemma-4-26b-a4b-it:free`, `google/gemma-4-31b-it:free`
* `liquid/lfm-2.5-2.6b:free`
* `nvidia/nemotron-3-nano-30b-a3b:free`
* `nvidia/nemotron-3-super-120b-a12b:free`
* `nvidia/nemotron-3-ultra-550b-a55b:free`
* `poolside/laguna-s-2.1:free`, `poolside/laguna-xs-2.1:free`
* `z-ai/glm-5.2:free`
* `x-ai/grok-4.20`, `x-ai/grok-4.3`, `x-ai/grok-4.5`, `x-ai/grok-4.6`
* `qwen/qwen3-max-thinking`, `qwen/qwen3.6-max-preview`

---

## 4. OpenCode Harness (`opencode`)

* **CLI Command**: `opencode run --format json "{prompt}"`
* **Model Flag**: `--model {model}` (Format: `provider/model`)
* **Configuration File**: [`engine/harness/configs.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/configs.py#L96-L110)

### Common Identifiers
* `opencode-go/deepseek-v4-flash`
* `opencode-go/deepseek-v4-pro`
* `opencode-go/muse-spark`
* `opencode-go/ox-alpha-free`
* `opencode-go/glm-5.3`
* `opencode-go/minimax-m3`

---

## 5. Codex CLI Harness (`codex-cli`)

* **CLI Command**: `codex exec --json --full-auto "{prompt}"`
* **Model Flag**: `--model {model}`
* **Configuration File**: [`engine/harness/configs.py`](file:///home/devhax/projects/fusuyfusuy/llm-benchyyyy/engine/harness/configs.py#L50-L62)

### Common Identifiers
* `gpt-5.1-codex-max`
* `gpt-5.1-codex-mini`
* `o3`
* `o4-mini`

---

## 6. Model Verification Cheat-Sheet

Before initiating large-scale benchmark runs, use `engine verify` to confirm API availability and container authentication:

```bash
# Verify Pi Agent (Ox Alpha Free)
python3 -m engine verify --harness pi-agent --model x-preview-f-free

# Verify Claude Code (Sonnet 5)
python3 -m engine verify --harness claude-code --model claude-sonnet-5

# Verify Antigravity (GPT-OSS 120B)
python3 -m engine verify --harness antigravity --model gpt-oss-120b-medium

# Verify OpenCode (DeepSeek V4 Flash)
python3 -m engine verify --harness opencode --model opencode-go/deepseek-v4-flash
```
