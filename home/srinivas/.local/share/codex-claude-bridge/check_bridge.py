import asyncio
import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable,
        args=['/home/srinivas/.local/share/codex-claude-bridge/server.py'])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps({'tools': [t.name for t in tools.tools]}), flush=True)
            status = await session.call_tool('claude_status', {})
            print(status.model_dump_json(), flush=True)
            result = await session.call_tool('claude_start', {
                'prompt': 'Connection test only. Do not read or change any files. Reply exactly: CLAUDE_BRIDGE_OK',
                'work_dir': '/home/srinivas/Documents/Codex', 'mode': 'review'})
            data = json.loads(result.content[0].text)
            print(json.dumps(data), flush=True)
            job_id = data['job_id']
            for _ in range(60):
                result = await session.call_tool('claude_result', {'job_id': job_id})
                data = json.loads(result.content[0].text)
                if data['status'] not in ('starting', 'running'):
                    print(json.dumps(data), flush=True)
                    assert data['status'] == 'completed' and 'CLAUDE_BRIDGE_OK' in data['output'], data
                    return
                await asyncio.sleep(2)
            raise TimeoutError('Claude connection test did not finish')

asyncio.run(main())
