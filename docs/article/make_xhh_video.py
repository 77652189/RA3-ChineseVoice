"""Comparison video for the player-facing Xiaoheihe post (the web editor can embed video but not audio).

  python -I -X utf8 docs/article/make_xhh_video.py    -> work/xhh_video/红警3中文配音_实机与对比.mp4

Real play first (the P2 cuts from tools/make_demo.py, the main thing to show), then the lines picked for the post:
each one original first, then our dub. Unit and adjutant lines come from original/ and voices/; the two in-mission
video calls play the game's own movie, once with the original soundtrack and once with ours. No download wording
anywhere (Xiaoheihe rejects it).
"""
import csv
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, ROOT)
import make_demo as md                                      # noqa: E402
from ra3voice import big                                    # noqa: E402

md.OUT = OUT = os.path.join(ROOT, 'work', 'xhh_video')
DEMO = os.path.join(ROOT, 'work', 'demo')
GAMES = {'ra3': md.RA3, 'uprising': md.RA3 + ' Uprising'}
FFPROBE = md.FF.replace('ffmpeg.exe', 'ffprobe.exe')
RED, BG, draw = md.RED, md.BG, md.draw

# (seg, unit name, English name, faction, [(batch, asset)]) in the order of the post
UNITS = [('u01_yuriko', '百合子', 'Yuriko Omega', '旭日帝国', [('empire', 'JUYurik_VoiSelectf')]),
         ('u02_kingoni', '鬼王', 'King Oni', '旭日帝国', [('empire', 'JUKingO_VoiSelUndb')]),
         ('u03_shogun', '将军战舰', 'Shogun Battleship', '旭日帝国', [('empire', 'IUShogu_VoiSelecte')]),
         ('u04_mirage', '幻影坦克', 'Mirage Tank', '盟军', [('allied', 'AUMirag_VoiSelMira')]),
         ('u05_guardian', '守护者坦克', 'Guardian Tank', '盟军', [('allied', 'AUGuard_VoiSelectc')]),
         ('u06_giga', '超级要塞', 'Giga Fortress', '旭日帝国 · 起义时刻新增', [('empire', 'IUGigaF_voiSelUndc')]),
         ('u07_peace', '和平使者', 'Pacifier FAV', '盟军 · 起义时刻新增', [('allied', 'AUPacif_voiSelecte')]),
         ('a01_soviet', '苏联副官', 'Soviet Adjutant', '战场播报', [('eva', 'Seva_ConComplete')]),
         ('a02_empire', '帝国副官', 'Imperial Adjutant', '战场播报',
          [('eva', 'Ieva_AllyUndAttack'), ('eva', 'Ieva_BaseUndAttack')])]
# (game, movie, title)
CALLS = [('ra3', 'a01th05', '盟军战役第 1 关'), ('uprising', 'jth02mv02', '起义时刻 · 帝国篇第 2 关')]
CALL_SIZE, CALL_Y = 640, 120


def probe(path, entry):
    r = subprocess.run([FFPROBE, '-v', 'error', '-show_entries', entry, '-of', 'csv=p=0', path],
                       capture_output=True, text=True)
    return r.stdout.strip().splitlines()[0]


def call_audio(game, movie, tag):
    """The movie's whole soundtrack, original ('en') or ours ('zh'), decoded to a wav in OUT."""
    name = 'data\\movies\\' + movie + '.snd'
    pack = (os.path.join(GAMES[game], 'Data', 'EnglishMovieAudio.big') if tag == 'en'
            else os.path.join(ROOT, 'dist', game, 'CNVoice_movie.big'))
    snd = os.path.join(OUT, f'{movie}_{tag}.snd')
    wav = snd[:-4] + '.wav'
    if not os.path.exists(wav):
        open(snd, 'wb').write(big.read_files(pack, [name])[name])
        subprocess.run([md.VGM, '-o', wav, snd], capture_output=True, check=True)
    return wav


def call_lines(game, movie, col):
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['movie'] == movie and r['games'].split('+')[0] == game]
    return [(float(r['start']), float(r['dur']), r[col].replace('\n', ' ')) for r in sorted(rows, key=lambda r: float(r['start']))]


