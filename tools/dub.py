"""Generate Chinese candidates with IndexTTS2 (run with the IndexTTS venv python).

  third_party/index-tts/.venv/Scripts/python tools/dub.py giga_fortress [--takes 3] [--only ASSET ...]

Speaker timbre: the original clip of the same line. Clips shorter than MIN_REF_SECONDS fall back to
the group's single longest *spoken* original (a line that has a translation), never a sigh, laugh or
battle cry — those made the model hum instead of speak. Never concatenate clips into a reference: IndexTTS2 copies the
seams as mid-sentence pauses (see archive/pause_experiment/result_ABCDE.txt).
Emotion/delivery: the original clip of the same line.
Output: candidates/<unit>/<asset>_<k>.wav (22.05 kHz)
"""
import argparse
import csv
import glob
import json
import os
import sys

from scipy.io import wavfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TTS_DIR = os.path.join(ROOT, 'third_party', 'index-tts')
MIN_REF_SECONDS = 1.0


def duration(path):
    sr, x = wavfile.read(path)
    return len(x) / sr


def longest_clip(src_dir, prefix, spoken):
    paths = [p for p in glob.glob(os.path.join(src_dir, prefix + '*.wav'))
             if os.path.splitext(os.path.basename(p))[0] in spoken]
    return max(paths, key=duration) if paths else None


def speaker_ref(src_dir, prefix, asset, fallback, min_ref=MIN_REF_SECONDS, same_actor=None, override=None):
    """A hand-picked same-actor line (override map: the own clip is drowned by other voices) first; else the own
    clip; if too short, the same actor's line (same_actor map, by speaker fingerprint), else the group's
    longest spoken clip. The last resort is only safe for single-speaker groups (unit voices)."""
    if override and asset in override:
        return os.path.join(src_dir, override[asset] + '.wav')
    own = os.path.join(src_dir, asset + '.wav')
    if duration(own) >= min_ref:
        return own
    if same_actor and asset in same_actor:
        return os.path.join(src_dir, same_actor[asset] + '.wav')
    return fallback.get(prefix) or own


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('unit')
    ap.add_argument('--takes', type=int, default=3)
    ap.add_argument('--emo-alpha', type=float, default=0.6)
    ap.add_argument('--only', nargs='*')
    # movies: references cut from the Demucs-separated vocals (original/movie_clean, tools/clean_refs.py) and
    # a short-clip threshold low enough that a 0.6 s line keeps its own speaker instead of another actor's
    ap.add_argument('--ref-dir', help='folder of <asset>.wav references (default original/<unit>)')
    ap.add_argument('--min-ref', type=float, default=MIN_REF_SECONDS)
    args = ap.parse_args()

    units = json.load(open(os.path.join(ROOT, 'units.json'), encoding='utf-8'))
    unit = units[args.unit]
    # units.json may set ref_dir / min_ref / same_actor for a batch (movie: clean vocals, tools/speakers.py)
    ref_dir = args.ref_dir or unit.get('ref_dir')
    src = os.path.abspath(os.path.join(ROOT, ref_dir)) if ref_dir else os.path.join(ROOT, 'original', args.unit)   # dub.py chdirs into index-tts
    min_ref = unit.get('min_ref', args.min_ref) if args.min_ref == MIN_REF_SECONDS else args.min_ref
    same_actor = json.load(open(os.path.join(ROOT, unit['same_actor']), encoding='utf-8')) if unit.get('same_actor') else None
    override = json.load(open(os.path.join(ROOT, unit['ref_override']), encoding='utf-8')) if unit.get('ref_override') else None
    out = os.path.join(ROOT, 'candidates', args.unit)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(ROOT, 'lines', f'{args.unit}.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['zh'].strip()]
    spoken = {r['asset'] for r in rows}
    fallback = {p: longest_clip(src, p, spoken) for p in unit['prefixes']}
    if args.only:
        rows = [r for r in rows if r['asset'] in args.only]

    os.chdir(TTS_DIR)
    sys.path.insert(0, TTS_DIR)
    import torch
    sys.path.insert(0, ROOT)
    from ra3voice import throttle
    throttle.setup(torch)
    from indextts.infer_v2 import IndexTTS2
    tts = IndexTTS2(cfg_path='checkpoints/config.yaml', model_dir='checkpoints',
                    use_fp16=True, use_cuda_kernel=False, use_qwen_emo=False)
    made = failed = 0
    for i, r in enumerate(rows, 1):
        prefix = next(p for p in unit['prefixes'] if r['asset'].lower().startswith(p.lower()))
        for k in range(args.takes):
            dst = os.path.join(out, f"{r['asset']}_{k}.wav")
            if os.path.exists(dst):
                continue
            try:
                spk = speaker_ref(src, prefix, r['asset'], fallback, min_ref, same_actor, override)
                emo = os.path.join(src, r['asset'] + '.wav')
                with throttle.work():
                    tts.infer(spk_audio_prompt=spk, text=r['zh'], output_path=dst,
                              emo_audio_prompt=emo if os.path.exists(emo) else spk, emo_alpha=args.emo_alpha)
                made += 1
            except Exception as e:  # one bad line must not stop a multi-hour batch
                failed += 1
                print(f'FAILED {r["asset"]}_{k}: {e!r}', flush=True)
        if i % 50 == 0:
            print(f'PROGRESS {args.unit} {i}/{len(rows)} made={made} failed={failed}', flush=True)
    print(f'FINISHED {args.unit} made={made} failed={failed}', flush=True)


if __name__ == '__main__':
    main()
