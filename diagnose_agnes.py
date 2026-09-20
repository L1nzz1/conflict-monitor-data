#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""搜索真实性验证：问实时问题，对比 web_search:true vs 无参数的回答。"""
import json, os, urllib.request

BASE = (os.environ.get('AGNES_BASE') or 'https://apihub.agnes-ai.com/v1').rstrip('/')
KEY = os.environ.get('AGNES_API_KEY') or ''
HDRS = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + KEY}
Q = ('What is today\'s date (year-month-day)? Then name ONE specific headline from BBC World news '
     'published in the last 12 hours, with its exact title. Be concrete.')


def ask(model, extra=None):
    body = {'model': model, 'messages': [{'role': 'user', 'content': Q}], 'max_tokens': 300}
    if extra:
        body.update(extra)
    req = urllib.request.Request(BASE + '/chat/completions',
                                 data=json.dumps(body).encode(), headers=HDRS)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode())
        msg = d['choices'][0]['message']['content'].strip()
        if d['choices'][0].get('finish_reason') == 'length':
            msg += ' …[截断]'
        return msg[:500]
    except Exception as e:
        return f'ERR {type(e).__name__}: {str(e)[:150]}'


print('===== A) agnes-2.5-flash 无搜索参数（基线，模型知识）=====')
print(ask('agnes-2.5-flash'))
print('\n===== B) agnes-3.0-flash 无搜索参数（基线）=====')
print(ask('agnes-3.0-flash'))
print('\n===== C) agnes-3.0-flash + web_search:true =====')
print(ask('agnes-3.0-flash', {'web_search': True}))
print('\n===== D) agnes-3.0-flash + enable_search:true =====')
print(ask('agnes-3.0-flash', {'enable_search': True}))
print('\n===== E) agnes-2.5-flash + web_search:true =====')
print(ask('agnes-2.5-flash', {'web_search': True}))
print('\n===== DONE =====')
