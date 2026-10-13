"""Figures for the Xiaoheihe article (docs/article/xiaoheihe.md). CPU only; run with the IndexTTS venv python:

  third_party/index-tts/.venv/Scripts/python -I -X utf8 docs/article/make_figs.py [load pipeline pauses spectrum pitch]

Writes docs/article/img/fig*.png (1600 px wide, dark theme to sit well in the app's dark mode).
"""
import json
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt                       # noqa: E402
from matplotlib import font_manager                   # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch   # noqa: E402
import numpy as np                                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
IMG = os.path.join(HERE, 'img')
DATA = os.path.join(HERE, 'data')
for f in ('font_m.ttf', 'font_b.ttf'):
    font_manager.fontManager.addfont(os.path.join(ROOT, 'work', 'demo', f))
FONT = font_manager.FontProperties(fname=os.path.join(ROOT, 'work', 'demo', 'font_m.ttf')).get_name()
plt.rcParams.update({'font.family': FONT, 'axes.unicode_minus': False})

BG, PANEL, FG, DIM, GRID = '#14161b', '#1e2128', '#e8e6e1', '#9aa0a8', '#2c3038'
RED, GREEN, GOLD, BLUE = '#d6403a', '#5fbf7f', '#e3b34c', '#5b9bd5'
W = 16                                                # inches at dpi 100 -> 1600 px


def fig(h):
    f = plt.figure(figsize=(W, h), dpi=100, facecolor=BG)
    return f


def save(f, name):
    os.makedirs(IMG, exist_ok=True)
    f.savefig(os.path.join(IMG, name), facecolor=BG)
    plt.close(f)
    print('->', name)


def box(ax, x, y, w, h, text, color, fs=19, sub=None, fill=PANEL):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0,rounding_size=0.12',
                                fc=fill, ec=color, lw=2.5))
    ax.text(x + w / 2, y + h / 2 + (0.16 if sub else 0), text, ha='center', va='center', color=FG, fontsize=fs,
            weight='bold')
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.27, sub, ha='center', va='center', color=DIM, fontsize=fs - 6)


def arrow(ax, a, b, color=DIM, rad=0.0, lw=2.5):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle='-|>', mutation_scale=24, color=color, lw=lw,
                                 connectionstyle=f'arc3,rad={rad}'))


def load_order():
    """The lowest SkuDef of the chain Steam starts (1.13 -> ... -> 1.0) with our lines in front of EnglishAudio."""
    sku = ['set-exe Data\\ra3_1.0.game', 'set-search-path big:;.', 'add-big Data\\MapsCampaign.big', '……',
           'add-big Data\\English.big']
    ours = ['add-big Data\\CNVoice_allied.big', 'add-big Data\\CNVoice_soviet.big', '……（选了哪几部分就有哪几行）',
            'add-big Data\\CNVoice_core.big']
    rest = ['add-big Data\\EnglishAudio.big', 'add-big Data\\EnglishMovieAudio.big', '……']
    f = fig(9)
    ax = f.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis('off')
    ax.text(0.6, 8.35, '游戏按配置文件从上往下打开资源包，同名文件以先打开的为准', color=FG, fontsize=24, weight='bold')
    # chain on the left
    chain = [('Steam 启动', 'RA3_english_1.13'), ('引用', 'RA3_english_1.12'), ('一层层引用', '1.11 → … → 1.1'), ('最底层', 'ra3_english_1.0')]
    for i, (t, s) in enumerate(chain):
        y = 6.6 - i * 1.55
        box(ax, 0.6, y, 3.6, 1.0, s, GOLD if i == 3 else DIM, fs=17, sub=t)
        if i < 3:
            arrow(ax, (2.4, y - 0.02), (2.4, y - 0.53))
    arrow(ax, (4.25, 2.0), (5.15, 2.0), GOLD)
    # file panel on the right
    ax.add_patch(FancyBboxPatch((5.2, 0.45), 10.2, 7.3, boxstyle='round,pad=0,rounding_size=0.15', fc=PANEL, ec=GRID, lw=2))
    ax.text(5.55, 7.3, 'ra3_english_1.0.SkuDef', color=GOLD, fontsize=17, family='monospace', weight='bold')
    y = 6.65
    lh = 0.47
    for ln in sku:
        ax.text(5.7, y, ln, color=DIM, fontsize=17, family='monospace' if ln.startswith(('add', 'set')) else FONT, va='center')
        y -= lh
    top = y + lh / 2
    for ln in ours:
        ax.text(5.7, y, ln, color=GREEN, fontsize=17, weight='bold', va='center',
                family='monospace' if ln.startswith('add') else FONT)
        y -= lh
    ax.add_patch(FancyBboxPatch((5.45, y + lh / 2), 9.7, top - y - lh / 2, boxstyle='round,pad=0,rounding_size=0.08',
                                fc='#5fbf7f1f', ec=GREEN, lw=2))
    ax.text(15.0, (top + y + lh / 2) / 2, '安装器插入的行\n（改之前先备份）', color=GREEN, fontsize=17, ha='right', va='center')
    for i, ln in enumerate(rest):
        ax.text(5.7, y, ln, color=RED if i == 0 else DIM, fontsize=17, va='center', weight='bold' if i == 0 else 'normal',
                family='monospace' if ln.startswith('add') else FONT)
        if i == 0:
            ax.text(15.0, y, '原版英文语音：排在后面，被中文盖住', color=RED, fontsize=16, ha='right', va='center')
        y -= lh
    save(f, 'fig2_load_order.png')


