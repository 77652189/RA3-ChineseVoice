"""Relight retail campaign missions: a mod BIG carrying only edited copies of their .map files (Light1 ...).

  python -I -X utf8 experimental/campaign/make_lightmod.py [preset] [map stem ...]
      -> Documents\\Red Alert 3\\Mods\\Light<n>\\  (default: preset vivid, camp_a01_brightonbeach_smith)

GlobalLighting holds four time-of-day groups of three lights (sun, accent 1, accent 2; light 0/3/6/9 carry the
ambient): morning, afternoon, evening, night, and the map's time of day (1..4) picks one (Brighton Beach 2,
Cannes 1, Heidelberg 3). The last 16 bytes start with the shadow colour (B, G, R, A; retail a0 a0 a0 7f).
Presets change only the active group, the shadow colour and the post effects (Bloom intensity, LookupTable blend).
Bench, Brighton Beach (work/testbench/light_a01_*.png): every preset shows in game, so retail missions can be
relit by shipping their .map alone; 'vivid' blows out the white pavilion, 'subtle' and 'crisp' are candidates.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import maplight                                  # noqa: E402
import mapscript                                 # noqa: E402
from ra3voice import big                         # noqa: E402

PRESETS = {
    # crisper daylight: stronger sun and accents, a touch more ambient, darker shadows, bloom on, richer LUT
    'vivid': dict(sun=1.2, accent=1.15, ambient=1.15, shadow=0.75, bloom=0.35, lut=0.75),
    # vivid blows out white buildings on Brighton Beach (no bloom in retail there): restrained version
    'subtle': dict(sun=1.08, accent=1.1, ambient=1.0, shadow=0.8, bloom=0.12, lut=0.7),
    # no bloom (kept as the map has it), deeper shadows and a stronger colour LUT: contrast instead of glow
    'crisp': dict(sun=1.1, accent=1.0, ambient=0.9, shadow=0.65, bloom=None, lut=0.85),
    # exaggerated, only to make the effect unmistakable on a bench frame
    'test': dict(sun=1.6, accent=1.4, ambient=1.5, shadow=0.4, bloom=0.8, lut=1.0),
}


def relight(m, p):
    lt = maplight.lighting(m)
    g = (lt['time_of_day'] - 1) * 3
    sun, a1, a2 = lt['lights'][g:g + 3]
    sun['color'] = [c * p['sun'] for c in sun['color']]
    sun['ambient'] = [c * p['ambient'] for c in sun['ambient']]
    for a in (a1, a2):
        a['color'] = [c * p['accent'] for c in a['color']]
    rest = bytearray(lt['rest'])
    rest[0:3] = bytes(int(v * p['shadow']) for v in rest[0:3])      # shadow colour B, G, R
    lt['rest'] = bytes(rest)
    maplight.set_lighting(m, lt)
    fx = maplight.post_effects(m)
    names = [n for n, _ in fx]
    if p['bloom'] is None:
        pass
    elif 'Bloom' not in names:
        fx.append(('Bloom', [('Intensity', 'Float', (p['bloom'],))]))
    else:
        fx[names.index('Bloom')] = ('Bloom', [('Intensity', 'Float', (p['bloom'],))])
    for k, (n, params) in enumerate(fx):
        if n == 'LookupTable':
            fx[k] = (n, [(pn, t, (p['lut'], 0.0, 0.0, 0.0) if pn == 'BlendFactor' else v) for pn, t, v in params])
    maplight.set_post_effects(m, fx)
    return lt['time_of_day']


def main():
    preset = sys.argv[1] if len(sys.argv) > 1 else 'vivid'
    stems = sys.argv[2:] or ['camp_a01_brightonbeach_smith']
    name = os.environ.get('CNV_LIGHT_NAME', 'Light' + {'vivid': '1', 'subtle': '2', 'crisp': '3'}.get(preset, 'T'))
    arc, maps = mapscript.campaign_maps()
    files = []
    for stem in stems:
        path = next(n for n in maps if n.lower().endswith(stem + '.map'))
        m = mapscript.MapFile(big.read_files(arc, [path])[path])
        tod = relight(m, PRESETS[preset])
        files.append((path, m.map_file()))
        print(f'{stem}: time of day {tod}, preset {preset}', maplight.post_effects(m))
    out = os.path.join(os.path.expanduser('~'), 'Documents', 'Red Alert 3', 'Mods', name)
    os.makedirs(out, exist_ok=True)
    big.write(os.path.join(out, f'{name}.big'), files)
    with open(os.path.join(out, f'{name}_1.0.skudef'), 'w', encoding='ascii', newline='') as f:
        f.write(f'mod-game 1.12\r\nadd-big {name}.big\r\n')
    print('->', out)


if __name__ == '__main__':
    main()
