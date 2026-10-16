"""Exercise latest-message language switching in one real model session."""
import json
import unicodedata
from pathlib import Path
from uuid import uuid4

import requests

BASE = 'http://127.0.0.1:8192'
OUT = Path(__file__).resolve().parents[1] / 'test-results/general-agent/language-result.json'


def main():
    response = requests.post(BASE + '/api/v1/agent/sessions', json={}, timeout=30)
    response.raise_for_status()
    session_id = response.json()['session_id']
    prompts = [
        ('en', 'In one short sentence, what can you help me do on this urban planning map? Do not call tools.'),
        ('vi', 'Trong một câu ngắn, bạn có thể giúp tôi làm gì trên bản đồ quy hoạch này? Không gọi công cụ.'),
        ('en', 'What is your role on this map? Give one short sentence without calling tools.'),
    ]
    evidence = {'session_id': session_id, 'turns': []}
    for language, prompt in prompts:
        response = requests.post(BASE + '/api/v1/agent/chat', json={
            'session_id': session_id, 'request_id': str(uuid4()),
            'message': prompt, 'allow_native': False,
        }, timeout=120)
        response.raise_for_status()
        result = response.json()
        answer = result['answer']
        accented = any(unicodedata.category(c).startswith('L') and ord(c) > 127 for c in answer)
        # These bounded English/Vietnamese prompts permit a simple smoke check;
        # inspect stored replies too, rather than claiming a general detector.
        passed = accented if language == 'vi' else not accented
        evidence['turns'].append({'prompt': prompt, 'expected_language': language,
                                  'answer': answer, 'passed': passed})
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
        assert passed, evidence['turns'][-1]
    print(json.dumps({'passed': True, 'turns': evidence['turns']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
