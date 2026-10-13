import anyio

from mcp import Client
from mcp.types import TextContent


async def main() -> None:
    async with Client("http://localhost:8000/mcp") as client:
        print("Protocol version:", client.protocol_version)

        tools = await client.list_tools()
        print("Tools:", [tool.name for tool in tools.tools])

        result = await client.call_tool("hello", {"name": "Zeynep"})
        for block in result.content:
            if isinstance(block, TextContent):
                print("Result:", block.text)
        print("Error:", result.is_error)


if __name__ == "__main__":
    anyio.run(main)