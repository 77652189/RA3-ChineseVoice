"""Run: python -I tests/test_pipeline.py   (or pytest)"""
import os
import random
import struct
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big, eq, pauses, refpack, snr, xas                    # noqa: E402
from ra3voice.game import AudioStream, AF_NUM_SAMPLES            # noqa: E402

GAME_DATA = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3 Uprising\Data'


def _snr_db(x, y):
    x = x.astype(float)
    e = x - y
    return 10 * np.log10(np.sum(x ** 2) / max(np.sum(e ** 2), 1))


def test_refpack_literal_roundtrip():
    rnd = random.Random(1)
    for n in (0, 1, 3, 4, 5, 111, 112, 113, 5000):
        d = bytes(rnd.randrange(256) for _ in range(n))
        assert refpack.decompress(refpack.compress_literal(d)) == d


def test_xas_encode_quality():
    sr = 48000
    t = np.arange(sr) / sr
    x = np.round(12000 * np.sin(2 * np.pi * (100 * t + 2000 * t ** 2))).astype(np.int16)
    y = xas.decode(xas.encode(x), len(x))
    assert len(y) == len(x)
    assert _snr_db(x, y) > 30


def test_snr_header_layout():
    pcm = np.zeros(300, dtype=np.int16)
    blob = snr.build(pcm, 48000)
    assert blob[:4] == bytes.fromhex('0400bb80')
    info = snr.parse(blob)
    assert (info['codec'], info['channels'], info['sample_rate'], info['num_samples']) == (4, 1, 48000, 300)
    assert len(info['payload']) == 3 * xas.FRAME_BYTES


def test_stereo_dual_mono_roundtrip():
    sr = 48000
    t = np.arange(5000) / sr
    x = np.round(8000 * np.sin(2 * np.pi * 300 * t)).astype(np.int16)
    blob = snr.build(x, sr, channels=2)
    info = snr.parse(blob)
    assert info['channels'] == 2 and info['num_samples'] == 5000
    assert len(info['payload']) == 2 * ((5000 + 127) // 128) * xas.FRAME_BYTES
    y, _ = snr.decode(blob)
    assert _snr_db(x, y) > 30


def test_pause_detector_counts_unexplained_gaps():
    sr = 16000
    rng = np.random.default_rng(3)
    voiced = lambda s: rng.normal(0, 0.2, int(s * sr))
    silent = lambda s: np.zeros(int(s * sr))
    # "关键建筑损失" said with a 0.4 s hole in the middle and no comma -> one extra pause
    x = np.concatenate([silent(0.1), voiced(0.5), silent(0.4), voiced(0.6), silent(0.1)])
    assert len(pauses.gaps(x, sr)) == 1
    assert pauses.extra(x, sr, '关键建筑损失。')[0] == 1
    # the same gap is fine where the text has a comma
    assert pauses.extra(x, sr, '注意，盟友基地。')[0] == 0
    # short closures (< 0.12 s) and leading/trailing silence are not pauses
    y = np.concatenate([silent(0.3), voiced(0.4), silent(0.06), voiced(0.4), silent(0.3)])
    assert pauses.extra(y, sr, '资金已达一万。') == (0, 0.0)
    assert pauses.allowed('是的，我同意。') == 1 and pauses.allowed('收到！出发！') == 1
    # long narration may breathe: a 0.2 s gap is fine in an 8 s line, not in a 1.7 s bark
    z = np.concatenate([silent(0.1), voiced(4.0), silent(0.2), voiced(4.0), silent(0.1)])
    assert pauses.extra(z, sr, '一句很长的旁白没有标点')[0] == 0
    z = np.concatenate([silent(0.1), voiced(4.0), silent(0.5), voiced(4.0), silent(0.1)])
    assert pauses.extra(z, sr, '一句很长的旁白没有标点')[0] == 1


def test_matching_eq_moves_spectrum_toward_original():
    from scipy.signal import butter, sosfilt
    sr = 48000
    rng = np.random.default_rng(2)
    hp = butter(4, 300, 'highpass', fs=sr, output='sos')
    orig = [sosfilt(hp, rng.normal(0, 0.1, sr)) for _ in range(3)]
    new = [rng.normal(0, 0.1, sr) for _ in range(3)]
    taps = eq.design(orig, new, sr)
    out = [eq.apply(x, taps) for x in new]

    def low_ratio(clips):
        f, p = eq.ltas(clips, sr)
        return p[f < 150].sum() / p[(f > 500) & (f < 3000)].sum()
    assert low_ratio(out) < low_ratio(new) / 10


def test_big_roundtrip():
    files = [('data\\a.bin', b'hello'), ('data\\audio\\cdata\\x.cdata', b'\x00' * 100)]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 't.big')
        big.write(p, files)
        assert big.read_files(p, [n for n, _ in files]) == dict(files)
        idx = big.read_index(p)
        assert os.path.getsize(p) == struct.unpack('<I', open(p, 'rb').read()[4:8])[0]
        assert idx[0][1] == struct.unpack('>I', open(p, 'rb').read()[12:16])[0]


