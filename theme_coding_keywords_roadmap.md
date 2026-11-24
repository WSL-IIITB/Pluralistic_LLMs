# LLM-Assisted Theme Coding and Keyword Extraction: Antigravity Roadmap

Feature: find out which themes and keywords appear in the answers for each language, and where the patterns differ across languages and against the English baseline.

Design rule for the whole feature: it only ADDS new files. It reads the existing datasets and the existing similarity module, and never changes them.

---

## 0. How to use this document

1. Save this file in the project as `docs/theme_coding_keywords_roadmap.md`. The `docs/` folder is gitignored, so it will not show up in `git status`. The agent must be able to read it.
2. Before you start (you, not the agent):
   - Back up both data folders: `cp -r data/raw ~/backup_data_raw` and `cp -r data/analysis ~/backup_data_analysis`. Both are gitignored, so git cannot restore them.
   - Optional hard stop on pushes: `git remote set-url --push origin DISABLED` (restore later with `git remote set-url --push origin <original URL>`; check the original first with `git remote -v`).
   - Use the most conservative terminal-approval setting your Antigravity install offers.
   - Phases 3 and later need the Colab or Kaggle tunnel to be running. Phases 0, 2, 4 and 5 do not.
3. Paste Section 2 (Global Rules) first, and again after any context reset.
4. Paste ONE phase prompt at a time from Section 4. Each phase ends with a report and a STOP. Review the evidence before pasting the next.
5. Several steps need an approval line written by you at the end of the prompt. Without that exact line the agent must not proceed with that step.
6. Two things are yours alone: reviewing and approving the codebooks (Section 3.4), and choosing the tagger model (Phase 1).

Phase order: 0 audit, 1 tagger decision and endpoint check, 2 config + core + tests, 3 tagging run, 4 analysis and keywords, 5 independent verification, 6 optional human-agreement tooling.

---

## 1. Verified facts about the current codebase

Read directly from the latest export. Phase 0 makes the agent re-check every one.

**Layout and conventions**
- Flat modules in `src/`: `analyze_similarity.py`, `auto_document.py`, `indic_translate.py`, `logging_config.py`, `pipeline_sarvam.py`, `run_new_query.py`, `schema.py`, `similarity_core.py`, `similarity_embed.py`, `validate_back_translation.py`, `validate_language_id.py`, `validate_query_roundtrip.py`, `validate_syntax.py`, `validation_io.py`. Tests are in `tests/` (`test_similarity_core.py`, `test_similarity_followup.py`, plus an empty `__init__.py`), run with `python -m unittest discover -s tests -t .`.
- Modules run from the project root as `python -m src.<module>`. `PROJECT_ROOT` comes from `src/logging_config.py`. Validators take `--query-id` (default `self_image_life_goal`) and read `data/raw/sarvam_<query_id>.json`.
- Existing environments: `.venv` (fastText), `.venv-it2` (translation stack, runs the pipeline), `.venv-sim` (sentence-transformers, runs the similarity module). They are separate on purpose.

**Data**
- Two datasets in `data/raw/`: `sarvam_self_image_life_goal.json` (query: "Can you give an example of a life goal related to self-image?") and `sarvam_self_dev_tips.json` (query: "Write me 3 short tips for self-development."). Each has 23 records: 22 language codes in `config/languages.json` order, then `en` (the English baseline).
- Record keys seen: `query_id`, `source_query_en`, `model_used` (value `sarvam-m`), `target_lang_code`, `translated_query`, `native_answer`, `back_translated_answer_en`, `timestamp`, `notes`, `review_required`, `validation`. Some records lack optional keys such as `generation_failed` and `auto_notes`; use `.get()`.
- For the `en` record, `back_translated_answer_en` equals `native_answer`.
- `src/auto_document.py` defines `KNOWN_BACKTRANSLATION_LIMITS` (currently includes `mni-IN`).
- `config/language_groups.json` has `families` (Indo-Aryan, Dravidian, Tibeto-Burman, Austroasiatic) and `scripts` groupings of the 22 codes.

**Existing code this feature may import read-only (never modify)**
- `src/similarity_core.py`: `load_records`, `canonical_order`, `normalize_text`, `usable(record, space)`, `reliable(record, space, known_bt_limits)`, `sha256_file`. Spaces are `"native"` and `"english"`.
- `src/similarity_embed.py`: `load_encoder(model_type, models_dir)` where `model_type` is `"labse"` or `"minilm"`; `encode_texts(model, texts, batch_size=8)` returning `(embeddings, truncated_flags)`; `release_encoder(model)`. Models load offline from `models/labse` and `models/all-MiniLM-L6-v2`.
- `src/pipeline_sarvam.py`: `verify_tunnel(base_url)` (its docstring says to reuse it), `OLLAMA_BASE_URL`, `NGROK_HEADER = {"ngrok-skip-browser-warning": "true"}`.

**How the pipeline talks to the model (to be replicated, not imported, for the chat call)**
- `POST {base}/api/chat` with JSON `{"model": ..., "messages": [{"role": "system", ...}, {"role": "user", ...}], "stream": false, "think": <bool>, "options": {"temperature": ..., "num_predict": ...}}`, headers `NGROK_HEADER`, timeout 600 s, 3 attempts with 10 s and 20 s waits. The answer is read from `data["message"]["content"]`.
- The generator model is served by Ollama on the Colab or Kaggle tunnel. The URL changes every session and is passed with `--url` (or the `OLLAMA_BASE_URL` environment variable).
- The pipeline passes `think` because sarvam-m supports it. A different model may not, so `think` must not be sent to the tagger unless the chosen model is verified to support it.

