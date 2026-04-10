import json
from typing import Any, Optional

async def parse_json(data: str) -> Optional[Any]:
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        print(f'Failed to decode JSON: {data}')
        return None