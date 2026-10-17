"""P3 of the Bilibili upload: what changed from 1.0 to 1.1 (1.0.1 + 1.0.2 + 1.1), each example played as in 1.0, then
as in 1.1. About a minute; it opens on the most audible 1.0 mistake and never shows a silent card before the end
(Bilibili reported many exits in the first 3 seconds of P1, which opens on 9 s of text).

  python -I -X utf8 docs/article/make_update_video.py    -> work/p3/红警3中文配音_1.1更新对比.mp4

Movie sound comes from the shipped packages (release/红警3中文配音MOD_v1.0_完整版, ..._v1.1_完整版), so the clips are
exactly what players heard; unit and adjutant lines come from the archived takes (archive/dan4_redub) or the English
original (lines 1.0 did not dub). Clips were checked for the world map (B站 rejects it unmasked): none shows one.
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

md.OUT = OUT = os.path.join(ROOT, 'work', 'p3')
RED, draw = md.RED, md.draw
PACK = {v: os.path.join(ROOT, 'release', f'红警3中文配音MOD_v{v}_完整版', 'files', 'ra3', 'CNVoice_movie.big')
        for v in ('1.0', '1.1')}
GREY, LIGHT, DIM = '0x9AA0A8', '0xC9CDD3', '0x7D838C'


def movie_wav(movie, ver):
    name = 'data\\movies\\' + movie + '.snd'
    snd = os.path.join(OUT, f'{movie}_{ver}.snd')
    wav = snd[:-4] + '.wav'
    if not os.path.exists(wav):
        open(snd, 'wb').write(big.read_files(PACK[ver], [name])[name])
        subprocess.run([md.VGM, '-o', wav, snd], capture_output=True, check=True)
    return wav


def clip(seg, movie, start, length, ver, what, headline=None, until=None):
    """A piece of a ra3 movie with the 1.0 or 1.1 dub; Chinese subtitles (game timing) in both. headline: the point
    of the clip in a bar over the picture (whole clip, or until `until` s), so no silent title card is needed."""
    wav = movie_wav(movie, ver)
    lines = [l for l in md.movie_lines(movie, 'zh') if start - 0.5 < l[0] < start + length]
    ass = md.subs_file(lines, start, f'{seg}.ass')
    ch = int(subprocess.run([md.FF.replace('ffmpeg.exe', 'ffprobe.exe'), '-v', 'error', '-show_entries',
                             'stream=channels', '-of', 'csv=p=0', wav], capture_output=True, text=True).stdout.split()[0])
    mix = md.DOWNMIX6 if ch == 6 else 'pan=stereo|FL=c0|FR=c1'
    video = os.path.join(md.RA3, 'Data', 'Movies', movie.upper() + '.vp6')
    end = start + length
    tag = ('1.0（旧）' if ver == '1.0' else '1.1（新）') + ' · ' + what
    md.ff(['-i', video, '-i', wav, '-filter_complex',
           f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={md.W}:{md.H}:flags=lanczos,setsar=1,"
           f"subtitles={ass}:fontsdir=.,{md.label(tag)},{head_bar(headline, length if until is None else until)}"
           f"fade=t=in:st=0:d=0.3,fade=t=out:st={length - 0.3}:d=0.3[v];"
           f"[1:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{mix},{md.LOUD},"
           f"afade=t=in:st=0:d=0.2,afade=t=out:st={length - 0.3}:d=0.3[a]",
           '-map', '[v]', '-map', '[a]', '-t', f'{length}'] + md.ENC + [f'{seg}.mp4'])
    return f'{seg}.mp4'


def head_bar(text, until):
    if not text:
        return ''
    return draw(text, 64, '(w-text_w)/2', 150, color='0xFFE08A',
                extra=f":box=1:boxcolor=black@0.62:boxborderw=22:enable='lt(t,{until:.2f})'") + ','


def ab_card(seg, title, sub, items):
    """items: [(tag, wav, text)] played in turn, the tag and the line shown while each plays."""
    wav, spans, total = md.concat_audio(seg, [w for _, w, _ in items], gap=0.6)
    layers = [draw(sub, 40, '(w-text_w)/2', 250, font='font_m.ttf', color=GREY),
              draw(title, 110, '(w-text_w)/2', 310),
              f"drawbox=x=(iw-120)/2:y=470:w=120:h=6:color={RED}@1:t=fill"]
    for (a, b), (tag, _, text) in zip(spans, items):
        on = f":enable='between(t,{a:.2f},{b + 0.5:.2f})'"
        old = tag.startswith('1.0')
        layers.append(draw(tag, 46, '(w-text_w)/2', 560, color=DIM if old else '0xE8B04A', extra=on))
        layers.append(draw(text, 70, '(w-text_w)/2', 640, color='0xAEB3BA' if old else 'white', extra=on))
    return md.card(seg, round(total + 0.5, 2), layers, audio=wav)


def main():
    os.makedirs(OUT, exist_ok=True)
    fonts = os.path.join(ROOT, 'third_party', 'fonts', 'out')
    shutil.copyfile(os.path.join(fonts, 'bhei01b.ttf'), os.path.join(OUT, 'font_b.ttf'))
    shutil.copyfile(os.path.join(fonts, 'bhei00m.ttf'), os.path.join(OUT, 'font_m.ttf'))
    v = lambda b, a: os.path.join(ROOT, 'voices', b, a + '.wav')
    orig = lambda b, a: os.path.join(ROOT, 'original', b, a + '.wav')
    old_dan = lambda b, a: os.path.join(ROOT, 'archive', 'dan4_redub', b, 'voices', a + '.wav')
    # no silent title card: the first frame already plays the most audible 1.0 mistake (Bilibili's 3-second exits)
    segs = [
        clip('h1_old', 'afs07', 28.3, 4.4, '1.0', '红警3中文配音 · 1.1 更新对比', headline='旧版：谭雅怎么是男声？'),
        clip('h1_new', 'afs07', 28.3, 4.4, '1.1', '红警3中文配音 · 1.1 更新对比', headline='1.1：修好了'),
        clip('h2_old', 'jfs07', 125.6, 4.5, '1.0', '帝国第 7 关 · 天皇', headline='旧版：老天皇一开口是女声'),
        clip('h2_new', 'jfs07', 125.6, 4.5, '1.1', '帝国第 7 关 · 天皇', headline='1.1：约 390 句过场换成更像原演员的音色'),
        clip('h3_old', 'jfs07', 8.0, 3.5, '1.0', '帝国第 7 关 · 达郎', headline='旧版：儿子也是女声'),
        clip('h3_new', 'jfs07', 8.0, 3.5, '1.1', '帝国第 7 关 · 达郎', headline='1.1：男女声颠倒都修正了'),
        clip('m1_old', 'afs05', 21.8, 7.9, '1.0', '盟军第 5 关简报', headline='旧版：嘴还没动，中文先出来了'),
        clip('m1_new', 'afs05', 21.8, 7.9, '1.1', '盟军第 5 关简报', headline='1.0.2 起：约 1050 句按演员开口对齐'),
    ]
    segs.append(ab_card('u1_dan', '「中弹」念成了「中谈」', '读音修正 · 1.1 重配 23 句', [
        ('1.0（旧）', old_dan('soviet', 'SUComba_VoiSelUndc'), '「我中弹了！」'),
        ('1.1（新）', v('soviet', 'SUComba_VoiSelUndc'), '「我中弹了！」')]))
    segs.append(ab_card('u2_eva', '漏配的语音补上了', '旧版没认出 EA 拼错的文件名，还是英文', [
        ('1.0（旧） · 苏联副官', orig('eva', 'Svea_UltraNagnticSatellteReady'), 'Ultra magnetic satellite ready.'),
        ('1.1（新） · 苏联副官', v('eva', 'Svea_UltraNagnticSatellteReady'), '「终极磁力卫星准备完毕！」'),
        ('1.0（旧） · 娜塔莎', orig('soviet', 'SUNatas_VoiFeara'), "I can't kill if I'm dead!"),
        ('1.1（新） · 娜塔莎', v('soviet', 'SUNatas_VoiFeara'), '「死了可就杀不了人了！」')]))
    segs.append(md.card('x99_end', 7, [
        f"drawbox=x=(w-12)/2-470:y=250:w=12:h=120:color={RED}@1:t=fill",
        draw('装了旧版：安装器里点「检查更新」', 80, '(w-text_w)/2+10', 260),
        draw('新下载：网盘链接不变，已经是 1.1', 48, '(w-text_w)/2', 440, font='font_m.ttf', color=LIGHT),
        draw('还修了：残留的英文单词　·　音量过小的中文　·　更新时不再重复下载已有文件', 38, '(w-text_w)/2', 560,
             font='font_m.ttf', color=GREY),
        draw('念错、翻错、声线不对，欢迎在评论区告诉我', 40, '(w-text_w)/2', 650, font='font_m.ttf', color=LIGHT),
        draw('AI 语音合成（IndexTTS2）　·　社区非盈利作品　·　游戏版权归 Electronic Arts 所有', 32, '(w-text_w)/2', 760,
             font='font_m.ttf', color=DIM)]))

    with open(os.path.join(OUT, 'list.txt'), 'w', encoding='utf-8') as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    final = '红警3中文配音_1.1更新对比.mp4'
    md.ff(['-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-movflags', '+faststart', final])
    t = 0.0
    probe = md.FF.replace('ffmpeg.exe', 'ffprobe.exe')
    for s in segs:
        d = float(subprocess.run([probe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                                  os.path.join(OUT, s)], capture_output=True, text=True).stdout.strip())
        print(f'{int(t // 60)}:{t % 60:04.1f}  {s}')
        t += d
    print('->', os.path.join(OUT, final), f'{t:.1f}s')


if __name__ == '__main__':
    main()