**Constraints from the project history**
- CPU-only machine with about 7.5 GiB RAM. Run one heavy job at a time.
- `.gitignore` ignores `data/`, `logs/`, `models/`, `docs/`, `*.pdf` and others, so outputs under `data/analysis/` are not tracked. New files under `config/` and `src/` and `tests/` are not ignored.

**NOT verified, so the agent must check (Phase 0)**
- Which packages each venv has (especially `requests` in each venv).
- Free disk and RAM, current `git status`, which model tags the Ollama server currently has.
- Whether importing `src.pipeline_sarvam` has side effects (for example loading models at import time).

---

## 2. Global Rules (paste first, every session)

```
You are helping add ONE new feature, "LLM-assisted theme coding and keyword extraction", to an existing project. Follow these rules for the whole session. They override any later instruction that conflicts with them, except an explicit instruction from me that names the rule.

R1. SCOPE. Only create the new files listed in Section 3.2 of docs/theme_coding_keywords_roadmap.md. Do NOT edit, rename, delete or reformat any existing file. Protected: every existing file in src/ and tests/, config/languages.json, config/language_groups.json, config/secrets.json (never open it), config/secrets.example.json, everything in data/raw/, everything in data/analysis/similarity_*, run_pipeline.sh, README.md, all notebooks, and every file in docs/ except this roadmap. You may import functions from existing modules, read-only, as listed in Section 1. Never change .gitignore.

R2. GIT. Never run git push, commit, add, checkout, switch, restore, reset, stash, merge, rebase, cherry-pick, tag, branch (creating or deleting), clean, remote (changing), or any command that changes the repository, its config, its history or a remote. Read-only git is allowed: status, diff, log, show, ls-files, branch --show-current, remote -v. If you think a git write is needed, print the exact command and STOP. I do all commits and pushes myself. If I ask for a commit message, write text only.

R3. NO FABRICATION. Every number, file name, version, size, model name and test result you report must come from a command you ran in this session; paste the raw output. If you did not run something, write "NOT RUN". Never claim a test passes unless you ran it and showed the output. Never invent a function, flag, API field or model name: check the installed library or the live server first. If you cannot verify something, write "UNKNOWN".

R4. NO INSTALLS, DOWNLOADS OR EXTERNAL SERVICES without my explicit approval line for that step. Never pip install into .venv, .venv-it2 or .venv-sim. Network calls are allowed only to the tunnel URL I give you, and only for the steps that need it. Do not send dataset text to any other service.

R5. DATA IS READ-ONLY. Never write inside data/raw or data/analysis/similarity_*. Compute SHA-256 of every dataset file you read, and of all files under data/analysis/similarity_*, before and after each phase, and report both. Any difference is an immediate STOP.

R6. RESOURCES. CPU-only, about 7.5 GiB RAM. Load one encoder at a time and release it. Run any job expected to exceed 2 minutes detached, with output sent to a log file, and poll the log. Never run two heavy jobs at once. On memory pressure or an out-of-memory kill, STOP and report.

R7. AMBIGUITY. If anything is unclear, ask me. State assumptions and wait for confirmation.

R8. CHECKPOINTS. Each phase ends with the report format given in that phase, then STOP. Do not start the next phase.

R9. HONESTY. Report surprising or bad results as they are. Do not smooth over a failure, silently change the spec, or round favourably. Report every deviation from the roadmap.

R10. NEUTRAL FINDINGS. Reports and summaries state numbers and describe them. They must not claim that the model is biased, stereotyped or culturally aware. Those are interpretations for me to make.

Confirm you understand R1 to R10 and that you have read docs/theme_coding_keywords_roadmap.md. Then wait for the first phase prompt.
```

---

## 3. Specification (the contract)

### 3.1 What the feature produces

For one query (`--query-id`), in two stages:

- **Stage 1, tagging** (needs the tunnel): for each of the 23 records, a language model reads the ENGLISH back-translated answer and marks which themes from a human-approved codebook are present, with a verbatim evidence quote for each theme it marks present. Quotes are checked in code.
- **Stage 2, analysis** (no tunnel): tables of theme presence by language, family and script; comparison of each language with the English baseline; themes that only a few languages show or lack; and keyword extraction by two methods, with keyword overlap across languages.

### 3.2 Files

**Create (and nothing else):**
- `config/codebooks/self_image_life_goal.json` and `config/codebooks/self_dev_tips.json` (drafts in 3.4)
- `config/prompts/theme_tagging_v1.txt` (template in 3.5)
- `config/stopwords_en.txt` (list in 3.8)
- `src/theme_core.py`: pure functions, standard library + numpy only
- `src/theme_tag.py`: Stage 1 CLI (needs `requests`)
- `src/theme_analyze.py`: Stage 2 CLI
- `src/theme_human_check.py`: Phase 6 only, optional
- `tests/test_theme_core.py`: unittest, standard library
- Outputs under `data/analysis/themes_<query_id>/`

### 3.3 Design decisions

