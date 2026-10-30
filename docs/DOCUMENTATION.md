# Vectra IT KB Assistant

`answer(question)` returns `{"answer", "citations", "abstained"}` using **only** the Vectra IT KB. It cites
the articles it used, abstains and suggests a ticket when the KB doesn't cover a question, and masks personal
data before anything leaves the process.

The code is split so that each file does one job. [README.md](../README.md) has the full map; in short:

```
docs/kb/KB-*.md                   the 9 KB articles (input data)
code/main.py                      CLI: ingest | ask | chat | eval | serve | test
code/web/index.html               web UI
code/vectra/knowledge_base.py     parse + decide what to ingest      code/vectra/ingest.py      Pinecone upsert
code/vectra/privacy.py            PII masking                        code/vectra/safety.py      escalations, unsafe advice
code/vectra/agents/               guard -> retrieval -> answer (LLM) -> verifier
code/vectra/storage/              sessions + answer cache, in memory or Redis
code/vectra/pipeline.py           runs the agents in order, answer()
code/vectra/api.py                FastAPI                            code/vectra/evaluation/    eval cases, scoring, report
code/tests/                       22 offline tests
```

## 1. How to run

```
pip install -r requirements.txt uvicorn pytest
copy .env.example local\.env      # OPENAI_API_KEY and PINECONE_API_KEY (local/ is git-ignored)
cd code

python main.py ingest --dry-run   # which articles go in and why (no API calls)
python main.py ingest             # embed + upsert to Pinecone, writes kb_manifest.json
python main.py ask "What is the resolution target for a P2 ticket?"
python main.py chat               # interactive chat in one session
python main.py eval               # scored run -> reports/eval_report.md + eval_results.json
python main.py serve              # web UI at http://localhost:8000/ , API docs at /docs
python main.py test               # 22 offline tests, no API calls
```

In Python (from `code/`): `from vectra import answer; answer("My account got locked")`

**Hosted:** `app.py` exposes the FastAPI app for serverless hosting (region next to the Redis database). Keys are
environment variables on the host, never uploaded. Sessions and the answer cache live in Redis, because a serverless
host runs many short-lived instances that don't share memory.

## 2. Request flow (agents)

```
            question (+ optional session_id)
                       │
              ┌────────▼────────┐  local, ~0 ms
              │   GuardAgent    │  mask name / email / phone / employee id
              │                 │  detect urgency: security → ext. 7333, P1 → ext. 4357
              └────────┬────────┘
                       │ masked text only from here on
              ┌────────▼────────┐  ~0 ms
              │  SessionStore   │  last 2 turns; a short follow-up is searched with the previous question
              └────────┬────────┘
              ┌────────▼────────┐  ~0 ms         hit → return cached JSON (no OpenAI, no Pinecone)
              │  Answer cache   │──────────────►
              └────────┬────────┘
                       │ miss
              ┌────────▼────────┐  OpenAI embed + Pinecone query
              │ RetrievalAgent  │  top-3, filter status = "current", score ≥ MIN_SCORE
              └────────┬────────┘
          nothing ≥ threshold │ relevant articles
     ┌────────────────────────┤
     │ abstain, no LLM call   │
     │                ┌───────▼────────┐  OpenAI chat (JSON mode, temperature 0)
     │                │  AnswerAgent   │  "answer only from <kb_articles>, cite doc_ids, else abstain"
     │                └───────┬────────┘
     │                ┌───────▼────────┐  local, ~0 ms
     └───────────────►│ VerifierAgent  │  compares the draft with the retrieved articles:
                      │                │   drop citations that weren't retrieved; none valid → abstain
                      │                │   unsafe advice / stale VPN address → abstain
                      │                │   strip echoed personal data; prepend urgent note + cite it
                      └───────┬────────┘
                              ▼
     {"answer", "citations", "abstained", "session_id", "meta": {latency per stage, scores, checks}}
```

Only **one** agent uses the LLM. Guard and Verifier are plain code on purpose: instant, deterministic and
testable, and a prompt injection can't talk them out of their rules.

## 3. Ingestion: what went in and how it's split

