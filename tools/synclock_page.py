"""Listening page for the sync-locked lines that had to be sped up to the original length (tools/sync_lock.py,
ra3voice/fitlen.py): English original, our line before, and as built now (dist/ra3), with a tick box for "too rushed".
Lines only padded with silence or trimmed at the ends are left out: they sound the same as before.

  python -I -X utf8 tools/synclock_page.py      -> work/synclock/index.html   (after "ra3cv.py build --game ra3")
"""
import csv
import html
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import choose_takes                                           # noqa: E402
import ra3cv                                                  # noqa: E402
from ra3voice import audio_io, big, fitlen                    # noqa: E402
from ra3voice.game import AudioStream, chain_for_game         # noqa: E402

OUT = os.path.join(ROOT, 'work', 'synclock')
MIN_RATE = 1.05          # below this the speed-up is not audible


def main():
    os.makedirs(OUT, exist_ok=True)
    choose_takes.OUT = OUT
    stream = AudioStream(chain_for_game(ra3cv.GAMES['ra3']))
    locked = sorted(ra3cv.sync_locked('ra3'))
    files = ra3cv.voice_files(os.path.join(ROOT, 'voices'), 'ra3')
    text = {}
    for b in ('allied', 'soviet', 'empire', 'eva', 'commander', 'mission'):
        p = os.path.join(ROOT, 'lines', b + '.csv')
        if os.path.exists(p):
            for r in csv.DictReader(open(p, encoding='utf-8-sig')):
                text[r['asset'].lower()] = r
    originals = stream.read_cdata([stream.get(n) for n in locked])
    rows = []
    for n in locked:
        if n.lower() not in files:
            continue
        wav, comp = files[n.lower()]
        a = stream.get(n)
        ref, sr = stream.decode(a, originals[n])
        x = audio_io.match_level(audio_io.load_mono(wav, sr), ref)
        _, rate = fitlen.fit(x, len(ref), sr)
        if rate < MIN_RATE:
            continue
        blob = big.read_files(os.path.join(ROOT, 'dist', 'ra3', ra3cv.COMP_BIG.format(comp)), [a.cdata_path])[a.cdata_path]
        built, _ = stream.decode_replacement(a, blob)
        for tag, pcm in (('en', ref), ('before', audio_io.to_int16(x)), ('after', built)):
            audio_io.save_wav(os.path.join(OUT, f'{n}_{tag}.wav'), np.asarray(pcm, dtype=np.int16), sr)
        rows.append((rate, n, len(ref) / sr, len(x) / sr, len(built) / sr))
    rows.sort(reverse=True)
    body = []
    for rate, n, t_en, t_before, t_after in rows:
        r = text.get(n.lower(), {})
        au = lambda tag: (f'<audio controls preload=none src="{choose_takes.mp3(f"{n}_{tag}.mp3", os.path.join(OUT, f"{n}_{tag}.wav"))}">'
                          '</audio>')
        body.append(f'<tr data-a="{n}"><td class=r>快 {(rate - 1) * 100:.0f}%</td>'
                    f'<td><div class=zh>{html.escape(r.get("zh", ""))}</div><div class=en>{html.escape(r.get("en", ""))} · {n}'
                    f' · 原版 {t_en:.1f} 秒，之前 {t_before:.1f} 秒</div></td>'
                    f'<td>{au("en")}</td><td>{au("before")}</td><td>{au("after")}</td>'
                    f'<td><label><input type=checkbox> 太赶</label></td></tr>')
    for f in os.listdir(OUT):
        if f.endswith('.wav'):
            os.remove(os.path.join(OUT, f))
    doc = f'''<!doctype html><meta charset=utf-8><title>联机对齐试听</title>
<style>
:root{{--bg:#15171b;--fg:#ddd;--mut:#999;--line:#333;--hi:#e8b04a;--sel:#3a2a12}}
@media (prefers-color-scheme: light){{:root{{--bg:#fafafa;--fg:#222;--mut:#666;--line:#ddd;--hi:#b7791f;--sel:#fdf0d5}}}}
body{{font-family:"Microsoft YaHei UI",sans-serif;background:var(--bg);color:var(--fg);margin:24px}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
.zh{{font-size:18px}}.en{{color:var(--mut);font-size:13px;margin-top:2px}}.r{{white-space:nowrap;color:var(--hi);font-size:16px}}
audio{{width:200px;height:32px}}tr.bad{{background:var(--sel)}}
#bar{{position:sticky;top:0;background:var(--bg);padding:10px 0;display:flex;gap:12px;align-items:center}}button{{font-size:15px;padding:6px 14px}}
</style>
<h1>联机对齐：加速过的台词（{len(rows)} 句）</h1>
<p>这些剧情台词会被任务脚本等着播完，为了合作联机不同步，必须和英文原版一样长，所以压短了。只补静音的句子听起来没变化，没列出来。
听着太赶的勾上，最后点「复制结果」发给我，我改说法或重配；没勾的当作可以。</p>
<div id=bar><button id=copy>复制结果</button><span id=n>已勾 0 句</span></div>
<table><tr><th>加速</th><th>台词</th><th>英文原版</th><th>之前</th><th>现在</th><th></th></tr>
{chr(10).join(body)}
</table>
<script>
const KEY='synclock-listen';let saved={{}};try{{saved=JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{}}
const rows=[...document.querySelectorAll('tr[data-a]')];
function upd(){{const bad=rows.filter(r=>r.querySelector('input').checked);rows.forEach(r=>r.classList.toggle('bad',r.querySelector('input').checked));
document.getElementById('n').textContent='已勾 '+bad.length+' 句';const s={{}};bad.forEach(r=>s[r.dataset.a]=1);try{{localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}return bad}}
rows.forEach(r=>{{const c=r.querySelector('input');c.checked=!!saved[r.dataset.a];c.onchange=upd}});upd();
document.getElementById('copy').onclick=async()=>{{const t='太赶的：'+upd().map(r=>r.dataset.a).join(' ');try{{await navigator.clipboard.writeText(t)}}catch(e){{prompt('复制下面这行',t)}}document.getElementById('copy').textContent='已复制';}};
</script>'''
    open(os.path.join(OUT, 'index.html'), 'w', encoding='utf-8').write(doc)
    print('->', os.path.join(OUT, 'index.html'), len(rows), 'lines')


if __name__ == '__main__':
    main()