def pipeline():
    f = fig(7.6)
    ax = f.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 7.6)
    ax.axis('off')
    ax.text(0.6, 6.95, '每一句台词走一遍这条流水线', color=FG, fontsize=24, weight='bold')
    w, h = 3.2, 1.45
    row1 = [('原版语音', '从游戏包里拆出', DIM), ('听写英文', 'Whisper', BLUE), ('翻译', '官方字幕 + 术语表', BLUE),
            ('AI 配音', 'IndexTTS2，一句多版', RED)]
    xs = [0.6, 4.4, 8.2, 12.0]
    y1, y2 = 4.55, 1.35
    for x, (t, s, c) in zip(xs, row1):
        box(ax, x, y1, w, h, t, c, fs=22, sub=s)
    for a, b in zip(xs, xs[1:]):
        arrow(ax, (a + w + 0.05, y1 + h / 2), (b - 0.05, y1 + h / 2))
    row2 = [('听写中文打分', '字念对没有、有没有怪停顿', GOLD), ('挑最好的一版', '不合格的自动重配', GOLD),
            ('打包进游戏', '安装器按组件安装', GREEN)]
    xs2 = [12.0, 8.2, 4.4]
    for x, (t, s, c) in zip(xs2, row2):
        box(ax, x, y2, w, h, t, c, fs=22, sub=s)
    arrow(ax, (12.0 + w / 2, y1 - 0.05), (12.0 + w / 2, y2 + h + 0.05))
    for a, b in zip(xs2, xs2[1:]):
        arrow(ax, (a - 0.05, y2 + h / 2), (b + w + 0.05, y2 + h / 2))
    # retry loop: pick -> dub
    arrow(ax, (8.2 + w * 0.75, y2 + h + 0.05), (12.0 + 0.25, y1 - 0.05), RED, rad=-0.25, lw=2)
    ax.text(10.05, 3.55, '重配', color=RED, fontsize=18, ha='center')
    ax.text(0.6, 0.55, '过场视频还多两步：先用 Demucs 把英文人声从每个声道里去掉，再按字幕时间轴把中文放回去。',
            color=DIM, fontsize=17)
    save(f, 'fig3_pipeline.png')


