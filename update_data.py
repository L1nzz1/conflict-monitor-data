# -*- coding: utf-8 -*-
"""
全球冲突态势 - 数据更新脚本（GitHub Actions 定时运行）
流程：RSS 抓取（api.rss2json.com 代抓，绕墙）→ 关键词过滤 → Agnes AI 整理最新战况
     → 只更新 deaths/troops/status/desc 字段 → 校验 → 写回 data.json
不可变字段（id/name/region/tier/lon/lat/since/parties/countries）从旧数据合并保留。
"""
import json
import os
import re
import sys
import urllib.request
from datetime import date

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data.json')

AGNES_BASE = os.environ.get('AGNES_BASE', 'https://apihub.agnes-ai.com/v1')
AGNES_MODEL = os.environ.get('AGNES_MODEL', 'agnes-2.5-flash')
AGNES_API_KEY = os.environ.get('AGNES_API_KEY', '')

FEEDS = [
    ('BBC', 'https://api.rss2json.com/v1/api.json?rss_url=https%3A%2F%2Ffeeds.bbci.co.uk%2Fnews%2Fworld%2Frss.xml'),
    ('卫报', 'https://api.rss2json.com/v1/api.json?rss_url=https%3A%2F%2Fwww.theguardian.com%2Fworld%2Frss'),
]

# 冲突关键词（与网页端 NEWS_KW 一致思路）
KW = re.compile(
    r'war|invasion|offensive|battle|missile|drone|air ?strike|airstrike|ceasefire|'
    r'troops|military|civilian|casualt|killed|dead|death|conflict|clash|attack|'
    r'rebel|militia|occup|shelling|frontline|front line|offensiv|retreat|advance|'
    r'和平|战争|冲突|停火|袭击|轰炸|导弹|无人机|军队|士兵|伤亡|死亡|战|叛军|民兵|占领|战线|进攻|谈判',
    re.IGNORECASE)

# AI 只允许更新的字段
UPDATABLE = ('deaths', 'troops', 'status', 'desc')
NON_UPDATABLE = ('id', 'name', 'region', 'tier', 'lon', 'lat', 'since', 'parties', 'countries')


def fetch_json(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 conflict-monitor-bot'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def fetch_news():
    items = []
    for src, url in FEEDS:
        try:
            d = fetch_json(url)
            for it in d.get('items', []):
                title = (it.get('title') or '') + ' ' + (it.get('description') or '')
                if KW.search(title):
                    items.append({
                        'src': src,
                        'title': (it.get('title') or '').strip(),
                        'link': it.get('link', ''),
                        'pubDate': it.get('pubDate', ''),
                    })
        except Exception as e:
            print(f'[warn] feed {src} failed: {e}', file=sys.stderr)
    # 去重（按标题前 60 字符）
    seen, uniq = set(), []
    for it in items:
        k = it['title'][:60]
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    return uniq[:20]


def call_agnes(conflicts, news):
    brief = '\n'.join(f"- [{c['id']}] {c['name']}：当前状态「{c['status']}」，年内死亡估算 {c['deaths']}，投入兵力估算 {c['troops']}")
    headlines = '\n'.join(f"- ({n['src']}) {n['title']}" for n in news)
    prompt = f"""你是全球冲突态势监测员。以下是当前各冲突的已知数据：

{brief}

以下是从新闻 RSS 抓取的最新标题（按时间排序）：

{headlines}

请基于新闻标题，对上述各冲突的最新战况做整理更新。规则：
1. 只输出一个 JSON 数组，元素为 {{"id": "...", "deaths": 数字, "troops": 数字, "status": "一句中文状态", "desc": "两三句中文描述"}}。
2. 新闻中没有涉及的冲突也必须包含（保持原值）。
3. deaths/troops 只可上调不可下调，是年内估算值；无法从新闻推断时保持原值。
4. status/desc 要反映最新进展；desc 保留原文中仍准确的关键背景。
5. 不要输出任何解释、注释或 markdown 代码块标记，只输出 JSON。"""
    body = {
        'model': AGNES_MODEL,
        'messages': [
            {'role': 'system', 'content': '你是严谨的数据整理助手，只输出合法 JSON。'},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
    }
    req = urllib.request.Request(
        AGNES_BASE + '/chat/completions',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + AGNES_API_KEY},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read().decode('utf-8'))
    return resp['choices'][0]['message']['content']


def parse_ai_json(text):
    """剥掉可能的代码围栏，取第一个 [ 到最后一个 ]。"""
    t = text.strip()
    t = re.sub(r'^```(?:json)?', '', t).strip()
    t = re.sub(r'```$', '', t).strip()
    s, e = t.find('['), t.rfind(']')
    if s == -1 or e == -1 or e <= s:
        raise ValueError('no JSON array found in AI output')
    return json.loads(t[s:e + 1])


def merge_and_validate(old_conflicts, ai_list):
    old_by_id = {c['id']: c for c in old_conflicts}
    ai_by_id = {c.get('id'): c for c in ai_list}
    if set(ai_by_id.keys()) != set(old_by_id.keys()):
        missing = set(old_by_id.keys()) - set(ai_by_id.keys())
        extra = set(ai_by_id.keys()) - set(old_by_id.keys())
        raise ValueError(f'id mismatch: missing={missing} extra={extra}')

    merged, changes = [], []
    for c in old_conflicts:
        a = ai_by_id[c['id']]
        new = {k: c[k] for k in NON_UPDATABLE if k in c}
        for k in UPDATABLE:
            v = a.get(k, c.get(k))
            if k in ('deaths', 'troops'):
                try:
                    v = int(v)
                except (TypeError, ValueError):
                    v = c.get(k, 0)
                if v < 0:
                    v = 0
                if v < c.get(k, 0):
                    v = c.get(k, 0)  # 只可上调
            elif k == 'desc' and not isinstance(v, str):
                v = c.get(k, '')
            elif k == 'status' and not isinstance(v, str):
                v = c.get(k, '')
            new[k] = v
        merged.append(new)
        delta = {k: (c.get(k), v) for k, v in new.items() if c.get(k) != v}
        if delta:
            changes.append((c['id'], delta))
    return merged, changes


def main():
    if not AGNES_API_KEY:
        print('AGNES_API_KEY missing', file=sys.stderr)
        sys.exit(1)

    with open(DATA_PATH, encoding='utf-8') as f:
        old = json.load(f)

    news = fetch_news()
    print(f'news after filter: {len(news)}')
    if not news:
        print('no news items, skip')
        sys.exit(0)

    raw = call_agnes(old['conflicts'], news)
    ai_list = parse_ai_json(raw)
    merged, changes = merge_and_validate(old['conflicts'], ai_list)

    new_data = {
        'updated': date.today().isoformat(),
        'conflicts': merged,
        'supports': old['supports'],
        'battles': old['battles'],
        'cc': old['cc'],
    }
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(new_data, f, ensure_ascii=False, indent=1)

    print(f"updated={new_data['updated']} changed_conflicts={len(changes)}")
    for cid, delta in changes:
        print(' -', cid, json.dumps(delta, ensure_ascii=False))


if __name__ == '__main__':
    main()