def test_override_big_against_game():
    if not os.path.isdir(GAME_DATA):
        print('skip: game not installed')
        return
    stream = AudioStream(GAME_DATA)
    target = stream.get('IUGigaF_voiSelecta')
    orig = stream.read_cdata([target])[target.short_name]
    # original decodes, and our encoder reproduces it nearly bit-exact
    pcm, sr = snr.decode(orig)
    assert sr == 48000 and len(pcm) == stream.num_samples(target)
    rng = np.random.default_rng(0)
    new = np.round(rng.normal(0, 3000, 70001)).clip(-32768, 32767).astype(np.int16)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'm.big')
        stream.build_override(p, {target.short_name: new})
        names = [n for n, _, _ in big.read_index(p)]
        assert names == [target.cdata_path, 'data\\audio.bin']  # EA order: path separator sorts first
        files = big.read_files(p, names)
        new_bin = refpack.decompress(files['data\\audio.bin'])
        assert len(new_bin) == len(stream.bin)
        assert struct.unpack_from('<I', new_bin, target.bin_offset + AF_NUM_SAMPLES)[0] == 70001
        # only the 4 sample-count bytes changed
        diff = [i for i in range(len(new_bin)) if new_bin[i] != stream.bin[i]]
        assert all(target.bin_offset + AF_NUM_SAMPLES <= i < target.bin_offset + AF_NUM_SAMPLES + 4 for i in diff)
        dec, _ = snr.decode(files[target.cdata_path])
        assert len(dec) == 70001 and _snr_db(new, dec) > 15


def test_core_bin_patches_only_the_chosen_components():
    if not os.path.isdir(GAME_DATA):
        print('skip: game not installed')
        return
    stream = AudioStream(GAME_DATA)
    a, b = stream.get('IUGigaF_voiSelecta'), stream.get('JUImper_VoiSelecta')
    _, blob = stream.bin_file({a.short_name: 12345})
    new_bin = refpack.decompress(blob)
    assert struct.unpack_from('<I', new_bin, a.bin_offset + AF_NUM_SAMPLES)[0] == 12345
    assert struct.unpack_from('<I', new_bin, b.bin_offset + AF_NUM_SAMPLES)[0] == stream.num_samples(b)
    diff = [i for i in range(len(new_bin)) if new_bin[i] != stream.bin[i]]
    assert diff and all(a.bin_offset + AF_NUM_SAMPLES <= i < a.bin_offset + AF_NUM_SAMPLES + 4 for i in diff)
    import importlib.util
    spec = importlib.util.spec_from_file_location('ra3cv', os.path.join(ROOT, 'ra3cv.py'))
    ra3cv = importlib.util.module_from_spec(spec); spec.loader.exec_module(ra3cv)
    cs = ra3cv.combos(ra3cv.COMPONENTS)
    assert len(cs) == 63 and len({ra3cv.core_name(c) for c in cs}) == 63
    assert ra3cv.core_name({'eva', 'allied'}) == 'CNVoice_core_av.big'


def test_chain_never_includes_mod_archives():
    """Reads of 'original' game data must ignore our own archives, installed or not."""
    from ra3voice.game import chain_for_game, is_mod_big
    for d in (os.path.dirname(GAME_DATA), os.path.dirname(GAME_DATA).replace(' Uprising', '')):
        if not os.path.isdir(d):
            continue
        for lang in ('english', 'chinese_t'):
            chain = chain_for_game(d, lang)
            assert not any(is_mod_big(b) for b in chain.bigs), chain.bigs
            assert all(not is_mod_big(p) for p in chain.where.values())
            if lang == 'english':   # the text component adds ChineseT.big to English SkuDefs
                assert not any(os.path.basename(b).lower() == 'chineset.big' for b in chain.bigs), chain.bigs
    assert is_mod_big('X/Data/CNVoice_core.big') and is_mod_big('ChineseVoice.big') and not is_mod_big('EnglishAudio.big')


