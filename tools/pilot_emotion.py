"""Emotion pilot for one movie: A (released dubs) vs B / C (one fixed voice per character + scene-aware emotion).

  venv=third_party/index-tts/.venv/Scripts/python.exe
  $venv  -I -X utf8 tools/pilot_emotion.py prepare  afs07   # who speaks each line (CPU); emotion template
  (fill work/pilot/afs07/emotions.json: character names and an emotion vector per line, from the scene's script)
  $venv  -I -X utf8 tools/pilot_emotion.py generate afs07   # GPU, honours gpu_limit.json
  python -I -X utf8 tools/pilot_emotion.py pick     afs07   # Whisper + prosody -> B/, C/
  python -I -X utf8 tools/pilot_emotion.py render   afs07   # three versions of the movie, blind page

B: the character's own clean clip as timbre + the scene emotion vector (IndexTTS2 emo_vector), picked the usual
   way (pick.py: read correctly, no extra pauses, not too long).
C: the same takes plus takes that borrow the emotion from the line's original clip (the released method), picked
   by also asking: does the take move like the original (pitch spread, loudness swings, pitch relative to the
   character's usual pitch) and is it still that character's voice (CAMPPlus similarity).
Emotion vector order (IndexTTS2): happy, angry, sad, afraid, disgusted, melancholic, surprised, calm.
"""
import csv
import glob
import json
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))
REF = os.path.join(ROOT, 'original', 'movie_clean')
EMOTIONS = ['happy', 'angry', 'sad', 'afraid', 'disgusted', 'melancholic', 'surprised', 'calm']
TAKES = 6                 # per method and line
SAME_VOICE_SLACK = 0.08   # CAMPPlus similarity this far under the character's median take = not that character


def out_dir(mv):
    return os.path.join(ROOT, 'work', 'pilot', mv)


