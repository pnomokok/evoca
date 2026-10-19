# Friction log

What slowed us down while building Evoca, in the order we hit it. Each entry follows the same fields: task attempted,
steps taken, expected result, actual result, severity, workaround, and a suggestion.

Severity: **High** = blocked us or cost more than an hour; **Medium** = cost real time or forced a worse choice;
**Low** = surprising, but quick to get past.

| # | Area | Problem | Severity |
|---|---|---|---|
| 1 | MCP Python SDK v2 | Older FastMCP tutorials no longer work | Medium |
| 2 | AWS account (Free plan) | AccessDenied errors don't say why | High |
| 3 | AWS account, Amazon Polly | The project Region is fixed and limits voice quality | Medium |
| 4 | Amazon Bedrock | New accounts are blocked for about two hours | Low |
| 5 | MCP Python SDK v2 | Tool error messages are hidden from the client | Medium |
| 6 | Kiro and AI coding assistants | Generated code defaults to MCP SDK v1 APIs | Medium |
| 7 | AWS account, Amazon Polly | Upgrading to the Paid plan does not lift the Region lock | Medium |
| 8 | Amazon Bedrock (images) | No image model is reachable from the project Region | Medium |
| 9 | Kiro | Free credits ran out partway through the build | Medium |

---

## 1. Older FastMCP tutorials no longer work on MCP Python SDK v2

- **Task attempted:** Create a minimal MCP server over Streamable HTTP.
- **Steps taken:** Followed a tutorial that starts with `from mcp.server.fastmcp import FastMCP`, installed the current
  `mcp` package (2.3), and ran the server.
- **Expected result:** The tutorial code runs.
- **Actual result:** `ImportError`. In v2, FastMCP was renamed to `MCPServer`, and the old import path no longer exists.
- **Severity:** Medium. It costs time for anyone following an older guide, and most guides online are older.
- **Workaround:** Used `from mcp.server import MCPServer`, following the v2 documentation.
- **Suggestion:** Link the v2 migration guide from the hackathon's resources page, and add a short "v1 → v2 names"
  table to it.

## 2. Free plan AccessDenied errors don't say why

- **Task attempted:** Call Amazon Transcribe and Amazon Polly, and create an S3 bucket, from a new Free plan account.
- **Steps taken:** Called each service from the CLI and from boto3 with the account's credentials; checked our own IAM
  permissions; repeated the calls in several Regions.
- **Expected result:** Either the call works, or a clear message such as "not available on the Free plan" or "not
  available in this Region for your project".
- **Actual result:** A generic "explicit deny in a service control policy" error with only a policy ID. Two different
  policies (the plan's and the Region's) produce the same message.
- **Severity:** High. It cost us about an hour, because we first thought our own permissions were wrong.
- **Workaround:** Found the "Managed policies for projects" documentation, then tested each Region one by one. We
  replaced Transcribe with local speech-to-text (faster-whisper), which also gave us word timestamps.
- **Suggestion:** Name the reason in the error ("blocked by the Free plan" or "blocked outside your project Region")
  and link to the list of allowed services and Regions.

## 3. The project Region is fixed and limits voice quality

- **Task attempted:** Use Amazon Polly's neural voices for a voice-first app, where the voice is the product.
- **Steps taken:** Called Polly with `Engine="neural"` in our project Region, then tried other Regions.
- **Expected result:** We can pick a Region where neural voices are available.
- **Actual result:** Our project is fixed to eu-north-1, where Polly offers only the standard engine. Other Regions are
  denied (entry 2), and the Region cannot be changed (entry 7).
- **Severity:** Medium. Voice quality matters most in an Alexa+-style demo, and it is the first thing a listener notices.
- **Workaround:** Polly's standard engine in eu-north-1, for both the companion and the demo's sample answers.
- **Suggestion:** Show the assigned Region and its service limits (which Polly engines, which Bedrock models) during
  sign-up, before the account is created.

## 4. New accounts are blocked from Amazon Bedrock for about two hours

- **Task attempted:** Make a first Amazon Bedrock model call right after sign-up.
- **Steps taken:** Called several models through the Converse API from boto3; tried again after an hour.
- **Expected result:** Models work after sign-in, or the console shows a clear waiting state.
- **Actual result:** Every model returned "Your account is currently being verified" for about two hours. Anthropic
  models (our eval judge) then also needed a separate use-case form.
- **Severity:** Low. Fine once known, but surprising in a time-boxed hackathon.
- **Workaround:** Waited, submitted the form, and built against Amazon Nova in the meantime.
- **Suggestion:** Mention the verification window and the use-case form in the hackathon setup guide.

## 5. MCP SDK v2 hides tool error messages from the client