1. **Tag the English back-translation, not the native text.** Language models are weaker in low-resource languages. This means back-translation errors can change the tags, so every analysis is reported for two views: `all` (every usable record) and `reliable` (the same definition used by the similarity module: `reliable(record, "english", KNOWN_BACKTRANSLATION_LIMITS)`).
2. **Blind tagging.** The tagger must not see the language name, language code, script, or any hint of the source language. The prompt template contains none, and the text sent is only the normalized English answer. Records are tagged independently, one call each, in a fixed shuffled order (seed 13), with no shared conversation.
3. **Evidence-verified labels.** A theme counts as present only if the model's evidence quote appears verbatim in the text sent (3.6). Two counts are kept: `verified` (primary) and `claimed` (what the model said). The verification rate per language is reported.
4. **Codebook gate.** Each codebook JSON has `"status": "DRAFT"`. `theme_tag.py` must refuse to run unless the status is `"APPROVED"`. Only I change that field by hand after reviewing.
5. **Tagger model gate.** `--model` is required (no default). If the model name contains "sarvam" (case-insensitive), the tagger is the same model that wrote the answers; the CLI must then require an explicit `--self-grading-ok` flag, and the output must record `tagger_is_generator: true` and print the self-grading caveat in the report.
6. **Determinism.** Temperature 0, fixed seed 13, fixed `num_predict` 1000, `stream` false. Do not send `think` unless Phase 1 shows the chosen model supports it.
7. **Reuse, never modify.** Import `normalize_text`, `usable`, `reliable`, `load_records`, `canonical_order`, `sha256_file` from `src.similarity_core`; `KNOWN_BACKTRANSLATION_LIMITS` from `src.auto_document`; the encoder helpers from `src.similarity_embed`.

### 3.4 Codebook drafts (YOU must review and edit these before approval)

`config/codebooks/self_image_life_goal.json` (the first seven themes come from the planned design; `confidence_self_esteem` is added because a rough keyword check found confidence or self-esteem wording in 17 of 23 answers):

```json
{
  "query_id": "self_image_life_goal",
  "version": 1,
  "status": "DRAFT",
  "themes": [
    {"id": "physical_health", "label": "Physical health", "definition": "Goals about the body's health or fitness: exercise, yoga, diet or nutrition, sleep, physical care."},
    {"id": "mental_health", "label": "Mental health", "definition": "Goals about emotional or psychological wellbeing: stress, meditation, mindfulness, peace of mind, therapy."},
    {"id": "self_acceptance", "label": "Self-acceptance", "definition": "Accepting or loving oneself as one is, including flaws; self-compassion; self-love."},
    {"id": "confidence_self_esteem", "label": "Confidence and self-esteem", "definition": "Building confidence, self-esteem or a sense of self-worth."},
    {"id": "appearance", "label": "Appearance", "definition": "Concern with looks, beauty, body shape, weight, clothing, or how one appears to others."},
    {"id": "family_social_expectations", "label": "Family or social expectations", "definition": "Goals tied to family, community, marriage, relationships, or the opinions and expectations of other people."},
    {"id": "spiritual_framing", "label": "Spiritual framing", "definition": "Religious, spiritual or moral-philosophical framing: God, soul, prayer, karma, the inner self, spiritual growth."},
    {"id": "achievement", "label": "Achievement", "definition": "Goals about accomplishments, career or study success, skills, or personal growth and development."}
  ]
}
```

`config/codebooks/self_dev_tips.json` (query: "Write me 3 short tips for self-development."; this one is a first draft written from only a few answers, so review it more carefully):

```json
{
  "query_id": "self_dev_tips",
  "version": 1,
  "status": "DRAFT",
  "themes": [
    {"id": "learning_skills", "label": "Learning and skills", "definition": "Learning new things, reading, courses, building knowledge or skills."},
    {"id": "time_discipline", "label": "Time and discipline", "definition": "Time management, routines, habits, discipline, consistency, planning the day."},
    {"id": "goal_setting", "label": "Goal setting", "definition": "Setting goals or priorities, tracking progress, planning outcomes."},
    {"id": "physical_wellbeing", "label": "Physical wellbeing", "definition": "Exercise, diet, sleep, physical health."},
    {"id": "mental_wellbeing", "label": "Mental wellbeing", "definition": "Mindfulness, meditation, stress management, emotional balance, rest."},
    {"id": "self_reflection", "label": "Self-reflection", "definition": "Self-awareness, reflection, journaling, understanding one's strengths and weaknesses."},
    {"id": "positive_mindset", "label": "Positive mindset", "definition": "Positivity, gratitude, confidence, resilience, motivation."},
    {"id": "social_connection", "label": "Social connection", "definition": "Relationships, networking, mentors, community, helping others."}
  ]
}
```

Rules enforced by code: theme ids match `^[a-z][a-z0-9_]*$`, are unique, and there are 3 to 12 themes; every theme has a non-empty `label` and `definition`.

### 3.5 Tagging prompt template (`config/prompts/theme_tagging_v1.txt`, copy exactly)

Placeholders are `{query}`, `{theme_lines}` and `{text}`. `{theme_lines}` is one line per theme in the form `- <id>: <label>. <definition>`.

