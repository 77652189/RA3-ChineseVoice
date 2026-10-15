"""Assemble dubbed movie audio: put each Chinese line back at its subtitle time in the dialogue track
and re-encode that channel of the movie's .snd (see eaxa.py and tools/catalog_movie.py)."""
import os
import tempfile

import numpy as np

from . import audio_io, eaxa, stretch, vgm

SR = 48000
MAX_RATE = 1.5          # speed-up beyond this sounds rushed; the rest is cut with a fade (short lines tolerate 1.5x)
GUARD = 0.05            # keep this much silence before the next line starts
MUTE_BEFORE, MUTE_AFTER = 0.10, 0.30
RAMP = int(0.02 * SR)


def decode(snd):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'm.snd')
        open(p, 'wb').write(snd)
        x, sr = vgm.decode_file(p)
    assert sr == SR
    return x.reshape(len(x), -1)


def dialogue_channels(nch):
    """Channels that carry the dialogue: centre of 5.1 movies, both sides of stereo, or the only one."""
    return [1] if nch == 6 else list(range(nch))


def trim(x, thresh_db=-38, pad=0.03):
    """Cut leading/trailing low-level noise (TTS sometimes adds seconds of hiss before the words)."""
    hop = SR // 100                                   # 10 ms frames: noise spikes are not speech
    n = len(x) // hop
    if n < 2 or np.abs(x).max() == 0:
        return x
    e = np.sqrt(np.mean(np.asarray(x[:n * hop], dtype=np.float64).reshape(n, hop) ** 2, axis=1))
    loud = 20 * np.log10(e / e.max() + 1e-12) > thresh_db
    sustained = np.convolve(loud, np.ones(5), mode='same') >= 3   # >= 30 ms of sound, not an isolated click
    idx = np.where(loud & sustained)[0]
    if not len(idx):
        return x
    a, b = max(0, idx[0] * hop - int(pad * SR)), min(len(x), (idx[-1] + 1) * hop + int(pad * SR))
    return x[a:b]


def _ramp_mask(n, spans):
    m = np.ones(n)
    for a, b in spans:
        a, b = max(0, int(a * SR)), min(n, int(b * SR))
        if b <= a:
            continue
        m[a:b] = 0
        r = min(RAMP, a)
        m[a - r:a] = np.minimum(m[a - r:a], np.linspace(1, 0, r))
        r = min(RAMP, n - b)
        m[b:b + r] = np.minimum(m[b:b + r], np.linspace(0, 1, r))
    return m


VOICE_REL_DB = -40      # separated-vocal level (vs. the movie's loudest vocal) that still counts as speech
EXTEND_MAX = 2.0        # how far a removal window may grow to swallow the rest of the English line
BRIDGE = 0.25           # a breath this short inside the English line doesn't stop the growth (a07th08: "We ... only")


def speech_channels(nch):
    """Channels that can carry (bleed of) dialogue: all but the LFE of 5.1."""
    return [0, 1, 2, 3, 4] if nch == 6 else list(range(nch))


def removal_mask(voc, windows):
    """1 where the English voice must go, 0 elsewhere (ramped). windows: [(start_s, end_s)] of dubbed lines;
    each grows over the contiguous separated-vocal activity it touches, so late/early words go too."""
    return 1 - _ramp_mask(len(voc), grown_spans(voc, windows))


def _active(env):
    return 20 * np.log10(env / (env.max() + 1e-9) + 1e-12) > VOICE_REL_DB if len(env) else np.zeros(0, bool)


def grown_spans(voc, windows):
    """[(start_s, end_s)] per window, grown over the English voice it touches (see removal_mask)."""
    n = len(voc)
    hop = SR // 100
    nf = n // hop
    env = np.sqrt(np.mean(np.abs(voc[:nf * hop]).astype(np.float64).reshape(nf, hop, -1) ** 2, axis=(1, 2)))
    active = _active(env)
    # close short gaps between active frames, so a word split off by a breath still counts as the same line
    on = np.flatnonzero(active)
    for a, b in zip(on[:-1], on[1:]):
        if 1 < b - a <= BRIDGE * 100:
            active[a:b] = True
    spans = []
    for a, b in windows:
        fa, fb = max(0, int(a * 100)), min(nf, int(b * 100))
        lo, hi = fa, fb
        while lo > 0 and active[lo - 1] and fa - lo < EXTEND_MAX * 100:
            lo -= 1
        while hi < nf and active[hi] and hi - fb < EXTEND_MAX * 100:
            hi += 1
        spans.append((lo / 100, hi / 100))
    return spans


