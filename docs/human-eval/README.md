# Human evaluation of the persona responses

Two parts: a **reference CSV** (what each persona was and said) and a **web form** that collects
ratings into a Google Sheet.

## 1. The reference CSV — `persona_eval_items.csv`

One row per persona response (12 = 6 regions × male/female). Regenerate with
`cd backend && .venv/bin/python ../scripts/build_eval_items.py`.

| column | meaning |
|---|---|
| `item_id`, `region_id`, `region_name`, `persona_gender` | which persona |
| `persona_label`, `persona_age`, `persona_role`, `persona_place`, `persona_community`, `persona_tagline` | the persona card |
| `persona_description` | the short written description of the person |
| `persona_version` | 10-char hash of the exact persona prompt text (trace a response to its prompt) |
| `query` | the question that was asked |
| `persona_prompt` | the persona prompt given to the model as the start of its system prompt |
| `task_instructions` | the instruction block appended to the persona prompt (same for every row apart from the region name) |
| `user_message` | what the user message contained (the query plus the region's gathered evidence) |
| `response_tldr`, `response` | the persona's answer (source-number markers like `[12]` removed) |
| `baseline_response_no_persona` | the generic answer for that region with no persona (used for the A/B comparison) |
| `model_provider`, `reasoning_mode`, `run_id` | which run produced it |

**Caveats**
- The persona prompt was **rebuilt from the current persona files**; the run did not store it. The persona files have
  not been edited since the run as far as we know (their modification times only reflect git checkouts), and
  `persona_version` lets you confirm the text. The prompt is long (up to ~25,000 characters; the Google Sheets cell
  limit is 50,000).
- The evidence the model was shown (web sources, social clusters) is **not** in the CSV — only described in `user_message`.
- Every row shares one run and one model, so differences between rows are differences between personas, not models.

## 2. The form — `/evaluate/`

Lives in `public/evaluate/` (plain HTML, no build step) and ships with the site at
`<site>/evaluate/`. Each evaluator:

1. gives a little background and consents (name / email optional);
2. sees the 12 answers in a personal random order. For each: the question, the persona, the answer, then
   - 6 ratings (1–5): **fidelity** (sounds like this person), **authenticity** (details fit the region),
     **accuracy** (nothing wrong/invented), **stereotyping** (reverse-scored — higher = worse), **insight**
     (more than a generic answer would give), **overall**; plus their familiarity with the region;
   - a **blind A/B comparison** of the persona answer against the generic answer (random order, unlabelled):
     which is more likely to come from this person, and which better reflects the region;
   - optional flags (generic / factual error / stereotype / offensive) and a comment.
3. Progress is saved in the browser, so people can stop and resume. If the sheet can't be reached, answers
   are queued and re-sent; evaluators can also download their own answers as CSV.

### Connecting Google Sheets (≈5 minutes, needs your Google account)

1. Create a Google Sheet (name it e.g. *Persona evaluation responses*).
2. **Extensions → Apps Script**, replace the contents with [`apps-script/Code.gs`](apps-script/Code.gs), save.
3. **Deploy → New deployment → Web app** — *Execute as: Me*, *Who has access: Anyone* → Deploy, authorise,
   copy the **Web app URL** (ends in `/exec`).
4. Put that URL in `public/evaluate/config.json` as `"sheetEndpoint"`, commit and push. The site redeploys
   in about a minute.
5. Open `<site>/evaluate/`, submit one test item, check a row appears in the **Responses** tab (it creates the
   tab and header itself), then delete the test row.

Notes: the endpoint URL is visible to anyone who views the page source, so anyone could post junk rows; the script
ignores bot-filled forms and caps field sizes, and rows are keyed by evaluator + item so re-saving updates rather
than duplicates. Until `sheetEndpoint` is set, the form still works and just keeps answers in the browser.

### Analysing the sheet

`fidelity`, `authenticity`, `accuracy`, `insight`, `overall` — higher is better; `stereotyping` — higher is worse.
`cmp_more_likely_persona` / `cmp_better_represents` are already decoded to `persona` / `generic` / `both` / `neither`
(the form shows A/B in random order; `ab_order` records which way round each person saw it).