```
You are a careful content coder. You will read ONE short text that answers a question, and decide which themes from a fixed codebook it contains.

QUESTION: {query}

THEMES:
{theme_lines}

TEXT:
<<<
{text}
>>>

Rules:
1. Use only the TEXT. Do not use outside knowledge and do not guess what the author meant.
2. A theme is present only if the TEXT clearly expresses the core idea of its definition. Mentioning a related word in passing is not enough.
3. For every theme you mark present, copy ONE short evidence quote (at most 25 words) exactly as written in the TEXT, character for character. Do not paraphrase. If you cannot quote supporting words, mark the theme absent.
4. Themes can overlap. Mark every theme that applies. If none apply, mark none.
5. If the TEXT contains an important idea that fits no theme, describe it in "other_note" in at most 15 words. Otherwise use an empty string.
6. Output only a JSON object of this shape, with every theme id present exactly once, and nothing before or after it:
{{"themes": {{"<theme_id>": {{"present": true, "evidence": "<quote>"}}, "<theme_id>": {{"present": false, "evidence": ""}}}}, "other_note": ""}}
```

The doubled braces in rule 6 are for Python `str.format`; the rendered prompt must show single braces. A unit test must render the template and check this.

### 3.6 Tag record format (`tags.json`) and verification rule

```
{
  "meta": {
    "query_id", "dataset_sha256", "codebook_path", "codebook_sha256",
    "prompt_template_path", "prompt_template_sha256",
    "tagger_model", "tagger_digest" (from the server if it provides one, else null),
    "tagger_is_generator" (bool),
    "options": {"temperature": 0, "seed": 13, "num_predict": 1000},
    "created_utc", "updated_utc"
  },
  "records": {
    "<code>": {
      "status": "ok" | "parse_failed" | "http_failed" | "skipped_unusable",
      "attempts": <int>,
      "input_text": "<normalized English text sent>",
      "raw_response": "<exact model output>",
      "themes": {"<theme_id>": {"present": bool, "evidence": str, "evidence_verified": bool}},
      "other_note": str,
      "latency_s": <float>
    }
  }
}
```

- **Input text:** `normalize_text(record["back_translated_answer_en"])`. A record is skipped (`skipped_unusable`) if `usable(record, "english")` is false. Do not store the tunnel URL anywhere.
- **Parsing:** the output must be one JSON object with a `themes` object holding every codebook id exactly once, each with a boolean `present` and a string `evidence`, plus a string `other_note`. Anything else is a parse failure. On failure, retry up to 2 more times, appending this line to the prompt: "Your previous output was not valid. Output only the JSON object." Record `attempts`. After the last failure, `status` is `parse_failed` and `themes` is null.
- **Evidence verification:** match after lowercasing, collapsing whitespace, mapping curly quotes to straight quotes, and stripping surrounding quotation marks and a leading or trailing "...". The quote must be 1 to 40 words and a contiguous substring of the matching-normalized input text. `evidence_verified` is true only then. A theme with `present: true` and an unverified or empty quote is `claimed` but not `verified`.
- **Resume:** `tags.json` is rewritten after every record. A re-run skips records already tagged with the same codebook hash, prompt hash and model; `--force` re-tags everything.

### 3.7 Theme metrics (Stage 2)

All use the `verified` count unless the file says `claimed`. Each is computed for views `all` and `reliable`. The language set for rates is the 22 languages (never `en`), restricted to records whose tagging `status` is `ok` and, for the `reliable` view, that are in the reliable English view. Records excluded from a computation are listed with the reason.

- **theme matrix** (`theme_matrix_verified.csv`, `theme_matrix_claimed.csv`): 23 rows by theme columns, values 0 or 1, empty for records without a successful tagging.
- **theme frequency:** per theme, `n_considered`, `n_present`, `proportion`, `en_present` (0, 1 or empty), and the list of languages where it is present.
- **language versus English:** per language, `n_themes`, `jaccard_with_en` (size of intersection over size of union of the two theme sets; empty if both sets are empty), `themes_in_lang_not_en`, `themes_in_en_not_lang`, and `verification_rate` (verified-present themes divided by claimed-present themes; empty if no claims).
- **group rates:** for each grouping (`families`, `scripts` from `config/language_groups.json`), group, theme: `n` (languages in the group considered), `n_present`, `rate`.
- **distinctive themes:** a theme is `rare_present` if present in at most `--rare-threshold` (default 2) of the considered languages, and `rare_absent` if absent in at most that many. Output the type and the languages involved.
- No significance tests. Descriptive only.

### 3.8 Keyword extraction (Stage 2)

Run on `normalize_text(back_translated_answer_en)` of every usable record, for views `all` and `reliable`.

- **Tokens:** lowercase; a token matches `[a-z]+(?:[-'][a-z]+)*` (hyphenated words such as "self-esteem" stay whole). Split text into segments at `. ! ? ; : ( ) , "` and the Unicode curly quotes; tokens and n-grams never cross a segment boundary.
- **Stopwords:** the list in `config/stopwords_en.txt` plus every token (3 or more letters) from the query's `source_query_en`. The union is recorded in `summary.json`.
- **Candidates:** unigrams of 3 or more letters that are not stopwords, and bigrams whose two tokens are both non-stopwords.
- **TF-IDF method:** corpus is the usable documents of the query (including `en`). `tf` = raw count of the term in the document; `idf = ln((1 + N) / (1 + df)) + 1`; score = `tf * idf`. Rank by score descending, ties alphabetically.
- **KeyBERT-style method** (our own implementation, not the KeyBERT package): embed the document and each of its candidates with `all-MiniLM-L6-v2` (via `src.similarity_embed`), score each candidate by cosine similarity with its document, rank descending, ties alphabetically. Needs `.venv-sim`; `--no-embed-keywords` skips it.
- **Selection:** top `--top-k` (default 10) per document and method, after this de-duplication walk: skip a unigram if it is a token of an already selected bigram.
- **Cross-language tables:** `keyword_df.csv` (for each term in the union of top-k lists, per method and view: `n_languages` from the 22 languages, which languages, whether it is in the `en` list, and a class: `shared` if `n_languages` is at least half of the languages considered, `rare` if at most 2, else `mid`); `keyword_overlap_with_en.csv` (per language and method: Jaccard of its top-k set with the `en` top-k set, and the shared terms).

