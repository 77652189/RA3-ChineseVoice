"""Cut the demo video (1080p, ~2.5 min) from game footage and the finished dubs.

  python tools/make_demo.py            -> work/demo/红警3中文配音_演示.mp4

Footage: the game's own movies (Data/Movies/*.vp6) with the original audio (EnglishMovieAudio.big)
or our dub (dist/ra3/CNVoice_movie.big), subtitles from lines/movie.csv; unit and EVA lines from
voices/<batch>/; the installer screenshot from docs/img/installer_preview.png.
Needs third_party/ffmpeg (ffmpeg 9, gyan.dev essentials build) and third_party/vgmstream.
"""
import csv
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from ra3voice import big                                    # noqa: E402

FF = os.path.join(ROOT, 'third_party', 'ffmpeg', 'ffmpeg.exe')
VGM = os.path.join(ROOT, 'third_party', 'vgmstream', 'vgmstream-cli.exe')
RA3 = r'C:\Program Files (x86)\Steam\steamapps\common\Command and Conquer Red Alert 3'
OUT = os.path.join(ROOT, 'work', 'demo')
W, H, FPS = 1920, 1080, 30
BG = '0x0F1114'
RED = '0xD7262E'
ENC = ['-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-r', str(FPS),
       '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2']
# EA 5.1 order is L, C, R, Ls, Rs, LFE (checked: ch0/ch2 correlate, ch1 carries the dialogue)
DOWNMIX6 = 'pan=stereo|FL=0.55*c0+0.7*c1+0.4*c3|FR=0.55*c2+0.7*c1+0.4*c4'
LOUD = 'loudnorm=I=-16:TP=-1.5:LRA=11'

_n = [0]


