#!/usr/bin/env python3
import json
from pathlib import Path

CFG = Path('/root/.openclaw/openclaw.json')
DENY = ['group:fs', 'group:runtime']


def main() -> None:
    data = json.loads(CFG.read_text(encoding='utf-8'))
    changed = False

    for agent in data.get('agents', {}).get('list', []):
        aid = agent.get('id', '')
        if aid.startswith('wecom-'):
            tools = agent.setdefault('tools', {})
            if tools.get('deny') != DENY:
                tools['deny'] = DENY
                changed = True

    if changed:
        CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print('updated: applied deny to all wecom-* agents')
    else:
        print('no change: all wecom-* agents already restricted')


if __name__ == '__main__':
    main()
