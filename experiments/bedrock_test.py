"""Quick test: can we call a Bedrock model, and does it use tools correctly?

Step 1 tries a few models and reports which ones this account can use.
Step 2 runs a tool-calling round trip with the first model that works.
Usage: python experiments/bedrock_test.py
"""

import sys
import time

import boto3
from botocore.exceptions import ClientError

REGION = "us-east-1"

CANDIDATE_MODELS = [
    "us.anthropic.claude-haiku-4-5-20251001-v1:0",
    "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "us.amazon.nova-2-lite-v1:0",
    "us.amazon.nova-lite-v1:0",
    "us.amazon.nova-pro-v1:0",
]

TOOLS = {
    "tools": [
        {
            "toolSpec": {
                "name": "get_pending_questions",
                "description": "Return questions family members want the storyteller to answer.",
                "inputSchema": {
                    "json": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer", "description": "Max questions to return."}},
                        "required": ["limit"],
                    }
                },
            }
        }
    ]
}

SYSTEM = [
    {
        "text": (
            "You are Evoca, a warm voice companion that helps an older family member record life stories. "
            "Before greeting the storyteller, check which questions the family has sent. "
            "Then greet them in two short sentences and ask exactly one of those questions."
        )
    }
]


def try_model(client, model_id: str) -> bool:
    try:
        client.converse(
            modelId=model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the single word: ready"}]}],
            inferenceConfig={"maxTokens": 10},
        )
        print(f"  OK      {model_id}")
        return True
    except ClientError as error:
        code = error.response["Error"]["Code"]
        message = error.response["Error"]["Message"][:140]
        print(f"  FAILED  {model_id}  ->  {code}: {message}")
        return False


def tool_round_trip(client, model_id: str) -> None:
    messages = [{"role": "user", "content": [{"text": "(Session started. The storyteller, Ayse, has just sat down.)"}]}]

    started = time.time()
    first = client.converse(modelId=model_id, system=SYSTEM, messages=messages, toolConfig=TOOLS)
    print(f"\nFirst call: stopReason={first['stopReason']}  ({time.time() - started:.1f}s)")

    tool_uses = [block["toolUse"] for block in first["output"]["message"]["content"] if "toolUse" in block]
    if not tool_uses:
        print("Model did NOT call the tool. Its reply was:")
        print(first["output"]["message"]["content"])
        return

    call = tool_uses[0]
    print("Model called:", call["name"], "with", call["input"])

    fake_result = {
        "questions": [
            {"id": 1, "asked_by": "Zeynep (granddaughter)", "text": "How did you meet grandpa?"},
            {"id": 2, "asked_by": "Mert (grandson)", "text": "What was your first job?"},
        ]
    }
    messages.append(first["output"]["message"])
    messages.append(
        {
            "role": "user",
            "content": [{"toolResult": {"toolUseId": call["toolUseId"], "content": [{"json": fake_result}]}}],
        }
    )

    started = time.time()
    second = client.converse(modelId=model_id, system=SYSTEM, messages=messages, toolConfig=TOOLS)
    print(f"\nSecond call: stopReason={second['stopReason']}  ({time.time() - started:.1f}s)")
    for block in second["output"]["message"]["content"]:
        if "text" in block:
            print("Evoca says:", block["text"])


def main() -> None:
    client = boto3.Session(region_name=REGION).client("bedrock-runtime")

    print("Step 1: which models can this account use?")
    working = [model_id for model_id in CANDIDATE_MODELS if try_model(client, model_id)]
    if not working:
        print("\nNo model worked. Paste this output to Claude.")
        return

    chosen = sys.argv[1] if len(sys.argv) > 1 else working[0]
    print(f"\nStep 2: tool-calling test with {chosen}")
    tool_round_trip(client, chosen)


if __name__ == "__main__":
    main()