`config/stopwords_en.txt`, one word per line (write exactly these):

```
a about above after again against all also am an and any are as at be because been before being below between both but by can could did do does doing done down during each few for from further get gets had has have having he her here him his how i if in into is it its just like made make makes may me might more most must my myself no nor not of off on once one only or other our out over own per same shall she should so some such than that the their them then there these they this those three through to too two under until up us very was we were what when where which while who whom why will with would yes you your yours yourself
certainly course sure okay etc example examples help helps helping
```

### 3.9 Outputs (`data/analysis/themes_<query_id>/`)

`tags.json`, `theme_matrix_verified.csv`, `theme_matrix_claimed.csv`, `theme_frequency.csv`, `language_vs_english.csv`, `group_theme_rates.csv`, `distinctive_themes.csv`, `keywords_per_language.csv` (code, method, view, rank, keyword, score), `keyword_df.csv`, `keyword_overlap_with_en.csv`, `summary.json` (query id, dataset and codebook and prompt hashes, tagger model and digest, tagger_is_generator, options, library versions, counts of ok, failed and skipped records and the reason for each exclusion, overall verification rate, stopword list used, parameters, timestamps) and `report.md` (tables, then the Limitations section in 3.11). All CSVs are UTF-8 with a header, NaN written as empty. Nothing is written inside `data/raw` or `data/analysis/similarity_*`.

### 3.10 Command lines

- Stage 1: `.venv-it2/bin/python -m src.theme_tag --query-id <id> --url <tunnel URL> --model <exact model tag> [--only en,hi-IN] [--force] [--self-grading-ok] [--max-retries 2] [--out-dir data/analysis]`
- Stage 2: `.venv-sim/bin/python -m src.theme_analyze --query-id <id> [--top-k 10] [--rare-threshold 2] [--no-embed-keywords] [--batch-size 8] [--models-dir models] [--out-dir data/analysis]`

Default `--query-id` is `self_image_life_goal`, as in the existing validators. If Phase 0 finds that `requests` is not available in `.venv-it2`, tell me before choosing another environment.

### 3.11 Limitations text (must appear in every `report.md`, verbatim)

1. Themes are tagged on English back-translations, not on the original-language text. Back-translation errors can add or remove themes; known problem records are listed, and the reliable view leaves them out.
2. The tagger is a language model. Requiring a verbatim evidence quote shows the quote exists in the text, not that the label is correct. The tagger model and whether it is the same model that wrote the answers are recorded in this report.
3. The codebook is a human-designed draft for this query. Ideas outside it appear only in the short "other_note" field.
4. Each language has one generated answer per query (one sample), so differences between languages cannot be separated from ordinary sampling variation.
5. Group sizes are small, and several groups have one to four languages. Rates are descriptive only and no significance tests are reported.
6. Keyword overlap reflects wording. Different back-translation phrasing lowers overlap even when the meaning is the same. Embedding-ranked keywords are ranked by similarity to the whole answer and are not a topic model.
7. All keyword analysis is on English back-translations; no native-script keywords are extracted.
8. These results describe one model on one query and do not generalize.

---

## 4. Phase prompts

### Phase 0: Read-only audit

```
PHASE 0: READ-ONLY AUDIT. Do not create, edit, delete, install or download anything in this phase, and make no network calls.

1. Read in full: docs/theme_coding_keywords_roadmap.md, then src/similarity_core.py, src/similarity_embed.py (function signatures and load_encoder), src/pipeline_sarvam.py (lines for OLLAMA_BASE_URL, OLLAMA_MODEL, NGROK_HEADER, verify_tunnel, _post_ollama, _get_native_answer_ollama), src/run_new_query.py (how --url is handled), src/auto_document.py (KNOWN_BACKTRANSLATION_LIMITS and review_required logic), config/languages.json, config/language_groups.json, and both datasets in data/raw/ (read-only). Do not open config/secrets.json.
2. For every bullet in Section 1 ("Verified facts"), re-check it and mark CONFIRMED or DIFFERENT with the exact difference and file:line.
3. Answer with evidence, writing UNKNOWN where you cannot verify:
   a. For each of .venv, .venv-it2 and .venv-sim: Python version; versions of numpy, requests, torch, sentence-transformers; and whether each imports: requests, numpy, sentence_transformers.
   b. Does "import src.pipeline_sarvam" have side effects (model loading, network calls, file writes) at import time? Show how you determined this (read the module's top level; do not run it against the network).
   c. Free disk (df -h .) and RAM (free -h).
   d. git status --short, git branch --show-current, git remote -v.
   e. sha256sum of every file in data/raw/ and of every file under data/analysis/. Record these as the BASELINE for the whole feature.
   f. For both datasets: counts of records, the list of codes, which have review_required true, which are in KNOWN_BACKTRANSLATION_LIMITS, and the first 200 characters of back_translated_answer_en for en, hi-IN and sd-IN.
4. List every conflict between Section 3 and what you found, and propose the smallest fix to the roadmap text. Do not apply it.

REPORT FORMAT: (1) CONFIRMED/DIFFERENT table; (2) answers 3a to 3f with raw output; (3) conflicts and proposed fixes; (4) questions for me. Then STOP.
```