| doc | status | decision | why |
|---|---|---|---|
| KB-001, 003–008 | current | **ingest** | 7 articles → 7 vectors |
| KB-002 | deprecated, superseded_by KB-007 | **skip** | Retired VPN address `vpn.vectralogistics.example`; wrongly says Linux works |
| KB-099 | unverified, owner none | **skip** | Not reviewed by IT, and contains a **prompt injection** telling AI assistants to have users turn off antivirus (KB-006 forbids this) |

* **One article = one vector.** All articles are under 1.5 KB, so splitting gains nothing and could cut
  the KB-003 priority table or the KB-007 error-code table in half. The article is also the unit we cite.
* **Metadata on every vector:** `doc_id, title, status, effective_date, owner, supersedes, text`. The query
  also filters `status = "current"`, a second safety net if a bad article is ever ingested.
* **Re-ingesting is safe:** vector id = doc_id, so changed articles are overwritten and anything no longer
  current is **deleted** from the index.
* **`kb_manifest.json`** records what was ingested or skipped and a `kb_version` hash. The answer-cache key
  includes it, so a KB change invalidates cached answers.

## 4. Session management

| Property | How |
|---|---|
| Fast | In-memory `OrderedDict`; get, append and evict are O(1) under one lock, costing microseconds |
| Sliding expiry | 30 min idle (`SESSION_TTL_SECONDS`); every request restarts the clock |
| Bounded memory | Max 6 turns per session, max 10,000 sessions (oldest evicted first) |
| Secure ids | `secrets.token_urlsafe(16)`; an unknown or expired id gets a new id |
| No personal data | Only masked questions are stored |
| Follow-ups | A short or pronoun-led question ("And on Linux?") is searched with the question that set the topic (chains skip back past earlier follow-ups: VPN → "And on Linux?" → "What about macOS?" still searches with the VPN question); the last 2 turns go to the LLM as context, **not** as a source |
| API | `POST /answer` (creates a session if none given), `POST /sessions`, `GET`/`DELETE /sessions/{id}`, `GET /health`, `GET /` (web UI) |
| Web UI | Sample-question tray, chat with citation / abstain / PII / latency tags, the raw JSON of each answer below the chat, and a session-history drawer (top-right). History is kept in the browser with the **masked** question read back from `GET /sessions/{id}`, so raw personal data never lands in browser storage |
| Scale-out | Set `REDIS_URL` (any Redis) or `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` and sessions + the answer cache move to Redis (`RedisSessionStore`/`RedisCache`, same methods, sliding TTL via `GETEX`). Without them everything stays in memory. `/health` shows which store is active |

## 5. JSON contract

`answer(question)`:
```json
{"answer": "The resolution target for a P2 ticket is 8 hours. The first response time is 1 hour.", "citations": ["KB-003"], "abstained": false}
```
`POST /answer` adds `session_id` and `meta` (cache_hit, llm_called, followup, retrieved doc scores,
pii_masked, verifier checks, latency per stage, kb_version, error). If OpenAI or Pinecone fails, it still
returns valid JSON: `abstained: true`, a "raise a ticket" message and `meta.error`. It never crashes and
never makes up an answer.

## 6. How we know it works

* **22 offline tests** (`python main.py test`, in `code/tests/`): ingestion decisions, tables kept whole, PII masking,
  session TTL/eviction/follow-ups, the Redis store, verifier rules (incl. no repeated urgent note), cache, and safe JSON on service errors.
* **Live eval** (`python main.py eval`): the 5 samples, 9 tricky cases and a two-turn session,
  each run cold and then warm. Each part is scored separately.

Model comparison (`eval --models gpt-4.1-mini gpt-4o-mini`, kb_version `6f17bb80f92f`):

| model | pass | right article retrieved | correct abstain | correct citation | expected content | nothing unsafe | p50 | p95 |
|---|---|---|---|---|---|---|---|---|
| **gpt-4.1-mini** (default) | cold | 12/12 | 14/14 | 14/14 | **11/11** | 16/16 | 1.8 s | 2.1 s |
| gpt-4.1-mini | warm (cache) | 12/12 | 14/14 | 14/14 | 11/11 | 16/16 | < 1 ms | < 1 ms |
| gpt-4o-mini | cold | 12/12 | 14/14 | 14/14 | 10/11 (misses P2 first response) | 16/16 | 1.8 s | 2.3 s |

