"""Sampling QA for the dubs: a random sample of released lines, labelled by ear, gives the defect rate and the
labelled data the automatic judge is checked against.

  python -I -X utf8 tools/qa_sample.py page   r1 [--batch movie] [--n 100] [--seed 1]  -> work/qa/r1/index.html
  python -I -X utf8 tools/qa_sample.py ingest r1 "<the line the page copies>"            -> work/qa/r1/labels.csv

Each row plays the English original, then our dub; the listener marks it fine or ticks what is wrong. The same seed
gives the same sample, so a later round can re-check the same lines after a batch repair.
"""
import argparse
import csv
import html
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import choose_takes  # noqa: E402

TAGS = ['念错', '停顿怪', '语气不对', '音色不像', '杂音电音', '其他']


def released(batch):
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig')))
    return [r for r in rows if r.get('zh', '').strip() and os.path.exists(os.path.join(ROOT, 'voices', batch, r['asset'] + '.wav'))]


def page(rnd, batch, n, seed):
    out = os.path.join(ROOT, 'work', 'qa', rnd)
    os.makedirs(out, exist_ok=True)
    choose_takes.OUT = out
    rows = released(batch)
    sample = random.Random(seed).sample(rows, min(n, len(rows)))
    json.dump({'batch': batch, 'seed': seed, 'assets': [r['asset'] for r in sample]},
              open(os.path.join(out, 'sample.json'), 'w', encoding='utf-8'), indent=1)
    body = []
    for i, r in enumerate(sample, 1):
        a = r['asset']
        en = choose_takes.mp3(f'{a}_en.mp3', os.path.join(ROOT, 'original', batch, a + '.wav'))
        zh = choose_takes.mp3(f'{a}_zh.mp3', os.path.join(ROOT, 'voices', batch, a + '.wav'))
        tags = ''.join(f'<label><input type=checkbox value="{t}"> {t}</label>' for t in TAGS)
        body.append(f'<tr data-a="{a}"><td class=n>{i}</td><td><div class=zh>{html.escape(r["zh"])}</div>'
                    f'<div class=en>{html.escape(r["en"])}</div></td>'
                    f'<td><audio controls preload=none src="{en}"></audio></td>'
                    f'<td><audio controls preload=none src="{zh}"></audio></td>'
                    f'<td class=tags><label class=ok><input type=checkbox value="没问题"> 没问题</label>{tags}</td></tr>')
    doc = f'''<!doctype html><meta charset=utf-8><title>配音抽检 {rnd}</title>
<style>
:root{{--bg:#15171b;--fg:#ddd;--mut:#999;--line:#333;--hi:#e8b04a;--done:#1d2a1f}}
@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#222;--mut:#666;--line:#ddd;--hi:#b7791f;--done:#e9f5ec}}}}
body{{font-family:"Microsoft YaHei UI",sans-serif;background:var(--bg);color:var(--fg);margin:24px}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:7px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
.zh{{font-size:17px}}.en{{color:var(--mut);font-size:13px}}.n{{color:var(--mut)}}audio{{width:200px;height:30px}}
.tags label{{white-space:nowrap;margin-right:10px;font-size:14px}}.ok{{color:#5fbf73;font-weight:bold}}tr.done{{background:var(--done)}}
#bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:14px;align-items:center;z-index:1}}button{{font-size:15px;padding:6px 14px}}
</style>
<h1>配音抽检（随机 {len(sample)} 句过场，都是现在发布的版本）</h1>
<p>每句先听英文原声，再听中文配音。没毛病就勾「没问题」，有毛病就勾对应的类型（可多选）。不用纠结，凭第一感觉。全部标完点「复制结果」发给我。</p>
<div id=bar><button id=copy>复制结果</button><span id=n></span></div>
<table><tr><th></th><th>台词</th><th>英文原声</th><th>中文配音</th><th>标记</th></tr>
{chr(10).join(body)}
</table>
<script>
const KEY='qa-{rnd}';let saved={{}};try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
const rows=[...document.querySelectorAll('tr[data-a]')];
function state(){{const s={{}};rows.forEach(r=>{{const v=[...r.querySelectorAll('input:checked')].map(c=>c.value);if(v.length)s[r.dataset.a]=v;r.classList.toggle('done',v.length>0)}});return s}}
function upd(){{const s=state();document.getElementById('n').textContent='已标 '+Object.keys(s).length+' / '+rows.length;try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}return s}}
rows.forEach(r=>{{(saved[r.dataset.a]||[]).forEach(v=>{{const c=r.querySelector('input[value="'+v+'"]');if(c)c.checked=true}});
 r.querySelectorAll('input').forEach(c=>c.onchange=()=>{{if(c.checked&&c.value==='没问题')r.querySelectorAll('input').forEach(o=>{{if(o!==c)o.checked=false}});
  if(c.checked&&c.value!=='没问题')r.querySelector('input[value="没问题"]').checked=false;upd()}})}});upd();
document.getElementById('copy').onclick=async()=>{{const s=upd();const t='QA {rnd}: '+Object.entries(s).map(([a,v])=>a+'='+v.join('+')).join(' ');
 try{{await navigator.clipboard.writeText(t)}}catch(e){{prompt('复制下面这行',t)}}document.getElementById('copy').textContent='已复制';}};
</script>'''
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('->', os.path.join(out, 'index.html'), len(sample))


def ingest(rnd, text):
    out = os.path.join(ROOT, 'work', 'qa', rnd)
    sample = json.load(open(os.path.join(out, 'sample.json'), encoding='utf-8'))
    got = dict(x.split('=', 1) for x in text.split(':', 1)[1].split())
    rows = [{'asset': a, 'ok': int(got.get(a) == '没问题'), 'tags': got.get(a, '') if got.get(a) != '没问题' else '',
             'labelled': int(a in got)} for a in sample['assets']]
    with open(os.path.join(out, 'labels.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    lab = [r for r in rows if r['labelled']]
    bad = [r for r in lab if not r['ok']]
    print(f'{len(lab)} labelled, {len(bad)} with a defect ({len(bad) / max(1, len(lab)):.0%})')
    from collections import Counter
    print(Counter(t for r in bad for t in r['tags'].split('+')))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['page', 'ingest'])
    ap.add_argument('round')
    ap.add_argument('text', nargs='?')
    ap.add_argument('--batch', default='movie')
    ap.add_argument('--n', type=int, default=100)
    ap.add_argument('--seed', type=int, default=1)
    a = ap.parse_args()
    page(a.round, a.batch, a.n, a.seed) if a.cmd == 'page' else ingest(a.round, a.text)