def pauses():
    """2026-10-09 reference experiment (logs in archive/pause_experiment) and the v1.0 QC result (docs/qc_flagged.md)."""
    labels = ['几段原声拼起来当参考\n（中间留 0.3 秒）', '几段原声拼起来当参考\n（不留间隔）', '只用这一句自己的原声',
              '再加自动挑选和重配\n（最终 v1.0）']
    vals = [60, 76, 22, 44 / 4066 * 100]
    cols = [RED, RED, GOLD, GREEN]
    f = fig(8)
    f.text(0.04, 0.92, '“说话中间卡一下”的句子占多少', color=FG, fontsize=24, weight='bold')
    f.text(0.04, 0.865, '同一批台词，只换音色参考的给法', color=DIM, fontsize=17)
    ax = f.add_axes([0.06, 0.2, 0.9, 0.6], facecolor=BG)
    b = ax.bar(range(4), vals, color=cols, width=0.58)
    for r, v in zip(b, vals):
        ax.text(r.get_x() + r.get_width() / 2, v + 2, f'{v:.0f}%' if v >= 2 else f'{v:.1f}%', ha='center', color=FG,
                fontsize=24, weight='bold')
    ax.set_xticks(range(4))
    ax.set_xticklabels(labels, color=FG, fontsize=17)
    ax.set_ylim(0, 90)
    ax.set_yticks([0, 25, 50, 75])
    ax.set_yticklabels(['0', '25%', '50%', '75%'], color=DIM, fontsize=15)
    ax.grid(axis='y', color=GRID, lw=1)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0, pad=10)
    f.text(0.04, 0.035, '最后一栏是单位语音和播报全部 4066 句里，自动质检仍标出问题的比例（含读音），这些句子都人工听过。',
           color=DIM, fontsize=15)
    save(f, 'fig4_pauses.png')


def spectrum():
    import librosa
    import soundfile as sf
    a, b = 1.5, 15.6                     # the Krukov briefing excerpt used in the demo video
    en, sr = sf.read(os.path.join(ROOT, 'work', 'demo', 'a01mm01_en.wav'))
    zh, _ = sf.read(os.path.join(ROOT, 'work', 'demo', 'a01mm01_zh.wav'))
    sl = slice(int(a * sr), int(b * sr))

    def spec(x):
        s = np.abs(librosa.stft(x[sl].astype(np.float32), n_fft=2048, hop_length=480))
        return 20 * np.log10(s + 1e-7)
    panels = [(en[:, 1], '原版 · 中置声道', '英文对白'), (zh[:, 1], '中文版 · 中置声道', '换成中文配音'),
              (en[:, 0], '原版 · 左前声道', '英文也"漏"进了这里'), (zh[:, 0], '中文版 · 左前声道', '英文已去掉，只剩音乐和音效')]
    specs = [spec(x) for x, _, _ in panels]
    top = max(s.max() for s in specs)
    f = fig(9.4)
    f.text(0.04, 0.935, '过场视频：不只是换掉对白声道', color=FG, fontsize=24, weight='bold')
    f.text(0.04, 0.89, '盟军第一关简报（库可夫）14 秒的声谱，越亮表示这个频率的声音越响；人声是一条条横向的亮纹', color=DIM, fontsize=16)
    fmax = 6000
    nbin = int(fmax / (sr / 2) * 1025)
    for i, ((_, t, s), sp) in enumerate(zip(panels, specs)):
        r, c = divmod(i, 2)
        ax = f.add_axes([0.05 + c * 0.47, 0.47 - r * 0.42, 0.43, 0.33], facecolor=BG)
        ax.imshow(sp[:nbin], origin='lower', aspect='auto', cmap='magma', vmin=top - 75, vmax=top,
                  extent=[0, b - a, 0, fmax / 1000])
        ax.set_title(t, color=FG, fontsize=19, loc='left', weight='bold', pad=8)
        ax.text(0.99, 1.03, s, transform=ax.transAxes, ha='right', va='bottom', color=GREEN if r == 1 and c == 1 else DIM,
                fontsize=16)
        ax.tick_params(colors=DIM, labelsize=13, length=0)
        ax.set_ylabel('kHz', color=DIM, fontsize=13)
        if r == 1:
            ax.set_xlabel('秒', color=DIM, fontsize=13)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
    save(f, 'fig5_spectrum.png')


