# Spike results (Oct 13, 2026)

Short experiments to check that each building block works before we build on it.
Scripts live in `experiments/`. Audio files are git-ignored.

## Summary

| Block | Choice | Status |
|---|---|---|
| MCP server | MCP Python SDK v2 (`MCPServer`), Streamable HTTP | Works, protocol 2026-07-28 |
| LLM | Amazon Bedrock, Converse API | Works, tool calling verified |
| Speech-to-text | faster-whisper `small.en`, local CPU | Works, word timestamps |
| Text-to-speech | Amazon Polly standard (temporary) | Works, sounds robotic; revisit before demo |
| Amazon Transcribe | Not available on the AWS Free plan | Blocked |

## AWS account constraints (Free plan, "projects" experience)

- Project Region is assigned automatically from the contact address: **eu-north-1 (Stockholm)**. It cannot be changed on the Free plan.
- Most services only work in the project Region. `us-east-1` allows little more than Bedrock inference.
- **Bedrock** inference works from any Region. We call it in `us-east-1` with `us.` inference profiles.
- **Polly** works only in `eu-north-1`, and only with the `standard` engine (no neural or generative there).
- **Transcribe** is denied on the Free plan in every Region (Paid plan only).
- New accounts are blocked from Bedrock for about 2 hours while the account is verified.
- Anthropic models need a one-time use case form. Their usage is billed through AWS Marketplace;
  whether Free plan credits cover it is unconfirmed, so we use Amazon Nova until billing is checked.
- Local credentials come from `aws login` (no access keys). Boto3 needs the `crt` extra for this.

## LLM: tool-calling test (`experiments/bedrock_test.py`)

One fake tool (`get_pending_questions`) and a system prompt that asks the model to check family
questions before greeting the storyteller.

| Model | Called tool | Total latency | Notes |
|---|---|---|---|
| `us.amazon.nova-pro-v1:0` | Yes | 2.1 s | Leaks `<thinking>` tags into the reply; must be stripped before speech |
| `us.amazon.nova-2-lite-v1:0` | Yes | 1.4 s | Warm, natural reply, no tags |
| `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Yes | 2.5 s | Best reasoning: turned "grandpa" into "your husband" when speaking to the grandmother |

**Decision (for now):** Nova 2 Lite for both agents during development.
Candidate for later: Claude Haiku 4.5 for the archivist agent, once billing is confirmed.
The model ID is a single config value per agent.

## Speech-to-text test (`experiments/whisper_test.py`)

Input: 73 s English recording by a Turkish speaker, with Turkish names and places.

- Transcription took about 25 s on CPU (`small.en`, int8). That is roughly 3 to 4 s for a 10 s answer.
- Word-level timestamps for every word, which is what `Segment.words` needs.
- Without hints, all names were wrong (Ahmet → Ahmed, Zeynep → Zainab, Kaz Dağları → Kasdaller).
- With `initial_prompt="A family story. Names: Ahmet, Zeynep. Places: Kaz Dağları."` all six name mentions were correct.
- Remaining errors were common words (electricity → elasticity, gas → glass, GPS → GSP).

**Decision:** Always build an `initial_prompt` from the family's Person names (and known places) before transcribing.

Setup notes (Windows):
- Pin `av<17`; av 19 breaks faster-whisper 1.2.
- If `~/.cache` is a file, set `HF_HOME` to another folder before the first run.

## Text-to-speech

Polly `standard` voice (Joanna) in `eu-north-1` works but sounds robotic.
TTS stays behind one small function so we can swap in browser voices (for example Edge "Natural" voices)
or Polly neural later without touching the rest of the code.

## Speech-to-text model benchmark (Oct 18, 2026, `experiments/stt_benchmark.py`)

Question: can a smaller faster-whisper model shorten the device turn without losing names?
Settings as in `server/speech.py`: CPU (16 threads, AMD Ryzen laptop), int8, `beam_size=1`, `vad_filter`, word
timestamps, the seed family's `initial_prompt` (plus the companion's question for the Polly clips). Audio: the 5 files
in `experiments/audio/`, `core/seed_assets/seed_session.wav` (42 s) and 3 Polly answers (Kendra, about 9 s each,
cached in `experiments/audio_polly/`) using Fatma, Ayşe, Elif, Can and Yilmaz. Warm model, 3 runs per clip.

| Model | Median s per 10 s audio | Hint names missed (7 name checks, Polly clips) | Common words on the real recordings |
|---|---|---|---|
| small.en (current) | 5.01 | 5 of 7: Ayşe ×3 (Ayesha, Aisa, Aiza), Elif (Aylif), Can (Ken) | Baseline |
| distil-small.en | 10.00 | 5 of 7: Ayşe ×3, Elif, Yilmaz | Unusable: repetition loops ("She sat with me. She. She. ...") on 5 of 9 clips |
| base.en | 1.17 (77% faster) | 2 of 7: Ayşe ×2 (Isa) | New clear errors: "arm village", "I was married with 10", "milk magic", "winning dart roasts", "incursable", "helping Keon", and Zeynep and Ahmet lost in one sentence ("with the inner penoment") |

**Decision:** keep `small.en`. base.en is fast enough, but it fails the rule (every name right and no new clearly
wrong common words on the real recordings). distil-small.en is slower and loops. The model is now configurable with
`EVOCA_WHISPER_MODEL` (default `small.en`).

Findings:
- Per 10 s, short clips cost more (fixed overhead): a 9 s answer takes about 4.5 s with small.en.
- small.en misses Polly's Turkish names even with the hint (Elif → Aylif, Can → Ken), while base.en gets them on
  the same audio. Ayşe fails in every model: Polly's English voice does not say it the Turkish way.
- Model load (warm cache): small.en 3.1 s. The distil-small.en and base.en load times in the run included the download.

## Where the LLM + tools time goes (Oct 18, 2026, one `scripts/e2e_demo.py` run, call-level timing)

| Device request | Nova 2 Lite calls | MCP tool calls | LLM time | MCP time |
|---|---|---|---|---|
| Opening (day 1) | 3 | 4 (context, questions, mark asked, reactions delivered) | 4.6 s | 0.29 s (first context call 0.23 s) |
| Answer turn | 1 | 0 | 0.86 s | 0 |
| Secret turn ("keep this between us") | 2 (keep_private is a local tool round) | 2 × mark_private | 1.76 s | 0.04 s |
| "Play me the story" turn | 3 | 2 (search_archive, get_linked_playlist) | 2.59 s | 0.05 s |
| Opening (day 3) | 3 | 4 | 3.28 s | 0.07 s |

Each Nova round costs about 0.85 s; an MCP call costs 15 to 25 ms. The LLM + tools time is almost all LLM, and
it grows with the number of tool rounds, not with the tools.

Possible next steps (not done):
1. Opening: fetch session context and pending questions in code (through the MCP server, same filtering) and put
   them in the first request, so the model needs one round less: about 0.9 s off every opening.
2. Playlist: return the linked playlist with the `search_archive` hit (or let the model call both tools in one
   round): one round less, about 0.85 s off every "play me" turn.
