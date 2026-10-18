## 1. Old FastMCP tutorials break on MCP Python SDK v2
- Task: Create a minimal MCP server over Streamable HTTP.
- Expected: Tutorials using `from mcp.server.fastmcp import FastMCP` would work.
- Actual: In v2, FastMCP was renamed to `MCPServer`; the old import path no longer exists.
- Severity: Medium (costs time for anyone following older guides).
- Workaround: Used `from mcp.server import MCPServer` from the v2 docs.
- Suggestion: Link the v2 migration guide from Amazon's hackathon resources page.


## 2. Free plan AccessDenied errors do not say why
- Task: Call Amazon Transcribe and Polly, and create an S3 bucket, from a new Free plan account.
- Expected: A clear message such as "not available on the Free plan" or "not available in this Region for your project".
- Actual: A generic "explicit deny in a service control policy" error with only a policy ID. Two different policies (plan and Region) produce the same message.
- Severity: High (cost us about an hour; we first thought our own permissions were wrong).
- Workaround: Found the "Managed policies for projects" documentation and tested each Region.
- Suggestion: Name the reason in the error message and link to the list of allowed services and Regions.

## 3. Project Region is assigned automatically and limits voice quality
- Task: Use Amazon Polly neural voices for a voice-first app.
- Expected: Choose a Region where neural voices are available.
- Actual: Free plan projects in Europe are fixed to eu-north-1, where Polly only offers the standard engine. The Region cannot be changed without upgrading.
- Severity: Medium (voice quality matters for an Alexa+ style demo).
- Workaround: Use Polly standard for now; evaluate browser voices.
- Suggestion: Show the assigned Region and its service limits during sign-up.

## 4. New accounts are blocked from Bedrock for about two hours
- Task: Run a first Bedrock model call right after sign-up.
- Expected: Models work after sign-in, or the console shows a clear waiting state.
- Actual: Every model returned "Your account is currently being verified". Anthropic models then also required a separate use case form.
- Severity: Low to medium (fine once known, but surprising during a time-boxed hackathon).
- Workaround: Waited, submitted the form, and tested Amazon Nova in the meantime.
- Suggestion: Mention the verification window in hackathon setup guides.

## 5. MCP SDK v2 hides tool error messages
- Task: Return clear validation errors from MCP tools so the agent can correct its call.
- Expected: The message of a raised exception reaches the client.
- Actual: Any exception other than ToolError is reported only as "Error executing tool <name>". The agent cannot see why a call failed and cannot recover.
- Severity: Medium (silent; unit tests with a fake bridge cannot catch it).
- Workaround: Wrap every tool so expected validation errors are raised as ToolError, while unexpected crashes stay hidden.
- Suggestion: Document this behavior prominently in the v2 migration guide.

## 6. AI coding assistants default to MCP SDK v1 APIs
- Task: Generate MCP client and server code with AI coding assistants.
- Expected: Code that matches the installed SDK (mcp 2.3).
- Actual: Generated code repeatedly used v1 names: FastMCP, httpx, tool.inputSchema, result.isError. Each failed only at runtime.
- Severity: Medium (three separate runtime failures in one day).
- Workaround: Added an "MCP Python SDK v2" section to the Kiro steering file with the correct names.
- Suggestion: Ship an official steering/rules snippet for Kiro with the SDK, or have Kiro detect the installed SDK version.
## 7. Upgrading to the Paid plan does not lift the Region lock
- Task: Use Amazon Polly in eu-central-1 or us-east-1 after upgrading the project account to the Paid plan.
- Expected: The upgrade removes the plan's service and Region limits.
- Actual: Polly was still denied in eu-central-1 and us-east-1 with the same service control policy message (only a policy ID). The documented ways out are a separate account or turning on "advanced features", which cannot be undone.
- Severity: Medium (we upgraded expecting the lock to go away; it did not, and the remaining options were not reversible).
- Workaround: Kept Polly in the project Region (eu-north-1, standard engine).
- Suggestion: Say in the upgrade flow that the project Region stays fixed, and which services work only there.
