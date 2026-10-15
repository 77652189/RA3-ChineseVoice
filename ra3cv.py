"""RA3 / Uprising Chinese voice mod tool.

  python ra3cv.py build [--game ra3|uprising|all] [--test-on JUImper_Voi]
        pack voices/<batch>/<Asset>.wav into dist/<game>/CNVoice_<batch>.big (one archive per component)
        plus dist/<game>/core/CNVoice_core_<letters>.big (audio.bin for every combination of components)
        <Asset>@ra3.wav / <Asset>@uprising.wav override the shared file for that game only
  python ra3cv.py preview [batch ...]   A/B listening pages decoded from dist/ -> preview/
  python ra3cv.py release               assemble release/<name>/ + zip (installer, readme, archives)
  python ra3cv.py install / uninstall [--components allied,eva]   run the release installer here
"""
import argparse
import csv
import glob
import html
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from ra3voice import audio_io, big, snr, textpack                     # noqa: E402
from ra3voice.game import AudioStream, chain_for_game          # noqa: E402

GAMES = {
    'uprising': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising',
    'ra3': r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3',
}
# one archive per component, plus one "core" archive holding the audio.bin that matches the chosen
# set of components (the engine trusts the sample counts in audio.bin, so it must match exactly)
COMPONENTS = ['allied', 'soviet', 'empire', 'eva', 'commander', 'mission']
LETTER = {'allied': 'a', 'soviet': 's', 'empire': 'e', 'eva': 'v', 'commander': 'c', 'mission': 'm'}
COMP_BIG = 'CNVoice_{}.big'
CORE_BIG = 'CNVoice_core.big'
# text component: simplified string tables + fonts with simplified characters (no audio, no core)
TEXT = 'text'
FONT_DIR = os.path.join(ROOT, 'third_party', 'fonts', 'out')
FONT_LICENSE = os.path.join(ROOT, 'third_party', 'fonts', 'OFL.txt')


def core_name(combo):
    return 'CNVoice_core_' + ''.join(LETTER[c] for c in COMPONENTS if c in combo) + '.big'


def combos(comps):
    from itertools import combinations
    return [set(c) for r in range(1, len(comps) + 1) for c in combinations(comps, r)]
MOD_VERSION = '1.0'
RELEASE_NAME = f'红警3中文配音MOD_v{MOD_VERSION}'
SETUP_EXE = '红警3中文配音安装器.exe'
# hosted update manifest (manifest.json + patch folders); empty = the installer hides the update button
UPDATE_URL = os.environ.get('CNVOICE_UPDATE_URL', 'https://github.com/77652189/RA3-ChineseVoice/releases/latest/download/manifest.json')
# URL prefixes tried after a direct download fails (e.g. a GitHub download proxy); later manifests can change them
UPDATE_MIRRORS = []
BATCH_NAMES = {'allied': '盟军', 'soviet': '苏联', 'empire': '帝国', 'eva': '播报', 'commander': '指挥官', 'mission': '剧情对白'}
TEXT_NAME = '简体中文文字（界面、字幕）'
# movie component: whole .snd files of EnglishMovieAudio.big with the dialogue re-dubbed (no core)
MOVIE = 'movie'
MOVIE_NAME = '过场视频（剧情、简报、通话）'
# optional frame-rate unlock: SAGE-Unlocked (GPL-3.0, https://github.com/TheeHorse/SAGE-Unlocked), redistributed unmodified
FPS = 'fps'
FPS_NAME = '高帧率 120 帧（SAGE-Unlocked）'
FPS_DIR = os.path.join(ROOT, 'third_party', 'sage-unlocked')
FPS_VERSION = 'v1.9.5'
FPS_FILES = ('d3d9.dll', 'CnCFpsUnlocker.dll', 'SAGEUnlocked.ini')


TERM_MAP = os.path.join(ROOT, 'work', 'terms', 'term_map.json')
UI_EXTRA = os.path.join(ROOT, 'work', 'terms', 'untranslated_zh.json')   # strings the official release left in English


def read_rows(batch):
    path = os.path.join(ROOT, 'lines', batch + '.csv')
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def missing_glyphs(files):
    """Characters in the built string tables that our fonts cannot draw (they would show as boxes)."""
    from fontTools.ttLib import TTFont
    from ra3voice import csf, refpack
    cmap = TTFont(os.path.join(FONT_DIR, textpack.FONT_FILES[0])).getBestCmap()
    used = set()
    for name, blob in files:
        if name.endswith('.csf'):
            for t in csf.parse(refpack.decompress(blob)).values():
                used |= set(t)
    return sorted(c for c in used if ord(c) >= 0x2E80 and ord(c) not in cmap)