- **Task attempted:** Return clear validation errors from MCP tools, so the agent can correct its own call.
- **Steps taken:** Raised `ValueError` with a helpful message inside a tool, called the tool from our MCP client, and
  read the result the agent sees.
- **Expected result:** The exception's message reaches the client.
- **Actual result:** Any exception other than `ToolError` is reported only as "Error executing tool <name>". The agent
  cannot see why its call failed and cannot recover.
- **Severity:** Medium. It is silent: unit tests that call tools through a fake bridge cannot catch it.
- **Workaround:** Every tool raises expected validation errors as `ToolError`; unexpected crashes stay hidden, which is
  what we want for security.
- **Suggestion:** Document this behaviour prominently in the v2 migration guide, with an example of `ToolError`.

## 6. AI coding assistants default to MCP SDK v1 APIs

- **Task attempted:** Generate MCP client and server code with AI coding assistants, including Kiro's agent.
- **Steps taken:** Asked for MCP tools, a client bridge and tests, with mcp 2.3 installed.
- **Expected result:** Code that matches the installed SDK.
- **Actual result:** Generated code repeatedly used v1 names: `FastMCP`, `httpx`, `tool.inputSchema`, `result.isError`.
  Each one failed only at runtime, in three separate places on the same day.
- **Severity:** Medium.
- **Workaround:** Added an "MCP Python SDK v2" section with the correct names to our Kiro steering file
  (`.kiro/steering/evoca-rules.md`). The problem stopped. Claude Code reads the same file, so both agents follow it.
- **Suggestion:** Ship an official Kiro steering snippet with the MCP SDK, or let Kiro detect the installed SDK version
  and steer itself.

## 7. Upgrading to the Paid plan does not lift the Region lock

- **Task attempted:** Use Amazon Polly in eu-central-1 or us-east-1, to get a better voice than eu-north-1 allows.
- **Steps taken:** Upgraded the project account to the Paid plan, set a spending limit, signed in again with
  `aws login`, and ran the same Polly script in eu-central-1 and us-east-1. We then tried a separate, classic account
  sign-up: it was marked "not eligible for the free plan" because our details matched the existing account.
- **Expected result:** The upgrade removes the plan's service and Region limits.
- **Actual result:** Polly was still denied in both Regions, with the same service control policy message (only a
  policy ID). The documented ways out are a separate account or turning on "advanced features", which cannot be undone.
- **Severity:** Medium. We upgraded expecting the lock to go away; it didn't, and the remaining options were not
  reversible.
- **Workaround:** Kept Polly in the project Region (eu-north-1, standard engine).
- **Suggestion:** Say in the upgrade flow that the project Region stays fixed, and list the services that only work
  there.

## 8. No image model is reachable from the project Region

- **Task attempted:** Generate the fictional demo family's old photos and the landing page images with Amazon Bedrock,
  so every part of the demo is built on AWS.
- **Steps taken:** Looked up Amazon Nova Canvas, then the other image models on Amazon Bedrock and their Regions.
- **Expected result:** An Amazon image model we can call from our project.
- **Actual result:** Nova Canvas reached end of life on September 30, 2026, during the hackathon. The remaining image
  models on Bedrock (Stability AI) are offered in us-west-2, which our project Region lock (entries 2 and 7) denies.
- **Severity:** Medium. We had to go outside AWS for one part of the demo.
- **Workaround:** Generated the images with ChatGPT and say so in the README and in the demo itself.
- **Suggestion:** Name a successor when a model reaches end of life, and offer at least one image model in every
  Region a project can be locked to.

## 9. Kiro's free credits ran out partway through the build

- **Task attempted:** Build the whole backend in Kiro: data model, access control, MCP server, agents and voice pipeline.
- **Steps taken:** Kiro's agent built the foundation task by task from October 12, with a plan first and our review
  before each change.
- **Expected result:** Enough credits to finish the project in Kiro during the hackathon window.
- **Actual result:** The free plan's 50 credits ran out on the evening of October 16, after about four days of
  intensive single-developer work. Planning steps alone cost 1 to 4 credits each. The credits ended in the middle of a
  task: the last step of the REST and voice pipeline, while Kiro was fixing `decode_audio`, with 10 of 13 new API
  tests passing.
- **Severity:** Medium. The task stopped half-done, and we had to move it and the later features (the archivist, the
  family panel, privacy hardening) to another coding agent.
- **Workaround:** Continued with Claude Code under the same steering rules (`.kiro/steering/evoca-rules.md`, read by
  both through `CLAUDE.md`), so the rules and the code style stayed the same.
- **Suggestion:** A hackathon credit allowance for registered participants; a usage meter that warns before the
  credits run out; and a cost estimate before a plan step, so a task is not cut off halfway.
