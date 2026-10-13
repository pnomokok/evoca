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