def build_text(game):
    """Simplified string tables for one game: glossary terms + subtitles taken from the dub scripts."""
    files = _build_text(game)
    miss = missing_glyphs(files)
    if miss:
        sys.exit(f'{game}: {len(miss)} characters missing from the fonts: {"".join(miss[:50])} '
                 f'-> run python tools/make_fonts.py')
    return files


def _build_text(game):
    return textpack.text_files(chain_for_game(GAMES[game], 'chinese_t'), FONT_DIR, terms=textpack.Terms(TERM_MAP),
                               en_chain=chain_for_game(GAMES[game], 'english'), mission_rows=read_rows('mission'),
                               movie_rows=[r for r in read_rows('movie') if r['games'] == game],
                               extra=json.load(open(UI_EXTRA, encoding='utf-8')) if os.path.exists(UI_EXTRA) else None)


def _movie_job(job):
    from ra3voice import movie
    import numpy as np
    pack, name, spec, voc_path = job
    snd = big.read_files(pack, [name])[name]
    lines = [(s, d, audio_io.load_mono(p, movie.SR)) for s, d, p in spec]
    voc = np.load(voc_path) if os.path.exists(voc_path) else None   # tools/separate_movies.py
    new, report = movie.build(snd, lines, voc)
    return name, new, report, voc is not None


MOVIE_CACHE = os.path.join(ROOT, 'work', 'movie_cache')


MOVIE_OFFSETS = os.path.join(ROOT, 'work', 'movie_offsets.json')


def movie_offsets():
    """{asset: seconds} where the actor speaks well after the subtitle time (measured on the separated vocals):
    the dub and its removal window move, the subtitle keeps the game's timing."""
    if not os.path.exists(MOVIE_OFFSETS):
        return {}
    return {k: float(v) for k, v in json.load(open(MOVIE_OFFSETS, encoding='utf-8')).items() if not k.startswith('_')}


def movie_jobs(game, voices_dir):
    """[(pack, snd name, [(start, dur, wav)], vocals .npy)] for every movie of a game with dubbed lines."""
    path = os.path.join(ROOT, 'lines', 'movie.csv')
    if not os.path.exists(path):
        return [], {}
    with open(path, encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['games'] == game]
    shift = movie_offsets()
    by_movie = {}
    for r in rows:
        wav = os.path.join(voices_dir, MOVIE, r['asset'] + '.wav')
        if os.path.exists(wav):
            by_movie.setdefault(r['movie'], []).append((float(r['start']) + shift.get(r['asset'], 0.0), float(r['dur']), wav))
    pack = os.path.join(GAMES[game], 'Data', 'EnglishMovieAudio.big')
    sep = os.path.join(ROOT, 'work', 'sep', game)
    jobs = [(pack, 'data\\movies\\' + m + '.snd', sorted(v), os.path.join(sep, m + '.npy'))
            for m, v in sorted(by_movie.items())]
    return jobs, by_movie


def movie_cache_key(job):
    """Changes whenever a movie's dubs, its separated vocals or the assembly code change."""
    import hashlib

    def stamp(p):
        # content, not mtime: fx.py rewrites every voice file even when nothing in it changed
        if not os.path.exists(p):
            return f'{p}|-'
        if p.endswith('.npy'):        # separated vocals: large, written once per movie by separate_movies.py
            return f'{p}|{os.path.getsize(p)}|{int(os.path.getmtime(p))}'
        return f'{p}|' + hashlib.sha1(open(p, 'rb').read()).hexdigest()
    pack_, name_, spec, voc = job
    h = hashlib.sha256(b''.join(open(os.path.join(ROOT, 'ra3voice', f), 'rb').read()
                                for f in ('movie.py', 'eaxa.py', 'stretch.py')))
    h.update('\n'.join([name_, stamp(voc)] + [f'{s}|{d}|{stamp(p)}' for s, d, p in spec]).encode('utf-8'))
    return h.hexdigest()


