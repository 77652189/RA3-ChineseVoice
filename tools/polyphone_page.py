"""Listening page for the polyphone candidates (work/polyphone/candidates.csv): the released dub of each line, the
character in question highlighted with the reading it should have, and a tick box for "read wrong".

  python -I -X utf8 tools/polyphone_page.py      -> work/polyphone/listen/index.html
"""
import csv
import html
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
from choose_takes import mp3 as _mp3  # noqa: E402
import choose_takes  # noqa: E402

OUT = os.path.join(ROOT, 'work', 'polyphone', 'listen')
TONE = str.maketrans('', '')


def marked(p):
    """CHOU2 -> chóu"""
    marks = {'1': '̄', '2': '́', '3': '̌', '4': '̀'}
    s, t = p[:-1].lower().replace('v', 'ü'), p[-1]
    if t not in marks:
        return s
    for v in ('a', 'e', 'ou'):
        if v in s:
            i = s.index(v)
            break
    else:
        i = max(s.rfind(c) for c in 'iouü')
    import unicodedata
    return unicodedata.normalize('NFC', s[:i + 1] + marks[t] + s[i + 1:])


def main():
    os.makedirs(OUT, exist_ok=True)
    choose_takes.OUT = OUT
    zh = {}
    for b in ('allied', 'soviet', 'empire', 'eva', 'commander', 'mission', 'movie'):
        for r in csv.DictReader(open(os.path.join(ROOT, 'lines', b + '.csv'), encoding='utf-8-sig')):
            zh[(b, r['asset'])] = r
    rows = list(csv.DictReader(open(os.path.join(ROOT, 'work', 'polyphone', 'candidates.csv'), encoding='utf-8-sig')))
    rows.sort(key=lambda r: (r['force'].split('=')[0], r['batch'], r['asset']))
    body = []
    for r in rows:
        line = zh[(r['batch'], r['asset'])]
        force = dict(x.split('=') for x in r['force'].split())
        text = ''.join(f'<mark>{html.escape(c)}</mark>' if c in force else html.escape(c) for c in line['zh'])
        want = '、'.join(f'{c} {marked(p)}' for c, p in force.items())
        src = _mp3(f'{r["asset"]}.mp3', os.path.join(ROOT, 'voices', r['batch'], r['asset'] + '.wav'))
        body.append(f'<tr data-a="{r["asset"]}"><td class=w>{html.escape(want)}</td><td><div class=zh>{text}</div>'
                    f'<div class=en>{html.escape(line.get("en", ""))} · {r["asset"]}</div></td>'
                    f'<td><audio controls preload=none src="{src}"></audio></td>'
                    f'<td><label><input type=checkbox> 念错了</label></td></tr>')
    doc = f'''<!doctype html><meta charset=utf-8><title>多音字试听</title>
<style>
:root{{--bg:#15171b;--fg:#ddd;--mut:#999;--line:#333;--hi:#e8b04a;--sel:#3a2a12}}
@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#222;--mut:#666;--line:#ddd;--hi:#b7791f;--sel:#fdf0d5}}}}
body{{font-family:"Microsoft YaHei UI",sans-serif;background:var(--bg);color:var(--fg);margin:24px}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
.zh{{font-size:18px}}.en{{color:var(--mut);font-size:13px;margin-top:2px}}.w{{white-space:nowrap;color:var(--hi);font-size:16px}}
mark{{background:none;color:var(--hi);font-weight:bold;text-decoration:underline}}audio{{width:240px;height:32px}}
tr.bad{{background:var(--sel)}}#bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:12px;align-items:center}}
button{{font-size:15px;padding:6px 14px}}
</style>
<h1>多音字试听（{len(rows)} 句，都是现在发布的配音）</h1>
<p>黄色标出的字应该读成左边的读音。听到念错的就勾上，最后点「复制结果」发给我；没勾的我当作没问题，不动。</p>
<div id=bar><button id=copy>复制结果</button><span id=n>已勾 0 句</span></div>
<table><tr><th>应读</th><th>台词</th><th>现在的配音</th><th></th></tr>
{chr(10).join(body)}
</table>
<script>
const KEY='polyphone-listen';let saved={{}};try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
const rows=[...document.querySelectorAll('tr[data-a]')];
function upd(){{const bad=rows.filter(r=>r.querySelector('input').checked);rows.forEach(r=>r.classList.toggle('bad',r.querySelector('input').checked));
document.getElementById('n').textContent='已勾 '+bad.length+' 句';const s={{}};bad.forEach(r=>s[r.dataset.a]=1);try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}return bad}}
rows.forEach(r=>{{const c=r.querySelector('input');c.checked=!!saved[r.dataset.a];c.onchange=upd}});upd();
document.getElementById('copy').onclick=async()=>{{const t='念错的：'+upd().map(r=>r.dataset.a).join(' ');try{{await navigator.clipboard.writeText(t)}}catch(e){{prompt('复制下面这行',t)}}document.getElementById('copy').textContent='已复制';}};
</script>'''
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('->', os.path.join(OUT, 'index.html'), len(rows))


if __name__ == '__main__':
    main()