def test_streamed_audio_header_lives_in_bin():
    """Mission dialogue keeps its SNR header in the .bin; a replacement must put XAS there."""
    ra3 = os.path.join(os.path.dirname(os.path.dirname(GAME_DATA)), 'Command and Conquer Red Alert 3', 'Data')
    if not os.path.isdir(ra3):
        print('skip: game not installed')
        return
    stream = AudioStream(ra3)
    a = stream.get('MA01_AlliedIntel01')
    hp = stream.header_in_bin(a)
    assert hp is not None and (stream.bin[hp] >> 4, stream.bin[hp] & 15) == (0, 6)   # EALayer3 v2
    assert stream.header_in_bin(stream.get('AUTanya_VoiSelUndFira')) is None
    rng = np.random.default_rng(5)
    pcm = np.round(rng.normal(0, 3000, 20000)).clip(-32768, 32767).astype(np.int16)
    (path, blob), = stream.cdata_files({a.short_name: pcm})
    _, bin_blob = stream.bin_file({a.short_name: len(pcm)})
    new_bin = refpack.decompress(bin_blob)
    header = new_bin[hp:hp + 8]
    # the originals' blocks are RefPack-compressed and small; ours must be too (in-game: raw = silence)
    assert refpack.is_refpack(stream.read_cdata([a])[a.short_name]) and refpack.is_refpack(blob)
    sns = refpack.decompress(blob)
    sizes, p = [], 0
    while p < len(sns):
        sizes.append((sns[p], int.from_bytes(sns[p + 1:p + 4], 'big'), struct.unpack_from('>I', sns, p + 4)[0]))
        p += sizes[-1][1]
    assert p == len(sns) and len(sizes) == 20 and sizes[-1][0] == 0x80 and all(f == 0 for f, _, _ in sizes[:-1])
    assert sum(n for _, _, n in sizes) == 20000
    info = snr.parse(header + sns)                        # what the engine sees: bin header + cdata blocks
    assert (info['codec'], info['channels'], info['sample_rate'], info['num_samples']) == (4, 2, 48000, 20000)
    assert struct.unpack_from('<I', new_bin, a.bin_offset + AF_NUM_SAMPLES)[0] == 20000
    dec, _ = snr.decode(header + sns)
    assert _snr_db(pcm, dec) > 15