def build_movies(game, voices_dir, out):
    """dist/<game>/CNVoice_movie.big from voices/movie/<asset>.wav and lines/movie.csv. Returns stats."""
    from concurrent.futures import ProcessPoolExecutor
    jobs, by_movie = movie_jobs(game, voices_dir)
    if not jobs:
        return {}
    cache = os.path.join(MOVIE_CACHE, game)
    os.makedirs(cache, exist_ok=True)
    key = movie_cache_key
    results, todo = {}, []
    for j in jobs:
        base = os.path.join(cache, os.path.basename(j[1]))
        k = key(j)
        if os.path.exists(base) and os.path.exists(base + '.json'):
            meta = json.load(open(base + '.json', encoding='utf-8'))
            if meta['key'] == k:
                results[j[1]] = (open(base, 'rb').read(), meta['report'], meta['separated'])
                continue
        todo.append((j, base, k))
    if todo:
        with ProcessPoolExecutor(max(1, (os.cpu_count() or 2) - 2)) as ex:
            for (j, base, k), (name, new, report, separated) in zip(todo, ex.map(_movie_job, [t[0] for t in todo])):
                open(base, 'wb').write(new)
                json.dump({'key': k, 'report': report, 'separated': separated}, open(base + '.json', 'w', encoding='utf-8'))
                results[name] = (new, report, separated)
    files, sped, cut, unseparated = [], 0, 0, 0
    for j in jobs:
        new, report, separated = results[j[1]]
        files.append((j[1], new))
        unseparated += not separated
        sped += sum(1 for _, rate, _ in report if rate > 1.001)
        cut += sum(1 for _, _, c in report if c > 0)
    big.write(os.path.join(out, COMP_BIG.format(MOVIE)), files)
    return {'movies': len(files), 'lines': sum(len(v) for v in by_movie.values()), 'sped up': sped, 'cut': cut,
            'without vocal separation': unseparated, 'reassembled': len(todo)}


def load_units():
    with open(os.path.join(ROOT, 'units.json'), encoding='utf-8') as f:
        return json.load(f)


def voice_files(voices_dir, game):
    """{asset_lower: (wav path, component)} for a game; <Asset>@<game>.wav beats the shared <Asset>.wav."""
    found = {}
    for p in glob.glob(os.path.join(voices_dir, '*', '*.wav')):
        comp = os.path.basename(os.path.dirname(p))
        stem = os.path.splitext(os.path.basename(p))[0]
        name, _, only = stem.partition('@')
        if only and only != game:
            continue
        if only or name.lower() not in found:
            found[name.lower()] = (p, comp)
    return found


def test_redirects(stream, jobs, prefix):
    """Test builds only: also put each voice clip on a cheap unit's line of the same kind,
    e.g. IUGigaF_voiSelecta -> JUImper_VoiSelecta, so it can be heard right after game start."""
    taken = {a.short_name.lower() for a, _ in jobs}
    extra = []
    for a, p in jobs:
        suffix = a.short_name.split('_', 1)[1]
        if suffix.lower().startswith('voi'):
            suffix = suffix[3:]
        target = (prefix + suffix).lower()
        if target in stream.by_name and target not in taken:
            extra.append((stream.by_name[target], p))
            taken.add(target)
    print(f'test mode: {len(extra)} clips also mapped onto {prefix}*')
    return extra


def build_game(game, args):
    stream = AudioStream(chain_for_game(GAMES[game]))
    files = voice_files(args.voices, game)
    jobs = [(stream.by_name[k], p, c) for k, (p, c) in sorted(files.items()) if k in stream.by_name]
    if args.test_on:
        extra = test_redirects(stream, [(a, p) for a, p, _ in jobs], args.test_on)
        comp_of = {p: c for _, p, c in jobs}
        jobs += [(a, p, comp_of[p]) for a, p in extra]
    originals = stream.read_cdata([a for a, _, _ in jobs])
    by_comp = {}
    for a, p, c in jobs:
        ref, sr = stream.decode(a, originals[a.short_name])
        x = audio_io.load_mono(p, sr)
        if not args.no_level:
            x = audio_io.match_level(x, ref)
        by_comp.setdefault(c, {})[a.short_name] = audio_io.to_int16(x)
    out = os.path.join(ROOT, 'dist', game)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, 'core'))
    comps = [c for c in COMPONENTS if c in by_comp]
    for c in comps:
        big.write(os.path.join(out, COMP_BIG.format(c)), stream.cdata_files(by_comp[c]))
    for combo in combos(comps):
        lengths = {n: len(pcm) for c in combo for n, pcm in by_comp[c].items()}
        big.write(os.path.join(out, 'core', core_name(combo)), [stream.bin_file(lengths)])
    text = build_text(game)
    big.write(os.path.join(out, COMP_BIG.format(TEXT)), text)
    movies = build_movies(game, args.voices, out)
    audio_big = os.path.join(GAMES[game], 'Data', 'EnglishAudio.big')
    info = {'clips': sum(len(v) for v in by_comp.values()), 'components': {c: len(by_comp[c]) for c in comps},
            'text files': [n for n, _ in text], 'movie': movies,
            'test_build': bool(args.test_on), 'EnglishAudio.big size': os.path.getsize(audio_big)}
    json.dump(info, open(os.path.join(out, 'build.json'), 'w', encoding='utf-8'), indent=1)
    print(f'{game}: {info["components"]} -> {out} ({len(combos(comps))} core variants)' + ('  [TEST BUILD]' if args.test_on else ''))


