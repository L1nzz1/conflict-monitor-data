#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断 Agnes 平台能力：模型清单 / 3.0-flash 可用性 / 搜索端点探测。
在 GitHub Actions 里运行（key 从 secrets 读），日志自动脱敏。
"""
import json, os, urllib.request, urllib.error

BASE = (os.environ.get('AGNES_BASE') or 'https://apihub.agnes-ai.com/v1').rstrip('/')
KEY = os.environ.get('AGNES_API_KEY') or ''
HDRS = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}


def call(method, path, body=None, timeout=45):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=HDRS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()[:2000]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return -1, f'{type(e).__name__}: {str(e)[:200]}'


print('===== 1) GET /models（平台模型清单）=====')
code, txt = call('GET', '/models')
print('status:', code)
print(txt[:1800])

print('\n===== 2) 模型可用性（chat/completions 逐个试）=====')
for model in ['agnes-3.0-flash', 'agnes-3.0-flash-preview', 'agnes-3.0',
              'agnes-2.5-flash', 'agnes-3.0-pro']:
    code, txt = call('POST', '/chat/completions', {
        'model': model,
        'messages': [{'role': 'user', 'content': 'hi, reply with OK only'}],
        'max_tokens': 10,
    })
    tag = 'OK' if code == 200 else 'FAIL'
    # 提取关键错误信息（模型不存在/无权限等）
    err = ''
    if code != 200:
        m = json.loads(txt) if txt.startswith('{') else {}
        err = (m.get('error', {}) or {}).get('message', '')[:120] if isinstance(m.get('error'), dict) else txt[:120]
    print(f'[{tag}] {model} -> {code} {err}')

print('\n===== 3) 搜索端点探测 =====')
for path in ['/search', '/web_search', '/tools/web_search', '/searches']:
    code, txt = call('POST', path, {'query': 'Iran war latest', 'max_results': 3}, timeout=30)
    print(f'{path} -> {code} {txt[:120]}')

print('\n===== 4) chat 模型 web_search 参数探测 =====')
for payload_name, extra in [
    ('web_search:true', {'web_search': True}),
    ('enable_search:true', {'enable_search': True}),
    ('tools:[web_search]', {'tools': [{'type': 'web_search'}]}),
]:
    body = {
        'model': 'agnes-3.0-flash',
        'messages': [{'role': 'user', 'content': 'What is the latest news about the US-Iran war today?'}],
        'max_tokens': 60,
    }
    body.update(extra)
    code, txt = call('POST', '/chat/completions', body)
    tag = 'OK' if code == 200 else 'FAIL'
    print(f'[{tag}] {payload_name} -> {code} {txt[:200]}')

print('\n===== DIAG DONE =====')