def call(seg, game, movie, title, tag):
    """The 288x288 call movie, scaled up in the middle of the dark card, subtitles underneath."""
    wav = call_audio(game, movie, tag)
    lines = call_lines(game, movie, tag)
    length = round(min(float(probe(wav, 'format=duration')), max(s + d for s, d, _ in lines) + 1.0), 2)
    ass = md.subs_file([(s, d, t) for s, d, t in lines], 0, f'{seg}.ass')
    ch = int(probe(wav, 'stream=channels'))
    mix = md.DOWNMIX6 if ch == 6 else ('pan=stereo|FL=c0|FR=c0' if ch == 1 else 'pan=stereo|FL=c0|FR=c1')
    video = os.path.join(GAMES[game], 'Data', 'Movies', movie.upper() + '.vp6')
    head = ('原版' if tag == 'en' else '中文配音') + ' · ' + title + ' · 任务中的视频通话'
    x = (md.W - CALL_SIZE) // 2
    md.ff(['-f', 'lavfi', '-t', f'{length}', '-i', f'color=c={BG}:s={md.W}x{md.H}:r={md.FPS}', '-i', video, '-i', wav,
           '-filter_complex',
           f"[1:v]setpts=PTS-STARTPTS,fps={md.FPS},scale={CALL_SIZE}:{CALL_SIZE}:flags=lanczos,setsar=1[m];"
           f"[0:v]drawbox=x={x - 4}:y={CALL_Y - 4}:w={CALL_SIZE + 8}:h={CALL_SIZE + 8}:color=0x2A2E35@1:t=fill[b];"
           f"[b][m]overlay={x}:{CALL_Y}:eof_action=repeat,subtitles={ass}:fontsdir=.,{md.label(head)},"
           f"fade=t=in:st=0:d=0.3,fade=t=out:st={length - 0.4}:d=0.4[v];"
           f"[2:a]{mix},{md.LOUD},apad,atrim=0:{length},afade=t=in:st=0:d=0.2,afade=t=out:st={length - 0.4}:d=0.4[a]",
           '-map', '[v]', '-map', '[a]', '-t', f'{length}'] + md.ENC + [f'{seg}.mp4'])
    return f'{seg}.mp4'


def play_cuts():
    """The P2 gameplay cuts; reuse the ones already rendered for Bilibili."""
    out = []
    for i, (start, length) in enumerate(md.PLAY_CUTS):
        done = os.path.join(DEMO, f'p2_{i:02d}.mp4')
        out.append(done if os.path.exists(done) else md.gameplay(f'p2_{i:02d}', start, length, '实机演示 · 盟军战役 · 东京港'))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    fonts = os.path.join(ROOT, 'third_party', 'fonts', 'out')
    shutil.copyfile(os.path.join(fonts, 'bhei01b.ttf'), os.path.join(OUT, 'font_b.ttf'))
    shutil.copyfile(os.path.join(fonts, 'bhei00m.ttf'), os.path.join(OUT, 'font_m.ttf'))
    segs = [md.card('x00_title', 4.5, [
        f"drawbox=x=(w-12)/2-560:y=360:w=12:h=170:color={RED}@1:t=fill",
        draw('红色警戒3 · 全中文配音', 120, '(w-text_w)/2+10', 365),
        draw('先看实机演示，再听原版和中文对比', 50, '(w-text_w)/2', 565, font='font_m.ttf', color='0xC9CDD3'),
        draw('原版 & 起义时刻　·　AI 普通话配音　·　社区非盈利作品', 34, '(w-text_w)/2', 650, font='font_m.ttf',
             color='0x7D838C')])]
    segs.append(md.card('x01_play', 3, [
        draw('实机演示', 100, '(w-text_w)/2', 410),
        draw('盟军战役 · 东京港　·　装好后的真实游戏画面和声音', 44, '(w-text_w)/2', 570, font='font_m.ttf',
             color='0xC9CDD3')]))
    segs += play_cuts()
    segs.append(md.card('x02_compare', 3, [
        draw('原版　→　中文', 100, '(w-text_w)/2', 410),
        draw('每句先放原版，再放中文配音', 44, '(w-text_w)/2', 570, font='font_m.ttf', color='0xC9CDD3')]))
    for seg, name, en_name, faction, items in UNITS:
        segs.append(md.unit_card(seg, name, en_name, faction, [(b, a, True) for b, a in items]))
    for i, (game, movie, title) in enumerate(CALLS):
        segs.append(call(f'c{i}_en', game, movie, title, 'en'))
        segs.append(call(f'c{i}_zh', game, movie, title, 'zh'))
    segs.append(md.card('x99_end', 6, [
        f"drawbox=x=(w-12)/2-500:y=360:w=12:h=120:color={RED}@1:t=fill",
        draw('一共 10171 句，全部中文', 96, '(w-text_w)/2+10', 365),
        draw('单位语音 · 副官播报 · 战役对白 · 视频通话 · 剧情过场 · 简体中文界面', 42, '(w-text_w)/2', 545,
             font='font_m.ttf', color='0xC9CDD3'),
        draw('念错、翻错、声线不对的地方，欢迎在评论区告诉我', 40, '(w-text_w)/2', 630, font='font_m.ttf',
             color='0xC9CDD3'),
        draw('AI 语音合成（IndexTTS2）　·　社区非盈利作品　·　游戏版权归 Electronic Arts 所有', 32, '(w-text_w)/2', 730,
             font='font_m.ttf', color='0x7D838C')]))
    with open(os.path.join(OUT, 'list.txt'), 'w', encoding='utf-8') as f:
        f.writelines("file '" + s.replace('\\', '/') + "'\n" for s in segs)
    final = '红警3中文配音_实机与对比.mp4'
    md.ff(['-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-movflags', '+faststart', final])
    t = 0.0
    for s in segs:      # where each part starts, for the article text
        p = s if os.path.isabs(s) else os.path.join(OUT, s)
        print(f'{int(t // 60)}:{t % 60:04.1f}  {os.path.basename(s)}')
        t += float(probe(p, 'format=duration'))
    print('->', os.path.join(OUT, final), f'{t:.1f}s')


if __name__ == '__main__':
    main()