def cmd_build(args):
    for g in (GAMES if args.game == 'all' else [args.game]):
        build_game(g, args)


def load_lines():
    lines = {}
    for p in glob.glob(os.path.join(ROOT, 'lines', '*.csv')):
        if p.endswith('_qc.csv'):
            continue
        batch = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                r['batch'] = batch
                lines[r['asset'].lower()] = r
    return lines


PAGE_CSS = '''body{font:14px system-ui,sans-serif;margin:0;padding:16px;background:#111;color:#ddd}
a{color:#8ab4f8}h2{font-size:18px;margin:0 0 4px}p{color:#999;margin:0 0 16px}
h3{font-size:15px;margin:20px 0 8px;color:#bbb}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.card{background:#1c1c1c;border:1px solid #333;border-radius:8px;padding:10px}
code{color:#8ab4f8;font-size:12px}.zh{font-size:17px;margin:6px 0 2px}.en{color:#999;margin-bottom:8px}
.ab{display:flex;align-items:center;gap:8px;margin-top:4px}.ab span{width:76px;flex:none;color:#aaa;font-size:12px}
audio{height:32px;width:100%;min-width:0}
.warn{color:#f0b429;font-size:13px;margin:4px 0}.card.flag{border-color:#f0b429}'''


def cmd_preview(args):
    """Decode what the built mods will actually play and write A/B pages per batch and voice group."""
    lines = load_lines()
    batches = args.batches or sorted({r['batch'] for r in lines.values()})
    out = os.path.join(ROOT, 'preview')
    sources = {}  # asset_lower -> (game, stream)
    mods = {}
    for g in ('ra3', 'uprising'):  # uprising last so it wins where both exist
        comp_bigs = glob.glob(os.path.join(ROOT, 'dist', g, COMP_BIG.format('*')))
        if not comp_bigs:
            continue
        stream = AudioStream(chain_for_game(GAMES[g]))
        by_cdata = {a.cdata_path.lower(): a for a in stream.assets}
        mods[g] = (None, stream)
        for mod in comp_bigs:
            for n, _, _ in big.read_index(mod):
                if n.lower() in by_cdata:
                    sources[by_cdata[n.lower()].short_name.lower()] = (g, n, mod)
    index = []
    for b in batches:
        os.makedirs(os.path.join(out, b, 'mod'), exist_ok=True)
        os.makedirs(os.path.join(out, b, 'orig'), exist_ok=True)
        rows = [r for r in lines.values() if r['batch'] == b and r['asset'].lower() in sources]
        for g, (_, stream) in mods.items():
            mine = [r for r in rows if sources[r['asset'].lower()][0] == g]
            if not mine:
                continue
            files = {}
            for mod in {sources[r['asset'].lower()][2] for r in mine}:
                files.update(big.read_files(mod, [sources[r['asset'].lower()][1] for r in mine
                                                  if sources[r['asset'].lower()][2] == mod]))
            originals = stream.read_cdata([stream.get(r['asset']) for r in mine])
            for r in mine:
                pcm, sr = stream.decode_replacement(stream.get(r['asset']), files[sources[r['asset'].lower()][1]])
                audio_io.save_wav(os.path.join(out, b, 'mod', r['asset'] + '.wav'), pcm, sr)
                o, osr = stream.decode(stream.get(r['asset']), originals[stream.get(r['asset']).short_name])
                audio_io.save_wav(os.path.join(out, b, 'orig', r['asset'] + '.wav'), o, osr)
                r['_d'] = (len(o) / osr, len(pcm) / sr)
        qc = {}
        qc_path = os.path.join(ROOT, 'lines', f'{b}_qc.csv')
        if os.path.exists(qc_path):
            with open(qc_path, encoding='utf-8-sig') as f:
                qc = {q['asset']: q for q in csv.DictReader(f) if q['flag']}
        groups = {}
        for r in sorted(rows, key=lambda r: r['asset'].lower()):
            groups.setdefault(r['group'], []).append(r)
        body = ''
        for grp, rs in groups.items():
            body += f'<h3 id="{html.escape(grp)}">{html.escape(grp.strip("_"))}（{len(rs)} 条）</h3><div class="grid">'
            for r in rs:
                od, nd = r['_d']
                n = r['asset']
                warn = ''
                if n in qc:
                    why = '、'.join({'READ': '读音', 'PAUSE': '断句', 'LONG': '偏长', 'CHECK': '待查'}.get(k, k)
                                   for k in qc[n]['flag'].split('+'))
                    warn = (f'<div class="warn">⚠ 自动质检（{why}）：识别成「{html.escape(qc[n]["heard"])}」'
                            f'，{qc[n]["new_s"]}s / 原版 {qc[n]["orig_s"]}s</div>')
                body += (f'<div class="card{" flag" if warn else ""}" id="{html.escape(n)}"><code>{html.escape(n)}</code>{warn}'
                         f'<div class="zh">{html.escape(r["zh"]) or "（无台词）"}</div><div class="en">{html.escape(r["en"])}</div>'
                         f'<div class="ab"><span>原版 {od:.2f}s</span><audio controls preload="none" src="orig/{n}.wav"></audio></div>'
                         f'<div class="ab"><span>中文 {nd:.2f}s</span><audio controls preload="none" src="mod/{n}.wav"></audio></div></div>')
            body += '</div>'
        flagged = ''
        if qc:
            flagged = ('<p class="warn">⚠ 优先听这几条（自动质检没通过）：'
                       + '、'.join(f'<a href="#{html.escape(a)}">{html.escape(a)}</a>' for a in sorted(qc)) + '</p>')
        toc = ' · '.join(f'<a href="#{html.escape(g)}">{html.escape(g.strip("_"))}</a>' for g in groups)
        title = BATCH_NAMES.get(b, b)
        page = (f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{title}配音试听</title><style>{PAGE_CSS}</style>'
                f'<p><a href="../index.html">← 全部</a></p><h2>{title} · 中文配音试听（{len(rows)} 条）</h2>'
                f'<p>"中文"一行播放的是从 mod 包里解码出来的音频，和游戏里听到的一样。</p>{flagged}<p>{toc}</p>{body}')
        with open(os.path.join(out, b, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(page)
        index.append((b, title, len(rows), len(groups)))
        print(f'{b}: {len(rows)} clips -> preview/{b}/index.html')
    existing = {}
    for b in BATCH_NAMES:
        if os.path.exists(os.path.join(out, b, 'index.html')) and b not in [i[0] for i in index]:
            existing[b] = True
    links = ''.join(f'<li><a href="{b}/index.html">{t}</a>（{n} 条，{g} 组）</li>' for b, t, n, g in index)
    links += ''.join(f'<li><a href="{b}/index.html">{BATCH_NAMES[b]}</a></li>' for b in existing)
    with open(os.path.join(out, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(f'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>配音试听</title><style>{PAGE_CSS}</style><h2>中文配音试听</h2><ul>{links}</ul>')


# three downloads, so nobody has to guess: one per game, and a full one for "not sure which I have"
EDITIONS = [('完整版', ['ra3', 'uprising']), ('原版', ['ra3']), ('起义时刻', ['uprising'])]
EDITION_HINT = {'完整版': '原版《红色警戒3》和《起义时刻》都包含，不确定自己是哪个版本就用这个。',
                '原版': '只包含原版《红色警戒3》。如果你玩的是《起义时刻》，请下载「起义时刻」版或「完整版」。',
                '起义时刻': '只包含《起义时刻》。如果你玩的是原版《红色警戒3》，请下载「原版」或「完整版」。'}


def release_dir(edition='完整版'):
    return os.path.join(ROOT, 'release', f'{RELEASE_NAME}_{edition}')


def verify_dist_matches_patch(patch):
    """A full package rebuilt from a patch must hold exactly what that patch delivers (files and cores)."""
    import hashlib
    src = os.path.join(PATCH_DIR, patch['build'])
    for g, info in patch['games'].items():
        for f in info['files']:
            pbig = os.path.join(src, f['path'])
            names = [n for n, _, _ in big.read_index(pbig)]
            want = big.read_files(pbig, names)
            got = big.read_files(os.path.join(ROOT, 'dist', g, COMP_BIG.format(f['component'])), names)
            bad = [n for n in names if got.get(n) != want[n]]
            if bad:
                sys.exit(f'dist/{g} differs from patch {patch["build"]} ({f["component"]}: {len(bad)} files); rebuild the patch')
        for letters, c in info['core'].items():
            p = os.path.join(ROOT, 'dist', g, 'core', f'CNVoice_core_{letters}.big')
            if hashlib.sha256(open(p, 'rb').read()).hexdigest() != c['sha256']:
                sys.exit(f'dist/{g} core {letters} differs from patch {patch["build"]}; rebuild the patch')


def cmd_release(args):
    global MOD_VERSION, RELEASE_NAME
    # --from-patch: the full package equals <base release> + that patch and keeps the patch's build, version and
    # base, so later patches (always cumulative against the base release) apply to it as to a patched install
    patch = None
    if args.from_patch:
        patch = json.load(open(os.path.join(PATCH_DIR, args.from_patch, 'patch.json'), encoding='utf-8'))
        verify_dist_matches_patch(patch)
        MOD_VERSION = patch['version']
        RELEASE_NAME = f'红警3中文配音MOD_v{MOD_VERSION}'
    for g in GAMES:
        info = json.load(open(os.path.join(ROOT, 'dist', g, 'build.json'), encoding='utf-8'))
        if info['test_build']:
            sys.exit(f'dist/{g} is a TEST build; run "python ra3cv.py build" first')
    import hashlib
    sys.path.insert(0, os.path.join(ROOT, 'tools'))
    import build_installer
    sys.argv = [sys.argv[0]]
    build_installer.main()
    exe = os.path.join(build_installer.OUT, build_installer.EXE)
    exe_sha = hashlib.sha256(open(exe, 'rb').read()).hexdigest()
    inst = os.path.join(ROOT, 'installer')
    # old single-package layout
    shutil.rmtree(os.path.join(ROOT, 'release', RELEASE_NAME), ignore_errors=True)
    if os.path.exists(os.path.join(ROOT, 'release', RELEASE_NAME + '.zip')):
        os.remove(os.path.join(ROOT, 'release', RELEASE_NAME + '.zip'))
    import datetime
    build_id = patch['build'] if patch else datetime.datetime.now().strftime('%Y%m%d-%H%M')   # same for all editions
    sizes = {}
    import listen_index   # tools/ is on sys.path (build_installer above)
    listen_rows = {g: listen_index.entries(g, AudioStream(chain_for_game(GAMES[g])), COMP_BIG) for g in GAMES}
    for edition, games in EDITIONS:
        rel = release_dir(edition)
        shutil.rmtree(rel, ignore_errors=True)
        os.makedirs(os.path.join(rel, 'files'))
        pkg = {'version': MOD_VERSION, 'edition': edition, 'build': build_id, 'update_url': UPDATE_URL, 'update_mirrors': UPDATE_MIRRORS, 'core': CORE_BIG, 'component_big': COMP_BIG,
               'components': [{'id': c, 'name': BATCH_NAMES[c], 'letter': LETTER[c], 'kind': 'voice'} for c in COMPONENTS]
                             + [{'id': MOVIE, 'name': MOVIE_NAME, 'kind': 'movie'}] * all(
                                 os.path.exists(os.path.join(ROOT, 'dist', g, COMP_BIG.format(MOVIE))) for g in games)
                             + [{'id': TEXT, 'name': TEXT_NAME, 'kind': 'text'}]
                             + [{'id': FPS, 'name': FPS_NAME, 'kind': 'fps'}], 'games': {}}
        if patch:
            pkg['base'] = patch['base']
        for g in games:
            src = os.path.join(ROOT, 'dist', g)
            os.makedirs(os.path.join(rel, 'files', g, 'core'))
            for f in glob.glob(os.path.join(src, COMP_BIG.format('*'))):
                shutil.copyfile(f, os.path.join(rel, 'files', g, os.path.basename(f)))
            for f in glob.glob(os.path.join(src, 'core', '*.big')):
                shutil.copyfile(f, os.path.join(rel, 'files', g, 'core', os.path.basename(f)))
            pkg['games'][g] = json.load(open(os.path.join(src, 'build.json'), encoding='utf-8'))
        shutil.copyfile(FONT_LICENSE, os.path.join(rel, 'files', '字体许可证_OFL.txt'))
        os.makedirs(os.path.join(rel, 'files', FPS))
        for f in FPS_FILES + ('LICENSE.txt',):
            shutil.copyfile(os.path.join(FPS_DIR, f), os.path.join(rel, 'files', FPS, f))
        with open(os.path.join(rel, 'files', FPS, '来源说明.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
            f.write(f'帧率解锁插件 SAGE-Unlocked {FPS_VERSION}，作者 TheeHorse，以 GPL-3.0 发布（许可证见 LICENSE.txt）。\n'
                    '本 MOD 原样附带、未作修改。源代码：https://github.com/TheeHorse/SAGE-Unlocked\n'
                    f'（对应版本：https://github.com/TheeHorse/SAGE-Unlocked/releases/tag/{FPS_VERSION}）\n')
        json.dump(pkg, open(os.path.join(rel, 'files', 'package.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        # PowerShell 5.1 needs a BOM to read UTF-8 scripts; .bat files stay ASCII
        with open(os.path.join(inst, 'installer.ps1'), encoding='utf-8') as f:
            ps1 = f.read()
        with open(os.path.join(rel, 'files', 'installer.ps1'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
            f.write(ps1)
        # the GUI installer sits at the top; the PowerShell installer stays in files\ as a fallback
        shutil.copyfile(exe, os.path.join(rel, SETUP_EXE))
        for src, dst in (('install.bat', '备用-安装.bat'), ('uninstall.bat', '备用-卸载.bat')):
            with open(os.path.join(inst, src), encoding='ascii') as f:
                bat = f.read().replace('%~dp0files\\installer.ps1', '%~dp0installer.ps1')
            with open(os.path.join(rel, 'files', dst), 'w', encoding='ascii', newline='\r\n') as f:
                f.write(bat)
        with open(os.path.join(inst, 'README.txt'), encoding='utf-8') as f:
            readme = (f.read().replace('{VERSION}', MOD_VERSION).replace('{SETUP_EXE}', SETUP_EXE)
                      .replace('{SETUP_SHA256}', exe_sha).replace('{EDITION}', edition)
                      .replace('{EDITION_HINT}', EDITION_HINT[edition]))
        with open(os.path.join(rel, '说明.txt'), 'w', encoding='utf-8-sig', newline='\r\n') as f:
            f.write(readme)
        # the installer's 试听 window plays lines straight out of files/<game>/*.big; this is only the index
        print(f'listen index [{edition}]: {listen_index.write(os.path.join(rel, "files"), listen_rows, games)} lines')
        zpath = rel + '.zip'
        with zipfile.ZipFile(zpath, 'w', zipfile.ZIP_DEFLATED) as z:
            for dirpath, _, fnames in os.walk(rel):
                for fn in fnames:
                    full = os.path.join(dirpath, fn)
                    z.write(full, os.path.relpath(full, os.path.dirname(rel)))
        print(f'release [{edition}] -> {zpath} ({os.path.getsize(zpath) / 1e6:.1f} MB)')
        sizes[edition] = os.path.getsize(zpath)
    write_publish_copy(sizes, exe_sha)
    if patch:
        print(f'no release index: later patches keep diffing against base {patch["base"]}')
        return
    index = os.path.join(RELEASE_INDEX, build_id + '.json')
    os.makedirs(RELEASE_INDEX, exist_ok=True)
    json.dump({'build': build_id, 'version': MOD_VERSION, 'games': {g: dist_index(g) for g in GAMES}},
              open(index, 'w', encoding='utf-8'), indent=0)
    print(f'release index -> {index} (keep it: tools for future update patches diff against it)')


# ---------------------------------------------------------------- update patches
# Updates are small archives that the installer adds in front of the release archives (the first archive
# that has a file wins): every file that changed since a release, plus that build's audio.bin cores.
# A patch is cumulative against its base release, so a player downloads one patch whatever they missed.
RELEASE_INDEX = os.path.join(ROOT, 'releases')       # <build>.json: per-archive file hashes of each release
PATCH_DIR = os.path.join(ROOT, 'patches')
PATCH_NAME = 'CNVoice_patch_{}.big'     # placed right in front of CNVoice_<component>.big


def dist_index(game):
    import hashlib
    out = {}
    for path in sorted(glob.glob(os.path.join(ROOT, 'dist', game, COMP_BIG.format('*')))):
        names = [n for n, _, _ in big.read_index(path)]
        files = big.read_files(path, names)
        out[os.path.basename(path)] = {n: hashlib.sha1(b).hexdigest() for n, b in files.items()}
    return out


def cmd_patch(args):
    """patches/<build>/: per game, one archive per changed component with the files that changed since the
    base release, plus all cores; manifest entry patches/<build>/patch.json (add it to the hosted manifest.json)."""
    import datetime
    import hashlib
    base = json.load(open(os.path.join(RELEASE_INDEX, args.base + '.json'), encoding='utf-8'))
    build_id = datetime.datetime.now().strftime('%Y%m%d-%H%M')
    out = os.path.join(PATCH_DIR, build_id)
    shutil.rmtree(out, ignore_errors=True)
    entry = {'build': build_id, 'version': args.version, 'base': args.base, 'notes': args.notes, 'games': {}}

    def describe(path):
        # flat names: GitHub release assets cannot live in folders
        return {'path': os.path.basename(path), 'size': os.path.getsize(path),
                'sha256': hashlib.sha256(open(path, 'rb').read()).hexdigest()}
    for g in GAMES:
        old = base['games'].get(g, {})
        new = dist_index(g)
        os.makedirs(out, exist_ok=True)
        files = []
        for arc, names in new.items():
            comp = arc[len('CNVoice_'):-len('.big')]
            diff = [n for n, h in names.items() if old.get(arc, {}).get(n) != h]
            if not diff:
                continue
            # one patch per component, so a player only ever adds patches for what they installed
            # (a mission-line patch on top of a core without the mission lengths would cut those lines)
            p = os.path.join(out, f'{g}_' + PATCH_NAME.format(comp))
            big.write(p, list(big.read_files(os.path.join(ROOT, 'dist', g, arc), diff).items()))
            files.append(dict(describe(p), name=PATCH_NAME.format(comp), component=comp, entries=len(diff)))
        cores = {}
        for p in glob.glob(os.path.join(ROOT, 'dist', g, 'core', '*.big')):
            q = os.path.join(out, f'{g}_' + os.path.basename(p))
            shutil.copyfile(p, q)
            cores[os.path.basename(p)[len('CNVoice_core_'):-len('.big')]] = describe(q)
        entry['games'][g] = {'files': files, 'core': cores}
        print(f'{g}: ' + (', '.join(f"{f['component']} {f['entries']} files {f['size'] / 1e6:.1f} MB" for f in files) or 'no changes'))
    json.dump(entry, open(os.path.join(out, 'patch.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    # the hosted manifest only needs the newest patch: patches are cumulative against their base release
    json.dump({'patches': [entry], 'mirrors': UPDATE_MIRRORS}, open(os.path.join(out, 'manifest.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    print(f'patch -> {out}  (publish every file of this folder as one GitHub release, see HANDOFF.md)')


PUBLISH_DIR = os.path.join(ROOT, 'docs', 'publish')   # B 站简介、GitHub Release 说明、网盘文案的模板
REPO_URL = 'https://github.com/77652189/RA3-ChineseVoice'


def write_publish_copy(sizes, exe_sha):
    """Fill the publishing-copy templates with this release's sizes and checksum -> release/<same name>."""
    def human(n):
        return f'{n / 1e9:.1f} GB' if n >= 1e9 else f'{n / 1e6:.0f} MB'
    fill = {'{VERSION}': MOD_VERSION, '{SETUP_EXE}': SETUP_EXE, '{SETUP_SHA256}': exe_sha, '{REPO}': REPO_URL,
            '{FPS_VERSION}': FPS_VERSION}
    fill.update({'{SIZE_' + e + '}': human(n) for e, n in sizes.items()})
    for name in sorted(os.listdir(PUBLISH_DIR)):
        with open(os.path.join(PUBLISH_DIR, name), encoding='utf-8') as f:
            text = f.read()
        for k, v in fill.items():
            text = text.replace(k, v)
        left = sorted(set(re.findall(r'\{[A-Z_]+[^{}]*\}', text)))
        if left:
            sys.exit(f'{name}: unfilled placeholders {left}')
        with open(os.path.join(ROOT, 'release', name), 'w', encoding='utf-8-sig', newline='\r\n') as f:
            f.write(text)
        print(f'publish copy -> release/{name}')


def run_installer(action, components='all'):
    ps1 = os.path.join(release_dir(), 'files', 'installer.ps1')
    if not os.path.exists(ps1):
        sys.exit('run "python ra3cv.py release" first')
    cmd = ['pwsh', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1, '-Action', action, '-Silent',
           '-Components', components]
    cmd += ['-GameDir', '|'.join(GAMES.values())]
    sys.exit(subprocess.call(cmd))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    b = sub.add_parser('build')
    b.add_argument('--game', choices=['all', *GAMES], default='all')
    b.add_argument('--no-level', action='store_true')
    b.add_argument('--voices', default=os.path.join(ROOT, 'voices'), help='folder of <Asset>.wav (or batch subfolders)')
    b.add_argument('--test-on', metavar='PREFIX',
                   help='test build: also map clips onto e.g. JUImper_Voi (Imperial Warrior) lines')
    b.set_defaults(fn=cmd_build)
    p = sub.add_parser('preview'); p.add_argument('batches', nargs='*'); p.set_defaults(fn=cmd_preview)
    r = sub.add_parser('release')
    r.add_argument('--from-patch', metavar='BUILD',
                   help='package = base release + patches/BUILD (keeps its build, version and base)')
    r.set_defaults(fn=cmd_release)
    pa = sub.add_parser('patch', help='update patch against a release build (releases/<build>.json)')
    pa.add_argument('--base', required=True, help='build id of the release players have, e.g. 20261013-1200')
    pa.add_argument('--version', required=True, help='version shown to players, e.g. 1.0.1')
    pa.add_argument('--notes', default='', help='what changed (shown in the installer)')
    pa.set_defaults(fn=cmd_patch)
    i = sub.add_parser('install'); i.add_argument('--components', default='all', help='e.g. allied,eva (default all)')
    i.set_defaults(fn=lambda a: run_installer('install', a.components))
    u = sub.add_parser('uninstall'); u.add_argument('--components', default='all', help='components to remove (default all)')
    u.set_defaults(fn=lambda a: run_installer('uninstall', a.components))
    args = ap.parse_args()
    args.fn(args)


if __name__ == '__main__':
    main()