def pitch():
    """Movie dubs: median pitch of the dub vs its clean English line, before and after the clean-reference re-dub."""
    lo, hi = 0.72, 1.39                  # tools/speakers.py F0_LO / F0_HI
    runs = [(n, json.load(open(os.path.join(DATA, f'pitch_{n}.json')))) for n in ('before', 'after')
            if os.path.exists(os.path.join(DATA, f'pitch_{n}.json'))]
    f = fig(8.6)
    f.text(0.04, 0.93, '过场配音的声线对不对：音高对比', color=FG, fontsize=24, weight='bold')
    f.text(0.04, 0.885, '每个点是一句台词。横轴是原版演员这句话的音高，纵轴是中文配音的音高；落在虚线带外，基本就是男女声配反了',
           color=DIM, fontsize=15)
    titles = {'before': '修正前', 'after': '换干净参考重配后'}
    for i, (n, d) in enumerate(runs):
        ax = f.add_axes([0.06 + i * 0.47, 0.11, 0.41, 0.68], facecolor=BG)
        p = np.array([v for v in d.values() if v[0] > 0 and v[1] > 0])
        bad = (p[:, 1] / p[:, 0] < lo) | (p[:, 1] / p[:, 0] > hi)
        ax.scatter(p[~bad, 0], p[~bad, 1], s=7, color=BLUE, alpha=0.5, lw=0)
        ax.scatter(p[bad, 0], p[bad, 1], s=14, color=RED, alpha=0.9, lw=0)
        xs = np.array([60, 520])
        ax.plot(xs, xs, color=DIM, lw=1)
        ax.fill_between(xs, xs * lo, xs * hi, color='#ffffff', alpha=0.05)
        ax.plot(xs, xs * lo, color=DIM, lw=1, ls='--')
        ax.plot(xs, xs * hi, color=DIM, lw=1, ls='--')
        ax.set_xlim(60, 520)
        ax.set_ylim(60, 520)
        ax.set_title(f'{titles[n]}：{bad.sum()} 句声线明显不对（共 {len(p)} 句）', color=RED if bad.sum() else GREEN,
                     fontsize=19, loc='left', weight='bold', pad=10)
        ax.set_xlabel('原版音高（Hz）', color=DIM, fontsize=14)
        ax.set_ylabel('中文配音音高（Hz）', color=DIM, fontsize=14)
        ax.tick_params(colors=DIM, labelsize=12, length=0)
        ax.grid(color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.text(110, 450, '女声配给了男声角色', color=DIM, fontsize=13)
        ax.text(330, 90, '男声配给了女声角色', color=DIM, fontsize=13)
    save(f, 'fig6_pitch.png')


def funnel():
    """How the wrong-voice movie lines were run down (numbers from work/speakers/*.json, 2026-10-13)."""
    steps = [(207, '第一版过场配音', '声纹 + 音高检查标出的可疑句子', RED),
             (145, '换上干净的参考音，重配 1331 句后', '同样的检查再跑一遍', GOLD),
             (35, '用更准的音高算法复核', '短句音高容易测错八度，排除误报', GOLD),
             (4, '可疑的句子每句配 6 版，只留声线对的', '剩下的人工逐句听', GREEN)]
    f = fig(8.4)
    f.text(0.04, 0.925, '过场里“谁在说话”：一步步把配错声线的句子揪出来', color=FG, fontsize=24, weight='bold')
    f.text(0.04, 0.875, '一共 2782 句过场台词', color=DIM, fontsize=16)
    ax = f.add_axes([0.04, 0.06, 0.92, 0.76], facecolor=BG)
    ax.set_xlim(0, 100)
    ax.set_ylim(-0.6, len(steps) - 0.4)
    ax.axis('off')
    top = steps[0][0]
    for i, (n, t, s, c) in enumerate(steps):
        y = len(steps) - 1 - i
        w = max(1.2, 46 * n / top)
        ax.barh(y, w, left=0, height=0.62, color=c)
        ax.text(w + 1.2, y + 0.06, f'{n} 句', color=FG, fontsize=26, weight='bold', va='center')
        ax.text(62, y + 0.13, t, color=FG, fontsize=18, va='center', weight='bold')
        ax.text(62, y - 0.2, s, color=DIM, fontsize=15, va='center')
    save(f, 'fig6_voices.png')


if __name__ == '__main__':
    todo = sys.argv[1:] or ['load', 'pipeline', 'pauses', 'spectrum', 'funnel']
    for t in todo:
        {'load': load_order, 'pipeline': pipeline, 'pauses': pauses, 'spectrum': spectrum, 'pitch': pitch, 'funnel': funnel}[t]()