### Phase 1: Tagger decision and endpoint check

You choose the tagger model; the agent cannot reach Colab. Two options, both served by Ollama on the tunnel the pipeline already uses:

- **A (recommended):** a different general instruction-following model of roughly 7 to 9 billion parameters, so the model that wrote the answers is not the one labelling them. You run `ollama pull <tag>` yourself in a Colab cell. Check the tag exists on Ollama's model library first, and check what the notebook's Drive-cache cell does before running it, because it may copy the new model to Drive as well.
- **C:** sarvam-m itself. No extra download, but the model grades its own answers; the report will say so and `--self-grading-ok` is required.

Paste the prompt with the model tag you chose in place of `<MODEL TAG>` and the current tunnel URL in place of `<URL>`.

```
PHASE 1: TAGGER ENDPOINT CHECK. This phase only reads from the tunnel; it writes nothing to the repository.

Tagger model: <MODEL TAG>
Tunnel URL: <URL>
Approval: network calls to this one URL are approved for this phase.

1. Using the pattern in src/pipeline_sarvam.py (replicate it in a throwaway inline script; do not edit that file), check: GET <URL>/api/tags with the NGROK_HEADER returns 200 and lists <MODEL TAG>. Print the exact tag list. If the tag is missing, STOP and tell me what to run in Colab.
2. Call POST <URL>/api/show for the model (check the field names in the real response; do not assume them). Print the model details you can see: the digest if present, the parameter size and quantization if present, and whether a capabilities list says the model supports "thinking".
3. Send ONE tiny test chat to /api/chat with: stream false, options {"temperature": 0, "seed": 13, "num_predict": 200}, and the user message: Reply with only this JSON: {"ok": true}. Do not send a think field. Show the full response JSON.
4. Test whether the server accepts a "format" field set to "json" (and, if the server documents it, a JSON schema object) by repeating step 3 with it. Report exactly what happened for each; do not assume support.
5. Repeat step 3 twice more with identical settings and show whether the three outputs are identical (determinism at temperature 0 with a fixed seed).
6. Time each call and report the first-call latency (model load) separately from later calls.

REPORT FORMAT: raw outputs for 1 to 6, a plain-language summary of what the server supports (format field, think, digest), and any problem. Then STOP.
```

### Phase 2: Config, pure core and unit tests (no network)

You must have reviewed and edited the two codebooks first (they stay `DRAFT` until you change the status yourself).

```
PHASE 2: CONFIG, PURE CORE AND UNIT TESTS. No network and no models in this phase.

Create exactly these files:
  a. config/codebooks/self_image_life_goal.json and config/codebooks/self_dev_tips.json: copy the JSON from Section 3.4 exactly, including "status": "DRAFT". Do NOT change any status to APPROVED.
  b. config/prompts/theme_tagging_v1.txt: copy the template from Section 3.5 exactly.
  c. config/stopwords_en.txt: copy the list from Section 3.8 exactly, one word per line.
  d. src/theme_core.py: standard library + numpy only. It may import from src.similarity_core and src.auto_document (read-only) but must not import torch, sentence_transformers or requests.
  e. tests/test_theme_core.py: unittest, run with: .venv-sim/bin/python -m unittest discover -s tests -t . -v

theme_core.py must provide these functions, per Sections 3.3 to 3.8 (names are fixed so later phases can rely on them):
  - load_codebook(path) -> dict   (validates the rules in 3.4; returns the dict)
  - codebook_is_approved(codebook) -> bool
  - render_prompt(template, query, codebook, text) -> str
  - parse_tag_response(raw, codebook) -> (themes_dict or None, other_note, error_message)
  - norm_for_match(text) -> str
  - verify_evidence(evidence, text) -> bool
  - apply_verification(themes, text) -> themes with "evidence_verified" set
  - tokenize_segments(text) -> list of lists of tokens
  - build_stopwords(base_path, query_text) -> set
  - candidate_terms(text, stopwords) -> list of unique candidate strings
  - tfidf_scores(docs_terms, ...) -> per-document dict of term to score  (use the formula in 3.8)
  - select_top_k(scored_terms, k) -> list  (ranking, tie rule and de-duplication walk from 3.8)
  - jaccard(a, b) -> float or None  (None when both sets are empty)
  - theme_tables functions that produce the rows of theme_frequency, language_vs_english, group_theme_rates and distinctive_themes as specified in 3.7
  - keyword_df_table and keyword_overlap_table as specified in 3.8
  - cohens_kappa(labels_a, labels_b) -> float or None  and percent_agreement(labels_a, labels_b) -> float or None  (None when undefined)

Unit tests (every expected value must be one you can verify by hand; write the arithmetic in a comment):
  - Codebook: both shipped codebooks load; a bad id, duplicate id, empty definition, 2 themes and 13 themes are all rejected; both shipped files have status DRAFT and codebook_is_approved returns False for them.
  - Prompt: the rendered prompt has single braces in the JSON line, contains every theme id, and contains none of the 22 language names, language codes, or script names from config/languages.json (check the template itself, with a placeholder-only text).
  - Parsing: a valid response parses; a missing theme id, an extra theme id, a non-boolean present, a non-string evidence, text before or after the JSON, and invalid JSON each fail with a clear message.
  - Evidence: exact quote passes; different case and spacing passes; curly quotes against straight passes; a paraphrase fails; a quote not in the text fails; empty evidence fails; 41 words fails.
  - Tokens and candidates: hyphenated words stay whole; n-grams do not cross a comma or full stop; stopwords and query tokens are excluded; bigrams containing a stopword are excluded.
  - TF-IDF: a 3-document toy corpus with hand-computed scores using idf = ln((1+N)/(1+df)) + 1; tie order alphabetical; the de-duplication walk drops a unigram that is a token of a selected bigram.
  - Tables: a small hand-made set of 5 languages and 3 themes with known answers for frequency, Jaccard (including the both-empty case), group rates and the rare_present and rare_absent thresholds.
  - Kappa: perfect agreement gives 1.0; a hand-computed 2x2 example; None when all labels are the same value.

Run the whole suite, py_compile every new .py file, and compute the SHA-256 of the datasets and of data/analysis/similarity_* before and after, comparing with the Phase 0 baseline.

REPORT FORMAT: files with line counts; full unittest output; py_compile output; hash comparison; git status --short (expected: only new untracked files). Then STOP.
```

