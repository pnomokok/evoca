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