def test_movie_audio_channel_replacement():
    """EA-XA v2 movie audio: our decoder matches vgmstream; replacing one channel leaves the others
    bit-identical (they keep their bytes and their cross-block prediction history)."""
    from ra3voice import eaxa, vgm
    pack = os.path.join(os.path.dirname(GAME_DATA), '..', 'Command and Conquer Red Alert 3', 'Data', 'EnglishMovieAudio.big')
    if not os.path.exists(pack):
        print('skip: game not installed')
        return
    name = r'data\movies\a01th01.snd'
    data = big.read_files(pack, [name])[name]
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, 'a.snd')
        open(src, 'wb').write(data)
        ref, _ = vgm.decode_file(src)
        ref = ref.reshape(len(ref), -1)
        ours = eaxa.decode(data)
        assert np.array_equal(ours, ref)
        nch = ref.shape[1]
        t = np.arange(len(ref)) / 48000
        tone = np.round(6000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
        dst = os.path.join(d, 'b.snd')
        open(dst, 'wb').write(eaxa.replace_channel(data, 0, tone))
        out, _ = vgm.decode_file(dst)
        out = out.reshape(len(out), -1)
        assert out.shape == ref.shape
        assert all(np.array_equal(out[:, c], ref[:, c]) for c in range(1, nch))
        assert _snr_db(tone, out[:, 0]) > 20


def test_movie_removal_window_swallows_the_whole_english_line():
    """The subtitle says the line is at 1.0-2.0 s, but the actor starts at 0.7 s and trails to 2.6 s:
    the English must go from 0.7 to 2.6 s; an unrelated voice at 5 s (no dub) stays."""
    from ra3voice import movie
    sr = movie.SR
    voc = np.zeros((7 * sr, 2), dtype=np.int16)
    rng = np.random.default_rng(4)
    voc[int(0.7 * sr):int(2.6 * sr)] = rng.normal(0, 3000, (int(1.9 * sr), 2)).astype(np.int16)
    voc[5 * sr:6 * sr] = rng.normal(0, 3000, (sr, 2)).astype(np.int16)
    m = movie.removal_mask(voc, [(1.0, 2.0)])
    assert m[int(0.75 * sr)] == 1 and m[int(2.55 * sr)] == 1      # grown over the whole English line
    assert m[int(0.3 * sr)] == 0 and m[int(3.2 * sr)] == 0        # silence around it untouched
    assert m[int(5.5 * sr)] == 0                                   # undubbed background voice kept


def test_movie_removal_window_bridges_a_breath():
    """a07th08: "We" at 0.85 s, a 0.1 s breath, then the rest of the line from 1.05 s (subtitle 1.2 s).
    The lone "We" must go too; a voice 0.6 s after the line (no dub) stays."""
    from ra3voice import movie
    sr = movie.SR
    voc = np.zeros((5 * sr, 2), dtype=np.int16)
    rng = np.random.default_rng(5)
    voc[int(0.85 * sr):int(0.95 * sr)] = rng.normal(0, 3000, (int(0.1 * sr), 2)).astype(np.int16)
    voc[int(1.05 * sr):int(2.5 * sr)] = rng.normal(0, 3000, (int(1.45 * sr), 2)).astype(np.int16)
    voc[int(3.1 * sr):int(3.6 * sr)] = rng.normal(0, 3000, (int(0.5 * sr), 2)).astype(np.int16)
    m = movie.removal_mask(voc, [(1.1, 2.4)])
    assert m[int(0.9 * sr)] == 1 and m[int(1.0 * sr)] == 1
    assert m[int(3.3 * sr)] == 0


def test_movie_dub_level_follows_the_actor_when_the_subtitle_is_early():
    """sfs00 "Please.": subtitle at 1.0-1.8 s, actor at 1.8-2.3 s. The window is nearly silent, so the reference
    must come from the voiced part of the grown span (else the dub is matched to silence); a normal line keeps
    its window."""
    from ra3voice import movie
    sr = movie.SR
    rng = np.random.default_rng(6)
    ref = rng.normal(0, 3, 4 * sr)
    ref[int(1.8 * sr):int(1.8 * sr) + sr // 2] = rng.normal(0, 3000, sr // 2)
    span = movie.grown_spans(ref[:, None], [(0.9, 2.1)])[0]
    assert span[1] >= 2.29
    got = movie.level_reference(ref, 1.0, 0.8, span)
    assert np.sqrt(np.mean(got ** 2)) > 2000
    ref2 = rng.normal(0, 3, 4 * sr)
    ref2[int(1.0 * sr):int(1.8 * sr)] = rng.normal(0, 3000, int(0.8 * sr))
    span2 = movie.grown_spans(ref2[:, None], [(0.9, 2.1)])[0]
    assert len(movie.level_reference(ref2, 1.0, 0.8, span2)) == int(0.8 * sr)


def test_text_terms_and_subtitles_follow_the_dub():
    from ra3voice import textpack
    t = textpack.Terms()
    t.globals = [('纳米虫群巢穴', '纳米蜂群巢穴'), ('纳米虫群', '纳米蜂群'), ('俄军', '苏军'), ('苏军', 'X')]
    t.globals.sort(key=lambda p: -len(p[0]))
    import re as _re
    t._re = _re.compile('|'.join(_re.escape(a) for a, _ in t.globals)); t._map = dict(t.globals)
    t.exact = {'收割': '收割者'}
    # longest first, single pass: 俄军 -> 苏军 must not cascade into 苏军 -> X
    assert t.apply('释放纳米虫群：%s 俄军\\n') == '释放纳米蜂群：%s 苏军\\n'
    assert t.apply('纳米虫群巢穴') == '纳米蜂群巢穴'
    assert t.apply('收割') == '收割者' and t.apply('收割机甲') == '收割机甲'
    en = {'SUBTITLE:A01MM01_01': '*[2.3:1.8]Hello capitalist dogs!',
          'SUBTITLE:A01TH05': '*[1.1:4.9]First.[6:3.9]Second.',
          'DIALOGEVENT:MA01_AlliedIntel01': '*The Soviet Union is on Britain\'s doorstep.'}
    mission = [{'asset': 'MA01_AlliedIntel01', 'zh': '苏联打到英国家门口了。'}]
    movie = [{'movie': 'a01mm01', 'start': '2.30', 'zh': '你们好，资本主义走狗！'},
             {'movie': 'a01th05', 'start': '1.10', 'zh': '第一句。'}, {'movie': 'a01th05', 'start': '6.00', 'zh': '第二句。'}]
    ov = textpack.subtitle_overrides(en, mission, movie)
    assert ov['SUBTITLE:A01MM01_01'] == '[2.3:1.8]你们好，资本主义走狗！'          # English timing kept
    assert ov['SUBTITLE:A01TH05'] == '[1.1:4.9]第一句。[6:3.9]第二句。'
    assert ov['DIALOGEVENT:MA01_AlliedIntel01'] == '苏联打到英国家门口了。'
    # a segment without a dub keeps the whole label official (no half-replaced subtitles)
    assert 'SUBTITLE:A01TH05' not in textpack.subtitle_overrides(en, mission, movie[:2])


def _load_ra3cv():
    import importlib.util
    spec = importlib.util.spec_from_file_location('ra3cv', os.path.join(ROOT, 'ra3cv.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fake_project(m, d):
    """Point ra3cv at a temp project with one game: base release 'B' with eva {a: 1, b: 1, c: 1}."""
    m.ROOT, m.GAMES = d, {'g': d}
    m.RELEASE_INDEX, m.PATCH_DIR = os.path.join(d, 'releases'), os.path.join(d, 'patches')
    os.makedirs(os.path.join(d, 'dist', 'g', 'core'))
    os.makedirs(m.RELEASE_INDEX)
    json_dump = __import__('json').dump
    json_dump({'test_build': False, 'partial': []}, open(os.path.join(d, 'dist', 'g', 'build.json'), 'w'))
    eva = os.path.join(d, 'dist', 'g', 'CNVoice_eva.big')
    big.write(eva, [('a', b'1'), ('b', b'1'), ('c', b'1')])
    json_dump({'build': 'B', 'games': {'g': m.dist_index('g')}}, open(os.path.join(m.RELEASE_INDEX, 'B.json'), 'w'))
    return eva


def test_patch_redelivers_what_an_earlier_patch_changed():
    """Patch 1 changed eva:a; the 1.0.1 full package (base + patch 1) has the new a inside CNVoice_eva.big. If
    patch 2 sets a back to the base bytes it must still carry a, or those players keep patch 1's a under patch 2's
    core lengths. A file that disappears from dist cannot be expressed by a patch at all."""
    import argparse
    import json
    m = _load_ra3cv()
    with tempfile.TemporaryDirectory() as d:
        eva = _fake_project(m, d)
        args = argparse.Namespace(base='B', version='x', notes='')
        big.write(eva, [('a', b'2'), ('b', b'1'), ('c', b'1')])
        m.cmd_patch(args)
        first = os.listdir(m.PATCH_DIR)[0]
        os.rename(os.path.join(m.PATCH_DIR, first), os.path.join(m.PATCH_DIR, 'p1'))
        big.write(eva, [('a', b'1'), ('b', b'3'), ('c', b'1')])          # a reverted, b changed
        m.cmd_patch(args)
        p2 = [x for x in os.listdir(m.PATCH_DIR) if x != 'p1'][0]
        (patch,) = json.load(open(os.path.join(m.PATCH_DIR, p2, 'manifest.json'), encoding='utf-8'))['patches']
        (f,) = patch['games']['g']['files']
        assert sorted(n for n, _, _ in big.read_index(os.path.join(m.PATCH_DIR, p2, f['path']))) == ['a', 'b']
        big.write(eva, [('a', b'1'), ('b', b'3')])                        # c gone
        try:
            m.cmd_patch(args)
            raise AssertionError('a missing file must stop the patch')
        except SystemExit as e:
            assert 'missing' in str(e)


def test_full_package_check_sees_changes_outside_the_patch():
    """release --from-patch: dist must equal base + patch in every component, not only in the patched ones."""
    import argparse
    import json
    m = _load_ra3cv()
    with tempfile.TemporaryDirectory() as d:
        eva = _fake_project(m, d)
        big.write(eva, [('a', b'2'), ('b', b'1'), ('c', b'1')])
        m.cmd_patch(argparse.Namespace(base='B', version='x', notes=''))
        p = os.listdir(m.PATCH_DIR)[0]
        (patch,) = json.load(open(os.path.join(m.PATCH_DIR, p, 'manifest.json'), encoding='utf-8'))['patches']
        m.verify_dist_matches_patch(patch)                                 # dist == base + patch: fine
        big.write(eva, [('a', b'2'), ('b', b'9'), ('c', b'1')])          # a change the patch does not carry
        try:
            m.verify_dist_matches_patch(patch)
            raise AssertionError('an unpatched change must be caught')
        except SystemExit as e:
            assert 'not in patch' in str(e)


def test_one_release_carries_a_patch_for_each_base():
    """After a new full package (base C) the old players (base B) still need their cumulative patch: one GitHub
    release holds both, so asset names must not collide, each entry carries only what changed since its own base,
    and the builds differ (the installer keeps one patch.json per build in its cache)."""
    import argparse
    import json
    m = _load_ra3cv()
    with tempfile.TemporaryDirectory() as d:
        eva = _fake_project(m, d)
        big.write(eva, [('a', b'2'), ('b', b'1'), ('c', b'1')])          # the new full package C
        json.dump({'build': 'C', 'games': {'g': m.dist_index('g')}}, open(os.path.join(m.RELEASE_INDEX, 'C.json'), 'w'))
        big.write(os.path.join(d, 'dist', 'g', 'core', 'CNVoice_core_v.big'), [('audio.bin', b'x')])
        big.write(eva, [('a', b'2'), ('b', b'3'), ('c', b'1')])          # the next fix
        m.cmd_patch(argparse.Namespace(base=['C', 'B'], version='x', notes=''))
        (p,) = os.listdir(m.PATCH_DIR)
        src = os.path.join(m.PATCH_DIR, p)
        entries = {e['base']: e for e in json.load(open(os.path.join(src, 'manifest.json'), encoding='utf-8'))['patches']}
        assert sorted(entries) == ['B', 'C'] and entries['B']['build'] != entries['C']['build']
        carried = {b: sorted(n for f in e['games']['g']['files'] for n, _, _ in big.read_index(os.path.join(src, f['path'])))
                   for b, e in entries.items()}
        assert carried == {'B': ['a', 'b'], 'C': ['b']}
        paths = [f['path'] for e in entries.values() for f in e['games']['g']['files']]
        assert len(set(paths)) == len(paths) and all(os.path.exists(os.path.join(src, q)) for q in paths)
        assert {f['name'] for e in entries.values() for f in e['games']['g']['files']} == {'CNVoice_patch_eva.big'}
        assert entries['B']['games']['g']['core'] == entries['C']['games']['g']['core']   # one shared asset
        for e in entries.values():
            m.verify_dist_matches_patch(e)
        # the next patch on base B must redeliver what this one gave B players, found through the manifest
        assert m.earlier_patch_entries('B', 'g') == {'CNVoice_eva.big': {'a', 'b'}}
        assert m.earlier_patch_entries('C', 'g') == {'CNVoice_eva.big': {'b'}}


def test_batched_eaxa_encoder_matches_the_reference():
    """encode_channel_areas (all blocks at once) must give the same bytes as encode_channel_area block by block,
    for odd lengths, a single frame, loud noise and tones."""
    from ra3voice import eaxa
    rng = np.random.default_rng(8)
    pieces = [rng.integers(-32768, 32767, n) for n in (1, 27, 28, 29, 56, 57, 300, 1500)]
    pieces += [(np.sin(np.arange(n) / 5) * 30000).astype(np.int64) for n in (28, 700, 1500)]
    assert eaxa.encode_channel_areas(pieces) == [eaxa.encode_channel_area(p) for p in pieces]


def test_fitlen_keeps_the_original_length():
    """sync-locked lines must come out exactly as long as the original: pad short ones, trim then speed up long ones."""
    from ra3voice import fitlen
    sr = 48000
    rng = np.random.default_rng(5)
    speech = lambda s: rng.normal(0, 0.2, int(s * sr))
    quiet = lambda s: np.zeros(int(s * sr))
    # shorter: untouched, silence appended
    x = speech(1.0)
    y, rate = fitlen.fit(x, int(1.5 * sr), sr)
    assert len(y) == int(1.5 * sr) and rate == 1 and np.allclose(y[:len(x)], x) and not y[len(x):].any()
    # longer only by its quiet head and tail: trimmed, not sped up
    x = np.concatenate([quiet(0.5), speech(1.0), quiet(0.5)])
    y, rate = fitlen.fit(x, int(1.2 * sr), sr)
    assert len(y) == int(1.2 * sr) and rate == 1
    # longer speech: sped up to fit
    y, rate = fitlen.fit(speech(2.0), int(1.6 * sr), sr)
    assert len(y) == int(1.6 * sr) and 1.2 < rate < 1.3
    assert fitlen.fit(np.zeros(100), 50, sr)[0].shape == (50,)


if __name__ == '__main__':
    for k, f in list(globals().items()):
        if k.startswith('test_'):
            f()
            print('ok', k)