def ff(args):
    r = subprocess.run([FF, '-hide_banner', '-loglevel', 'error', '-y'] + args, cwd=OUT, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if r.returncode:
        raise RuntimeError(r.stderr[-2000:])


def text_file(s):
    _n[0] += 1
    name = f't{_n[0]:03d}.txt'
    with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
        f.write(s)
    return name


def draw(text, size, x, y, font='font_b.ttf', color='white', extra=''):
    return (f"drawtext=fontfile={font}:textfile={text_file(text)}:fontsize={size}:fontcolor={color}:"
            f"x={x}:y={y}{extra}")


def ass_time(t):
    t = max(0.0, t)
    return f'{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}'


def subs_file(lines, offset, name):
    """lines: [(start, dur, text)] in movie time; written relative to the clip start."""
    head = ('[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n[V4+ Styles]\n'
            'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, '
            'Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, '
            'MarginR, MarginV, Encoding\n'
            'Style: S,AR Heiti Bold B5,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,1,0,1,3.5,1.5,2,80,80,70,1\n\n'
            '[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    ev = ''.join(f'Dialogue: 0,{ass_time(s - offset)},{ass_time(s - offset + d + 0.25)},S,,0,0,0,,{t}\n'
                 for s, d, t in lines)
    with open(os.path.join(OUT, name), 'w', encoding='utf-8-sig') as f:
        f.write(head + ev)
    return name


def movie_lines(movie, col):
    with open(os.path.join(ROOT, 'lines', 'movie.csv'), encoding='utf-8-sig') as f:
        rows = [r for r in csv.DictReader(f) if r['movie'] == movie and r['games'] == 'ra3']
    return [(float(r['start']), float(r['dur']), (r[col] or r['zh_official']).replace('\n', ' '))
            for r in sorted(rows, key=lambda r: float(r['start'])) if (r[col] or r['zh_official'])]


def movie_audio(movie):
    """(original wav, dubbed wav) of a movie, both multichannel, in OUT."""
    name = 'data\\movies\\' + movie + '.snd'
    out = []
    for tag, pack in (('en', os.path.join(RA3, 'Data', 'EnglishMovieAudio.big')),
                      ('zh', os.path.join(ROOT, 'dist', 'ra3', 'CNVoice_movie.big'))):
        snd = os.path.join(OUT, f'{movie}_{tag}.snd')
        wav = snd[:-4] + '.wav'
        if not os.path.exists(wav):
            open(snd, 'wb').write(big.read_files(pack, [name])[name])
            subprocess.run([VGM, '-o', wav, snd], capture_output=True, check=True)
        out.append(os.path.basename(wav))
    return out


def label(text):
    """Small tag in the top-left corner: red bar + text."""
    return (f"drawbox=x=70:y=64:w=8:h=58:color={RED}@1:t=fill,"
            + draw(text, 40, 96, 70, extra=':shadowcolor=black@0.8:shadowx=2:shadowy=2'))


def clip(seg, movie, start, length, lang, tag, channels):
    """A piece of a game movie with original ('en') or dubbed ('zh') audio and matching subtitles."""
    en_wav, zh_wav = movie_audio(movie)
    wav = en_wav if lang == 'en' else zh_wav
    lines = [l for l in movie_lines(movie, 'en' if lang == 'en' else 'zh') if start - 0.5 < l[0] < start + length]
    ass = subs_file(lines, start, f'{seg}.ass')
    mix = DOWNMIX6 if channels == 6 else 'pan=stereo|FL=c0|FR=c1'
    video = os.path.join(RA3, 'Data', 'Movies', movie.upper() + '.vp6')
    # EA's VP6 container has no seek index: decode from the start and trim in the filter graph
    end = start + length
    ff(['-i', video, '-i', wav,
        '-filter_complex',
        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,scale={W}:{H}:flags=lanczos,setsar=1,"
        f"subtitles={ass}:fontsdir=.,{label(tag)},"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={length - 0.4}:d=0.4[v];"
        f"[1:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{mix},{LOUD},"
        f"afade=t=in:st=0:d=0.3,afade=t=out:st={length - 0.4}:d=0.4[a]",
        '-map', '[v]', '-map', '[a]', '-t', f'{length}'] + ENC + [f'{seg}.mp4'])
    return f'{seg}.mp4'


# the player's own recording of a campaign mission with the mod installed (not in the repo); skipped if missing
GAMEPLAY = os.environ.get('CNVOICE_GAMEPLAY', os.path.expanduser(os.path.join('~', 'Videos', '2026-10-13 10-43-21.mp4')))


def gameplay(seg, start, length, tag):
    """A piece of real play: in-game video call, unit replies and EVA, as recorded (scaled up to the demo size)."""
    ff(['-ss', str(start), '-t', str(length), '-i', GAMEPLAY,
        '-filter_complex',
        # the corner label would sit on the game's HUD: top centre on a dark box instead
        f"[0:v]scale={W}:{H}:flags=lanczos,setsar=1,"
        + draw(tag, 40, '(w-text_w)/2', 36, extra=':box=1:boxcolor=black@0.6:boxborderw=16') + ","
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={length - 0.4}:d=0.4[v];"
        f"[0:a]{LOUD},afade=t=in:st=0:d=0.3,afade=t=out:st={length - 0.4}:d=0.4[a]",
        '-map', '[v]', '-map', '[a]', '-t', f'{length}'] + ENC + [f'{seg}.mp4'])
    return f'{seg}.mp4'


def card(seg, length, layers, audio=None, image=None):
    """A designed full-screen card: dark background, drawn text layers, optional image and audio."""
    inputs = ['-f', 'lavfi', '-t', f'{length}', '-i', f'color=c={BG}:s={W}x{H}:r={FPS}']
    vf = '[0:v]'
    n = 1
    if image:
        inputs += ['-loop', '1', '-t', f'{length}', '-i', image]
        vf = f'[1:v]scale=1120:-1[img];[0:v][img]overlay=(W-w)/2:70,'
        n = 2
    vf += ','.join(layers) + f',fade=t=in:st=0:d=0.4,fade=t=out:st={length - 0.4}:d=0.4[v]'
    vf = vf.replace('[0:v],', '[0:v]')
    if audio:
        inputs += ['-i', audio]
        af = f'[{n}:a]aformat=channel_layouts=stereo,{LOUD},apad,atrim=0:{length}[a]'
    else:
        inputs += ['-f', 'lavfi', '-t', f'{length}', '-i', 'anullsrc=r=48000:cl=stereo']
        af = f'[{n}:a]anull[a]'
    ff(inputs + ['-filter_complex', vf + ';' + af, '-map', '[v]', '-map', '[a]', '-t', f'{length}'] + ENC + [f'{seg}.mp4'])
    return f'{seg}.mp4'


def voice_wav(batch, asset):
    for cand in (asset, asset + '@ra3', asset + '@uprising'):
        p = os.path.join(ROOT, 'voices', batch, cand + '.wav')
        if os.path.exists(p):
            return p
    raise FileNotFoundError(asset)


def lines_of(batch):
    with open(os.path.join(ROOT, 'lines', batch + '.csv'), encoding='utf-8-sig') as f:
        return {r['asset']: r for r in csv.DictReader(f)}


def concat_audio(seg, parts, gap=0.45):
    """parts: wav paths -> one wav with gaps; returns (file, [(start, end)])."""
    ins, fl, t, spans = [], '', 0.0, []
    for i, p in enumerate(parts):
        ins += ['-i', p]
        fl += f'[{i}:a]aformat=sample_rates=48000:channel_layouts=stereo,apad=pad_dur={gap}[p{i}];'
        r = subprocess.run([FF.replace('ffmpeg.exe', 'ffprobe.exe'), '-v', 'error', '-show_entries', 'format=duration',
                            '-of', 'csv=p=0', p], capture_output=True, text=True)
        d = float(r.stdout.strip())
        spans.append((t, t + d))
        t += d + gap
    fl += ''.join(f'[p{i}]' for i in range(len(parts))) + f'concat=n={len(parts)}:v=0:a=1[a]'
    name = f'{seg}.wav'
    ff(ins + ['-filter_complex', fl, '-map', '[a]', name])
    return name, spans, t


def unit_card(seg, title, en_name, faction, items):
    """items: [(batch, asset, show_english)] -> card with the unit name and each line's subtitle in turn.
    show_english may be a string: the correct English line where the Whisper transcript is wrong."""
    parts, subs = [], []
    for batch, asset, orig in items:
        row = lines_of(batch)[asset]
        if orig:
            parts.append(os.path.join(ROOT, 'original', batch, asset + '.wav'))
            subs.append('原声：' + (orig if isinstance(orig, str) else row['en']))
        parts.append(voice_wav(batch, asset))
        subs.append(row['zh'])
    wav, spans, total = concat_audio(seg, parts)
    length = round(total + 0.4, 2)
    # centred: faction / name / English name, a red rule, then each line in quotes as it plays
    layers = [draw(faction, 40, '(w-text_w)/2', 250, font='font_m.ttf', color='0x9AA0A8'),
              draw(title, 130, '(w-text_w)/2', 310),
              draw(en_name, 40, '(w-text_w)/2', 470, font='font_m.ttf', color='0x7D838C'),
              f"drawbox=x=(iw-120)/2:y=545:w=120:h=6:color={RED}@1:t=fill"]
    for (a, b), s in zip(spans, subs):
        quoted = s if s.startswith('原声') else '「' + s + '」'
        layers.append(draw(quoted, 68, '(w-text_w)/2', 640, color='0xFFFFFF' if not s.startswith('原声') else '0xAEB3BA',
                           extra=f":enable='between(t,{a:.2f},{b + 0.3:.2f})'"))
    return card(seg, length, layers, audio=wav)


def main():
    os.makedirs(OUT, exist_ok=True)
    fonts = os.path.join(ROOT, 'third_party', 'fonts', 'out')
    shutil.copyfile(os.path.join(fonts, 'bhei01b.ttf'), os.path.join(OUT, 'font_b.ttf'))
    shutil.copyfile(os.path.join(fonts, 'bhei00m.ttf'), os.path.join(OUT, 'font_m.ttf'))
    shutil.copyfile(os.path.join(ROOT, 'docs', 'img', 'installer_preview.png'), os.path.join(OUT, 'installer.png'))
    segs = []
    segs.append(card('s01_title', 6, [
        f"drawbox=x=(w-12)/2-560:y=380:w=12:h=170:color={RED}@1:t=fill",
        draw('红色警戒3 · 全中文配音', 120, '(w-text_w)/2+10', 385),
        draw('单位语音 · EVA 播报 · 剧情对白 · 过场视频 · 简体中文界面', 46, '(w-text_w)/2', 580, font='font_m.ttf', color='0xC9CDD3'),
        draw('原版 & 起义时刻　·　AI 普通话配音　·　社区非盈利作品', 34, '(w-text_w)/2', 660, font='font_m.ttf', color='0x7D838C')]))
    segs.append(card('s02_compare', 3, [draw('原版英文　→　中文配音', 80, '(w-text_w)/2', 480)]))
    segs.append(clip('s03_krukov_en', 'a01mm01', 1.5, 7.6, 'en', '原版英文', 6))
    segs.append(clip('s04_krukov_zh', 'a01mm01', 1.5, 15.6, 'zh', '中文配音 · 盟军第一关简报', 6))
    segs.append(clip('s05_news', 'afs01', 2.2, 26.5, 'zh', '剧情过场 · 盟军开篇', 6))
    segs.append(clip('s06_emperor', 'jfs01', 57.5, 20.5, 'zh', '剧情过场 · 帝国开篇', 6))
    segs.append(clip('s07_call', 'a01th01', 0, 4.8, 'zh', '任务中的视频通话', 2))
    segs.append(clip('s08_oleg', 'solgr1', 0, 5.4, 'zh', '遭遇战 AI 指挥官', 2))
    if os.path.exists(GAMEPLAY):
        segs.append(gameplay('s08b_play', 246, 24, '实机画面 · 盟军战役 · 东京港'))
    segs.append(card('s09_units', 3, [draw('单位语音', 90, '(w-text_w)/2', 470)]))
    segs.append(unit_card('s10_kirov', '基洛夫飞艇', 'Kirov Airship', '苏联', [('soviet', 'SUKirov_VoiCreatea', 'Kirov reporting.'), ('soviet', 'SUKirov_VoiAttackb', False)]))
    segs.append(unit_card('s11_conscript', '动员兵', 'Conscript', '苏联', [('soviet', 'SUConsc_VoiAttackc', False), ('soviet', 'SUConsc_VoiAttacke', False)]))
    segs.append(unit_card('s12_tanya', '谭雅', 'Tanya', '盟军', [('allied', 'AUTanya_VoiCrea', False), ('allied', 'AUTanya_VoiAtkd', False)]))
    segs.append(unit_card('s13_warrior', '帝国武士', 'Imperial Warrior', '旭日帝国', [('empire', 'JUImper_VoiAttackc', False), ('empire', 'JUImper_VoiAttClea', False)]))
    segs.append(unit_card('s14_yuriko', '百合子', 'Yuriko Omega', '旭日帝国', [('empire', 'JUYurik_VoiAttackc', False)]))
    segs.append(unit_card('s15_apoc', '天启坦克', 'Apocalypse Tank', '苏联', [('soviet', 'SUApoca_VoiAtka', False)]))
    segs.append(unit_card('s16_giga', '超级要塞', 'Giga Fortress', '旭日帝国 · 起义时刻', [('empire', 'IUGigaF_voiAttackd', False)]))
    segs.append(unit_card('s17_eva', '战场播报', 'EVA', '三阵营', [('eva', 'Aeva_ConComplete', False), ('eva', 'Aeva_BaseUndAttack', False), ('eva', 'Seva_10000credits', False)]))
    segs.append(card('s18_installer', 7, [
        draw('一键安装 · 按需勾选 · 随时卸载', 58, '(w-text_w)/2', 880),
        draw('不改版本号，不影响联机　·　自带检查更新和故障诊断　·　可选 120 帧', 34, '(w-text_w)/2', 965, font='font_m.ttf', color='0x9AA0A8')],
        image='installer.png'))
    segs.append(card('s19_end', 7, [
        f"drawbox=x=(w-12)/2-470:y=330:w=12:h=120:color={RED}@1:t=fill",
        draw('下载见视频简介', 96, '(w-text_w)/2+10', 335),
        draw('「原版」「起义时刻」「完整版」三种安装包，不确定就下完整版', 44, '(w-text_w)/2', 520, font='font_m.ttf', color='0xC9CDD3'),
        draw('制作工具开源　github.com/77652189/RA3-ChineseVoice　·　制作过程见小黑盒长文', 36, '(w-text_w)/2', 625, font='font_m.ttf', color='0xC9CDD3'),
        draw('社区非盈利作品，仅供交流学习 · 游戏版权归 Electronic Arts 所有', 32, '(w-text_w)/2', 715, font='font_m.ttf', color='0x7D838C')]))
    with open(os.path.join(OUT, 'list.txt'), 'w', encoding='utf-8') as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    final = '红警3中文配音_演示.mp4'
    ff(['-f', 'concat', '-safe', '0', '-i', 'list.txt', '-c', 'copy', '-movflags', '+faststart', final])
    print('->', os.path.join(OUT, final))


if __name__ == '__main__':
    main()