def movie_lines(mv):
    rows = [r for r in csv.DictReader(open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig'))
            if r['movie'] == mv and r['zh'].strip()]
    return sorted(rows, key=lambda r: float(r['start']))


def load16(path):
    from ra3voice import audio_io
    return audio_io.load_mono(path, 16000).astype(np.float32)


# ---------------------------------------------------------------- prepare (IndexTTS venv, CPU)
def prepare(mv):
    from speakers import Fingerprint, median_f0
    fp = Fingerprint()
    rows = movie_lines(mv)
    emb, info = {}, []
    for r in rows:
        y = load16(os.path.join(REF, r['asset'] + '.wav'))
        emb[r['asset']] = fp(y)
        info.append({'asset': r['asset'], 'en': r['en'], 'zh': r['zh'], 'start': float(r['start']),
                     'dur': float(r['dur']), 'seconds': round(len(y) / 16000, 2), 'f0': round(median_f0(y), 1)})
    # greedy clustering, longest clips first (short ones carry little voice)
    clusters = []
    for it in sorted(info, key=lambda i: -i['seconds']):
        e = emb[it['asset']]
        best = max(clusters, key=lambda c: float(e @ c['centroid']), default=None)
        if best is not None and float(e @ best['centroid']) >= 0.5:
            best['members'].append(it['asset'])
            v = np.mean([emb[a] for a in best['members']], axis=0)
            best['centroid'] = v / np.linalg.norm(v)
        else:
            clusters.append({'members': [it['asset']], 'centroid': e})
    out = {}
    for k, c in enumerate(clusters):
        long_enough = [a for a in c['members'] if next(i for i in info if i['asset'] == a)['seconds'] >= 2.0] or c['members']
        ref = max(long_enough, key=lambda a: float(emb[a] @ c['centroid']))
        out[f'S{k}'] = {'ref': ref, 'members': sorted(c['members']),
                        'f0': round(float(np.median([i['f0'] for i in info if i['asset'] in c['members']])), 1)}
        for a in c['members']:
            next(i for i in info if i['asset'] == a).update(cluster=f'S{k}', sim=round(float(emb[a] @ c['centroid']), 3))
    os.makedirs(out_dir(mv), exist_ok=True)
    json.dump({'lines': info, 'clusters': out}, open(os.path.join(out_dir(mv), 'lines.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    tpl = os.path.join(out_dir(mv), 'emotions.json')
    if not os.path.exists(tpl):
        json.dump({'_order': EMOTIONS, 'characters': {k: {'name': '?', 'ref': v['ref']} for k, v in out.items()},
                   'lines': {i['asset']: {'character': i['cluster'], 'vector': [0] * 8, 'note': ''} for i in info}},
                  open(tpl, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    for k, v in out.items():
        print(k, 'f0', v['f0'], 'ref', v['ref'], 'members', v['members'])


# ---------------------------------------------------------------- generate (IndexTTS venv, GPU)
def generate(mv):
    from speakers import Fingerprint
    emo = json.load(open(os.path.join(out_dir(mv), 'emotions.json'), encoding='utf-8'))
    chars = emo['characters']
    tts_dir = os.path.join(ROOT, 'third_party', 'index-tts')
    os.chdir(tts_dir)
    sys.path.insert(0, tts_dir)
    import torch
    from ra3voice import throttle
    throttle.setup(torch)
    from indextts.infer_v2 import IndexTTS2
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints', use_fp16=True,
                    use_cuda_kernel=False, use_qwen_emo=False)
    fp = Fingerprint()
    centroid = {k: fp(load16(os.path.join(REF, v['ref'] + '.wav'))) for k, v in chars.items()}
    takes_path = os.path.join(out_dir(mv), 'takes.json')
    takes = json.load(open(takes_path, encoding='utf-8')) if os.path.exists(takes_path) else {}
    rows = {r['asset']: r for r in movie_lines(mv)}
    for asset, spec in emo['lines'].items():
        ch = chars[spec['character']]
        spk = os.path.join(REF, ch['ref'] + '.wav')
        own = os.path.join(REF, asset + '.wav')
        for method in ('vec', 'aud'):
            for k in range(TAKES):
                dst = os.path.join(out_dir(mv), 'takes', method, f'{asset}_{k}.wav')
                if os.path.exists(dst):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                # as the IndexTTS2 web UI does: damp the emotions that go strange, cap the sum at 0.8
                kw = ({'emo_vector': tts.normalize_emo_vec([float(v) for v in spec['vector']], apply_bias=True),
                       'emo_alpha': 1.0} if method == 'vec'
                      else {'emo_audio_prompt': own, 'emo_alpha': 0.6})
                with throttle.work():
                    tts.infer(spk_audio_prompt=spk, text=rows[asset]['zh'], output_path=dst, **kw)
                takes[os.path.relpath(dst, out_dir(mv))] = {
                    'asset': asset, 'method': method,
                    'spk_sim': round(float(fp(load16(dst)) @ centroid[spec['character']]), 3)}
                json.dump(takes, open(takes_path, 'w', encoding='utf-8'), indent=1)
        print('done', asset, flush=True)
    print('FINISHED generate', flush=True)


# ---------------------------------------------------------------- pick (system python: Whisper, pypinyin)
def f0_track(y, sr=16000):
    """Per 20 ms frame: F0 in Hz (0 = unvoiced) by autocorrelation, and frame level in dB."""
    n, hop = 640, 320
    peak = np.abs(y).max() + 1e-9
    f0, db = [], []
    for a in range(0, len(y) - n, hop):
        fr = y[a:a + n].astype(np.float64)
        lvl = np.sqrt(np.mean(fr ** 2))
        db.append(20 * np.log10(lvl / peak + 1e-9))
        fr = fr - fr.mean()
        if lvl < peak * 0.08:
            f0.append(0.0)
            continue
        ac = np.correlate(fr, fr, 'full')[n - 1:]
        lo, hi = sr // 500, sr // 65
        k = lo + int(np.argmax(ac[lo:hi]))
        f0.append(sr / k if ac[k] > 0.4 * ac[0] else 0.0)
    return np.array(f0), np.array(db)


def prosody(y):
    """(pitch spread in semitones, loudness swing in dB, median F0) of a clip's voiced frames."""
    f0, db = f0_track(y)
    v = f0[f0 > 0]
    if len(v) < 5:
        return 0.0, 0.0, 0.0
    st = 12 * np.log2(v / np.median(v))
    loud = db[db > db.max() - 30]
    return float(np.percentile(st, 90) - np.percentile(st, 10)), float(np.std(loud)), float(np.median(v))


def pick(mv):
    import torch
    from transformers import pipeline
    import pick as base
    from ra3voice import audio_io, eq, pauses
    emo = json.load(open(os.path.join(out_dir(mv), 'emotions.json'), encoding='utf-8'))
    takes = json.load(open(os.path.join(out_dir(mv), 'takes.json'), encoding='utf-8'))
    rows = {r['asset']: r for r in movie_lines(mv)}
    asr = pipeline('automatic-speech-recognition', model=base.MODEL, dtype=torch.float16, device='cuda:0')
    # each character's usual pitch, in the originals and in its takes, so "higher than usual" can be compared
    orig_f0 = {a: prosody(load16(os.path.join(REF, a + '.wav'))) for a in emo['lines']}
    char_orig = {c: np.median([orig_f0[a][2] for a, s in emo['lines'].items() if s['character'] == c and orig_f0[a][2]])
                 for c in emo['characters']}
    scored = []
    for rel, t in takes.items():
        a, r = t['asset'], rows[t['asset']]
        x = base.trim(load16(os.path.join(out_dir(mv), rel)), 16000)
        hyp = asr({'raw': x, 'sampling_rate': 16000}, generate_kwargs={'language': 'zh', 'task': 'transcribe'})['text'].strip()
        e = base.cer(r['zh'], hyp)
        n_pause, _ = pauses.extra(x, 16000, r['zh'])
        sec = len(x) / 16000
        usual = base.PAUSE_PENALTY * n_pause + max(0.0, sec / float(r['seconds']) - 1.3) + e
        scored.append(dict(t, rel=rel, cer=e, usual=usual, sec=sec, prosody=prosody(x)))
    for c in emo['characters']:
        f0s = [s['prosody'][2] for s in scored if emo['lines'][s['asset']]['character'] == c and s['prosody'][2]]
        for s in scored:
            if emo['lines'][s['asset']]['character'] == c:
                s['char_take_f0'] = float(np.median(f0s)) if f0s else 0.0
    picks = {'B': {}, 'C': {}}
    for a in emo['lines']:
        mine = [s for s in scored if s['asset'] == a]
        ok = [s for s in mine if s['cer'] <= 0.2] or mine
        picks['B'][a] = min([s for s in ok if s['method'] == 'vec'] or ok, key=lambda s: s['usual'])
        spread_o, swing_o, f0_o = orig_f0[a]
        c = emo['lines'][a]['character']

        def expressive_gap(s):
            spread, swing, f0 = s['prosody']
            rel_o = np.log2(f0_o / char_orig[c]) if f0_o and char_orig[c] else 0.0
            rel_t = np.log2(f0 / s['char_take_f0']) if f0 and s['char_take_f0'] else 0.0
            return (abs(spread - spread_o) / max(spread_o, 2.0) + abs(swing - swing_o) / max(swing_o, 3.0)
                    + 2 * abs(rel_t - rel_o))
        # cross-language similarity runs low (released A dubs: 0.46-0.60), so judge each take against its
        # character's other takes: drop the ones clearly off the voice
        floor = np.median([s['spk_sim'] for s in scored if emo['lines'][s['asset']]['character'] == c]) - SAME_VOICE_SLACK
        voice_ok = [s for s in ok if s['spk_sim'] >= floor] or ok
        picks['C'][a] = min(voice_ok, key=lambda s: s['usual'] + 0.5 * expressive_gap(s))
    # EQ each version per character to the originals, as pick.py does, so B / C differ from A by voice and delivery
    for v, chosen in picks.items():
        d = os.path.join(out_dir(mv), v)
        os.makedirs(d, exist_ok=True)
        for c in emo['characters']:
            names = [a for a in chosen if emo['lines'][a]['character'] == c]
            if not names:
                continue
            won = {a: base.trim(audio_io.load_mono(os.path.join(out_dir(mv), chosen[a]['rel']), base.SR), base.SR) for a in names}
            orig = [audio_io.load_mono(os.path.join(ROOT, 'original', 'movie', a + '.wav'), base.SR) for a in names]
            taps = eq.design(orig, [won[a] for a in names], base.SR)
            for a in names:
                y = eq.apply(won[a], taps)
                y = y * min(1.0, 0.98 / max(float(np.max(np.abs(y))), 1e-9))
                audio_io.save_wav(os.path.join(d, a + '.wav'), audio_io.to_int16(y), base.SR)
    report = [{'asset': a, 'character': emo['characters'][emo['lines'][a]['character']]['name'],
               'B': picks['B'][a]['rel'], 'C': picks['C'][a]['rel'], 'C_method': picks['C'][a]['method'],
               'C_spk_sim': picks['C'][a]['spk_sim'], 'B_cer': round(picks['B'][a]['cer'], 2),
               'C_cer': round(picks['C'][a]['cer'], 2)} for a in emo['lines']]
    with open(os.path.join(out_dir(mv), 'picks.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)
    print(f'B / C written; C used the emotion-vector method for '
          f'{sum(r["C_method"] == "vec" for r in report)} of {len(report)} lines')


# ---------------------------------------------------------------- render (system python, ffmpeg)
def render(mv):
    import make_demo as md
    from ra3voice import audio_io, big, movie
    import ra3cv_loader
    ra3cv = ra3cv_loader.load()
    md.OUT = out = out_dir(mv)
    import shutil
    shutil.copyfile(os.path.join(ROOT, 'third_party', 'fonts', 'out', 'bhei01b.ttf'), os.path.join(out, 'font_b.ttf'))
    game = next(r['games'].split('+')[0] for r in movie_lines(mv))
    gdir = ra3cv.GAMES[game]
    name = 'data\\movies\\' + mv + '.snd'
    snd = big.read_files(os.path.join(gdir, 'Data', 'EnglishMovieAudio.big'), [name])[name]
    voc = np.load(os.path.join(ROOT, 'work', 'sep', game, mv + '.npy'))
    shift = ra3cv.movie_offsets()
    align = os.path.join(ROOT, 'work', 'align', 'offsets.json')
    if os.path.exists(align):
        shift = dict(json.load(open(align, encoding='utf-8')), **shift)
    rows = movie_lines(mv)
    versions = {'A': os.path.join(ROOT, 'voices', 'movie'), 'B': os.path.join(out, 'B'), 'C': os.path.join(out, 'C')}
    nch = None
    for v, d in versions.items():
        lines = sorted((float(r['start']) + shift.get(r['asset'], 0.0), float(r['dur']),
                        audio_io.load_mono(os.path.join(d, r['asset'] + '.wav'), movie.SR)) for r in rows)
        new = movie.mix(snd, movie.prepare(snd, lines, voc), voc)
        open(os.path.join(out, f'{v}.snd'), 'wb').write(new)
        wav = os.path.join(out, f'{v}.wav')
        import subprocess
        subprocess.run([md.VGM, '-o', wav, os.path.join(out, f'{v}.snd')], capture_output=True, check=True)
        nch = nch or (6 if movie.eaxa.channels(new) == 6 else 2)
    # same picture and subtitles (the game's timing) for all three; only the sound differs
    subs = md.subs_file([(float(r['start']), float(r['dur']), r['zh']) for r in rows], 0, 'subs.ass')
    video = os.path.join(gdir, 'Data', 'Movies', mv.upper() + '.vp6')
    masked = os.path.join(ROOT, 'work', 'demo', 'masked', mv.upper() + '.mp4')
    video = masked if os.path.exists(masked) else video
    mix = md.DOWNMIX6 if nch == 6 else 'pan=stereo|FL=c0|FR=c1'
    order = ['A', 'B', 'C']
    random.Random().shuffle(order)
    key = {}
    for label, v in zip('XYZ', order):
        md.ff(['-i', video, '-i', f'{v}.wav', '-filter_complex',
               f'[0:v]scale={md.W}:{md.H}:flags=lanczos,setsar=1,subtitles={subs}:fontsdir=.[v];[1:a]{mix},{md.LOUD}[a]',
               '-map', '[v]', '-map', '[a]', '-shortest'] + md.ENC + [f'{label}.mp4'])
        key[label] = v
    json.dump(key, open(os.path.join(out, 'answer_key.json'), 'w', encoding='utf-8'))
    page = ['<!doctype html><meta charset=utf-8><title>过场配音盲听</title><style>body{font-family:"Microsoft YaHei UI",'
            'sans-serif;background:#15171b;color:#ddd;margin:24px;max-width:1000px}video{width:100%;margin:6px 0 24px}'
            'h2{color:#e8a33d}</style><h1>同一段过场，三个版本，只有配音不同</h1>'
            '<p>顺序是随机打乱的。请按「感情是否自然、像不像这个角色、口型时间对不对」给 X / Y / Z 排个序，'
            '也可以说哪几句最明显。答案在 answer_key.json，听完再看。</p>']
    for label in 'XYZ':
        page.append(f'<h2>{label}</h2><video controls preload=metadata src="{label}.mp4"></video>')
    open(os.path.join(out, 'index.html'), 'w', encoding='utf-8').write('\n'.join(page))
    print('->', os.path.join(out, 'index.html'))


if __name__ == '__main__':
    {'prepare': prepare, 'generate': generate, 'pick': pick, 'render': render}[sys.argv[1]](sys.argv[2])