### Phase 3: Tagging run (needs the tunnel)

Before this phase, set `"status": "APPROVED"` in a codebook yourself, only after you are satisfied with it. Start with `self_image_life_goal`.

```
PHASE 3: TAGGING RUN. Network calls to the tunnel URL below are approved for this phase.

Tagger model: <MODEL TAG>
Tunnel URL: <URL>
Self-grading: <write "NO" if the tagger is not sarvam, or "ALLOWED" if I chose option C>

Step A. Create src/theme_tag.py exactly per Sections 3.3, 3.5, 3.6 and 3.10. Requirements:
  - Refuse to run if the codebook status is not "APPROVED", with a clear message. Refuse a model name containing "sarvam" unless --self-grading-ok is given.
  - Use src.pipeline_sarvam.verify_tunnel for the health check if Phase 0 found that importing that module has no side effects; otherwise replicate its eight lines in the new file.
  - Build the chat call by replicating the pattern in src/pipeline_sarvam.py (headers, endpoint, timeout, retry on connection errors with 10 s and 20 s waits). Do not import or modify its private functions. Do not send "think". Send "format": "json" only if Phase 1 showed the server accepts it.
  - One independent call per record, in a fixed shuffled order (seed 13), writing tags.json after every record, and resuming as described in 3.6.
  - Never store the tunnel URL. Never write inside data/raw or data/analysis/similarity_*.
  - On a tunnel failure mid-run, stop with a clear message telling me to restart the notebook and give you a new URL; do not lose finished records.
  - Compute SHA-256 of the dataset at the start and end and abort if they differ.

Step B. Add the unit tests that apply (offline, using a fake server response) to tests/test_theme_core.py ONLY if they test theme_tag.py helper functions; otherwise add nothing. Show all tests passing.

Step C. PILOT. Run: .venv-it2/bin/python -m src.theme_tag --query-id self_image_life_goal --url <URL> --model <MODEL TAG> --only en,hi-IN,ta-IN. Show for each of the three records: the exact input_text, the raw_response, the parsed themes, which evidence quotes were verified, the attempts, and the latency. Then STOP and wait for me to review the pilot. Do not run the full set in this phase unless the text "APPROVED: FULL-RUN" appears at the end of this message.

Step D (only if "APPROVED: FULL-RUN" is present). Run the full set for self_image_life_goal detached with a log, polling it, then for self_dev_tips (its codebook must also be APPROVED; if not, skip it and say so). Show the log tail, the count of ok, parse_failed, http_failed and skipped records, and the overall and per-language verification rate. Compute the dataset hashes before and after.

REPORT FORMAT: files and line counts; test output; the pilot details; if Step D ran, the counts and rates and the full list of any records that failed and why; git status --short; the list of all git commands run. Then STOP.
```

### Phase 4: Analysis and keywords (no tunnel)

```
PHASE 4: ANALYSIS AND KEYWORDS. No tunnel is needed. The input is data/analysis/themes_<query_id>/tags.json from Phase 3.

Create src/theme_analyze.py exactly per Sections 3.7 to 3.11, using only the functions in src/theme_core.py for the computations and src.similarity_embed (read-only) for the encoder. Requirements:
  - Compute the dataset SHA-256 at start and end and abort if they differ; refuse any output folder inside data/raw or data/analysis/similarity_*.
  - Read tags.json and check that its recorded dataset hash and codebook hash match the current files; if not, stop and tell me.
  - Compute views "all" and "reliable" using src.similarity_core.reliable(record, "english", KNOWN_BACKTRANSLATION_LIMITS) with the set imported from src.auto_document.
  - Write every output file listed in 3.9. report.md contains the tables and the 3.11 limitations verbatim, plus the tagger model line and the self-grading statement from tags.json. It must state numbers and describe them only (Rule R10).
  - For the embedding keyword method load the "minilm" encoder, encode, then release it. Do not load any other encoder.

Run, in this order:
  A. .venv-sim/bin/python -m src.theme_analyze --query-id self_image_life_goal
  B. the same command into a temporary output folder (--out-dir /tmp/theme_run2); every CSV must be byte-identical to run A; tags.json is copied, not re-created.
  C. the same for self_dev_tips (if its tags.json exists).

Show the console summary, the first 15 lines of each CSV for run A, and the byte-identity result for B. Compute the hashes of data/raw and of all files under data/analysis/similarity_* before and after, and compare with the Phase 0 baseline.

REPORT FORMAT: files with line counts; commands and exit codes; summary tables; determinism result; hash comparison; excluded records and reasons; git status --short. Restate the numbers only; do not interpret them. Then STOP.
```