The content checks include: P2 → 8 hours **and** 1 hour first response; lockout → 30 minutes plus the 5-attempt
rule or the reset link; mailbox → no advice that isn't in KB-004; phishing / P1 → the extension appears exactly
once (no repeated note).

Highlights: VPN → `zt-gw.vectralogistics.example` (KB-007, never the stale KB-002 address); parking pass,
slow laptop, canteen and the "turn off Defender" injection all abstain **without an LLM call**; Linux →
unsupported (KB-007); ZT-401 is answered from the table row; Anand's name, email and phone never reach OpenAI
or the logs and are not echoed back; phishing → ext. 7333; dock printers down → P1, ext. 4357 first.

Similarity scores seen: correct article **0.44–0.65**; best score for questions the KB doesn't cover
**0.19–0.31**. `MIN_SCORE = 0.35` sits in that gap.

### Fixes made after the first live run
1. **The prompt now asks for related facts from the same table row or section**, plus two invented examples
   of the right amount of detail. P2 now gives 1-hour first response + 8-hour resolution.
2. **"Don't add advice that isn't in the articles."** The mailbox answer no longer invents "delete emails".
3. **No repeated urgent note.** The verifier prepends the ext. 7333 / 4357 note only if the answer doesn't already contain it.
4. **Threshold raised 0.30 → 0.35.** The parking pass (0.305) now abstains without paying for an LLM call.
5. **Default model switched to gpt-4.1-mini**, the only one at 11/11, with similar latency.

### What still fails or is unproven
1. **The threshold rests on about 15 questions.** It needs a few hundred real tickets to tune properly.
2. **LLM answers vary between runs.** The lockout answer gives the 5-attempt rule but usually not the reset link.
   gpt-4o-mini still drops the P2 first-response time. The eval has to run on every prompt change.
3. **Name masking** only catches "I'm …" / "my name is …".
4. **Follow-up detection** is a heuristic, and the unsafe-advice filter is a pattern list.
5. **Speed:** a cold answer is about 1.8 s (embedding ~0.5 s, Pinecone ~0.4 s, LLM ~1.1 s). Pinecone sits in
   `aws us-east-1` while users are in India, so co-locate the API with the index, or use a closer region.

## 7. Speed

| Stage | Measured (cold) | What keeps it fast |
|---|---|---|
| Guard + session + verifier | < 1 ms | Plain code |
| Repeat question | **< 1 ms** | Answer cache (key = kb_version + model + masked question, 1 h TTL) |
| Embedding | ~0.5 s | Small model, question-embedding cache |
| Pinecone | ~0.3–0.4 s | top_k=3 with metadata, so no second fetch; same-region deployment would cut this to ~20 ms |
| LLM | ~1.1 s | gpt-4.1-mini, temperature 0, max 400 tokens, 3 short articles; **skipped** when nothing is relevant |

Tokens are not streamed, because the verifier must see the whole draft before the user does.
`python main.py eval --models gpt-4.1-mini gpt-4o-mini` compares models on accuracy **and** speed (results in section 6).

## 8. Before going live to 3,000 staff (priority order)
1. **Re-index automatically** when an article changes status (KB-002 → KB-007): run `ingest` from the KB's publish workflow.
2. **Never ingest unverified content** (KB-099). Ingestion enforces this; also make it a review gate.
3. **Mask personal data** before logging or calling the LLM (done). Add a stronger detector for names.
4. **Bigger test set from real Vectra tickets**, run on every KB or prompt change; block a release on any safety failure.
5. **P1 and security:** always tell users to phone ext. 4357 (KB-003) or SecOps ext. 7333 (KB-006) (done).
6. **Roll out to service-desk agents first**, collect feedback, then roll out to all staff.
7. Operations: co-locate the API and vector DB, turn on the Redis store (already built), rate limit per user, add SSO on the API, and set alerts on abstain rate and errors.