LEVEL_SLACK_DB = 6      # window reference this much quieter than the line's own English: the subtitle time is off


def level_reference(level_ref, start, dur, span):
    """The original clip a dub is level-matched to: normally the subtitle window; but where the subtitle comes
    early or late (sfs00 "Please.", a second ahead of the actor), the window holds little or no English and the
    dub came out inaudible, so then the voiced part of the line's grown removal span is used instead."""
    win = level_ref[max(0, int(start * SR)):int((start + dur) * SR)]
    a, b = max(0, int(span[0] * SR)), min(len(level_ref), int(span[1] * SR))
    hop = SR // 100
    nf = (b - a) // hop
    if nf <= 0:
        return win
    seg = level_ref[a:a + nf * hop]
    env = np.sqrt(np.mean(seg.reshape(nf, hop) ** 2, axis=1))
    voiced = np.flatnonzero(env > env.max() * 10 ** (VOICE_REL_DB / 20)) if env.max() > 0 else []
    if not len(voiced):
        return win
    speech = seg[voiced[0] * hop:(voiced[-1] + 1) * hop]
    rms = lambda y: np.sqrt(np.mean(y ** 2)) if len(y) else 0.0   # noqa: E731
    return speech if rms(win) < rms(speech) * 10 ** (-LEVEL_SLACK_DB / 20) else win


def build(snd, lines, voc=None):
    """snd: original movie bytes. lines: [(start, dur, dub float array in [-1, 1] at SR)] sorted by start.
    voc: separated English vocals [n, channels] int16 (see separate.py) or None. With it, the dubbed lines'
    English is removed from every speaker channel (it bleeds into L/R and the surrounds), keeping music,
    effects and undubbed background voices; without it only the dialogue channel is replaced.
    Returns (new snd bytes, report [(start, rate, cut_seconds)])."""
    x = decode(snd)
    n, nch = x.shape
    chans = dialogue_channels(nch)
    base = x[:, chans].astype(np.float64).mean(axis=1)
    level_ref = base if voc is None else voc[:, chans].astype(np.float64).mean(axis=1)
    out = np.zeros(n)
    mutes, report = [], []
    windows = [(start - MUTE_BEFORE, start + dur + MUTE_AFTER) for start, dur, _ in lines]
    spans = None if voc is None else grown_spans(voc[:, speech_channels(nch)], windows)
    for i, (start, dur, dub) in enumerate(lines):
        nxt = lines[i + 1][0] if i + 1 < len(lines) else n / SR
        avail = max(0.2, nxt - start - GUARD)
        dub = trim(np.asarray(dub, dtype=np.float64))
        rate, cut = 1.0, 0.0
        if len(dub) / SR > avail:
            rate = min(MAX_RATE, len(dub) / SR / avail)
            dub = stretch.wsola(dub, rate, SR)
            if len(dub) / SR > avail:
                cut = len(dub) / SR - avail
                dub = dub[:int(avail * SR)]
                dub[-RAMP:] *= np.linspace(1, 0, min(RAMP, len(dub)))
        ref = (level_ref[max(0, int(start * SR)):int((start + dur) * SR)] if spans is None
               else level_reference(level_ref, start, dur, spans[i]))
        if len(ref) and np.abs(ref).max() > 0:
            dub = audio_io.match_level(dub, np.round(ref).astype(np.int16))
        dub = dub * 32768
        a = int(start * SR)
        seg = dub[:max(0, n - a)]
        out[a:a + len(seg)] += seg
        end = max(start + dur + MUTE_AFTER, start + len(seg) / SR)
        mutes.append((start - MUTE_BEFORE, min(end, nxt - GUARD if i + 1 < len(lines) else end)))
        report.append((start, rate, cut))
    if voc is None:
        track = base * _ramp_mask(n, mutes) + out
        track = np.round(np.clip(track, -32768, 32767)).astype(np.int16)
        return eaxa.replace_channels(snd, {c: track for c in chans}), report
    gone = 1 - _ramp_mask(n, spans)
    new = {}
    for c in speech_channels(nch):
        y = x[:, c].astype(np.float64) - voc[:, c].astype(np.float64) * gone
        if c in chans:
            y += out
        new[c] = np.round(np.clip(y, -32768, 32767)).astype(np.int16)
    return eaxa.replace_channels(snd, new), report