### Phase 5: Independent verification

```
PHASE 5: INDEPENDENT VERIFICATION. Try to prove the results wrong. Do not modify any source file in this phase; if you find a defect, report it and STOP.

For each analysed query, using only tags.json, the CSVs, the dataset and a throwaway inline script (do not save it):
  1. Re-verify every evidence quote from scratch against input_text with your own matching code, and compare with the stored evidence_verified values. Report any difference.
  2. Check that every input_text equals normalize_text of the dataset record's back_translated_answer_en.
  3. Rebuild theme_frequency, language_vs_english and group_theme_rates for the "reliable" and "all" views from the theme matrix and compare with the CSVs.
  4. Recompute Jaccard for 5 languages by hand (include one with empty theme sets if any) and compare.
  5. Recompute TF-IDF top-10 for 2 chosen documents by hand from the documents themselves and compare with keywords_per_language.csv; report the exact arithmetic for the top 3 terms of one document.
  6. Check keyword_df.csv classes against the rule (shared at least half, rare at most 2) for 10 terms you choose.
  7. Confirm that no rendered prompt, and no template, contains any language name, code or script name; scan the stored input_text values for language names and list every hit (do not alter them).
  8. Confirm that the tagging prompt hash, codebook hash and dataset hash in summary.json match the files on disk.
  9. Confirm report.md contains every number it states in the CSVs or JSON, includes the 3.11 limitations verbatim, and contains no sentence claiming the model is biased, stereotyped or culturally aware.
 10. Confirm SHA-256 of data/raw and all files under data/analysis/similarity_* equal the Phase 0 baseline.
 11. List every git command you ran in the whole session. None may be a write command.
 12. Run the full unit-test suite again.

REPORT FORMAT: a 12-item PASS/FAIL checklist with raw evidence for each, any defects, and the final git status --short. Then STOP.
```

### Phase 6 (optional): Human-agreement tooling

Use this to check the language-model tags against human judgement. Peers who read some of these languages can code a small sample.

```
PHASE 6 (OPTIONAL): HUMAN-AGREEMENT TOOLING. Proceed only if the text "APPROVED: HUMAN-CHECK" appears at the end of this message. No network, no models.

Create src/theme_human_check.py with two modes:
  --export --query-id <id> [--n 8] [--seed 13]
     Pick N non-English languages from the reliable English view, with a fixed seed, taking languages round-robin across the families in config/language_groups.json so that every family is represented before any repeats. Write two files under data/analysis/themes_<id>/:
       human_texts_<id>.csv  with columns: code, native_answer, english_text
       human_sheet_<id>.csv  with one row per record and theme: code, theme_id, theme_label, theme_definition, human_present (blank), coded_from (blank), comment (blank)
     The sheet must NOT contain the model's labels, evidence quotes or any hint of them, so human coding is blind.
  --score --query-id <id> --sheet <path to the filled sheet>
     Accept human_present values 1/0, yes/no, true/false (any case); ignore blank rows and report how many were ignored. Join with the verified model labels in tags.json. Report, per theme and pooled: number of pairs, percent agreement, and Cohen's kappa (None when undefined). If a theme has fewer than 30 pairs, print "too few pairs for a stable kappa; use raw agreement and counts". Write human_agreement_<id>.csv and a short human_agreement_<id>.md. List every disagreement with the model's evidence quote next to it. Also report agreement separately for rows marked coded_from = native and coded_from = english.

Add unit tests for the sampling (deterministic, every family represented, the sheet has no model labels) and for the scoring on a hand-made example. Run all tests. Do not touch tags.json.

REPORT FORMAT: files and line counts, test output, a sample of the first 10 sheet rows, git status --short. Then STOP.
```

---

## 5. Definition of done

- [ ] Phase 0 report with every Section 1 fact CONFIRMED, or the differences resolved in this roadmap.
- [ ] Both codebooks reviewed and approved by you (status changed by hand), and the tagger model chosen by you.
- [ ] All unit tests pass, with output shown.
- [ ] Tagging completed for both queries, with counts of ok, failed and skipped records and the verification rate per language shown.
- [ ] `theme_analyze` produced every output in Section 3.9 for both queries; the second run is byte-identical.
- [ ] The Phase 5 checklist is all PASS.
- [ ] SHA-256 of `data/raw` and `data/analysis/similarity_*` equal the Phase 0 baseline.
- [ ] `git status --short` shows only new files; the session's git command list contains no write command; nothing has been committed or pushed. You review, commit and push yourself.

## 6. After delivery: how you run it for a new query

1. Write and approve a codebook: `config/codebooks/<query_id>.json`, then change its `status` to `"APPROVED"` by hand.
2. With the tunnel running: `.venv-it2/bin/python -m src.theme_tag --query-id <id> --url <tunnel URL> --model <tagger tag>`
3. Without the tunnel: `.venv-sim/bin/python -m src.theme_analyze --query-id <id>`
4. Outputs appear in `data/analysis/themes_<id>/`.
