"""fix_noinit.py <shader_src_dir>: make EA's RA3 shader source compile with the June 2010 fxc.
That preprocessor rejects empty macro arguments, and EA passes NO_INITIALIZER (an empty macro) as the last argument
of REGISTER_BIND*. Add *_NI variants without the initializer parameter and use them at those call sites.
The expanded HLSL is identical."""
import os, re, sys

d = sys.argv[1]
rm = os.path.join(d, 'RegisterMap.fxh')
t = open(rm, encoding='latin-1').read()
out = []
for line in t.splitlines(keepends=True):
    out.append(line)
    m = re.match(r'(\s*#define (REGISTER_BIND\w*)\(([^)]*), initializer\))(.*?)(\r?\n)$', line)
    if m and not m.group(2).endswith('_NI'):
        body = re.sub(r'\s*\binitializer\s*$', '', m.group(4))
        out.append('%s#define %s_NI(%s)%s%s' % (re.match(r'\s*', line).group(0), m.group(2), m.group(3), body, m.group(5)))
open(rm, 'w', encoding='latin-1', newline='').write(''.join(out))

gp = os.path.join(d, 'GlobalParameters.fxh')
t = open(gp, encoding='latin-1').read()
n = 0


def repl(m):
    global n
    n += 1
    return m.group(1) + '_NI(' + m.group(2).rstrip().rstrip(',').rstrip() + ')'


t2 = re.sub(r'\b(REGISTER_BIND\w*)\(((?:[^()]|\([^()]*\))*?),\s*NO_INITIALIZER\s*\)', repl, t)
open(gp, 'w', encoding='latin-1', newline='').write(t2)
print('RegisterMap: added', sum('_NI(' in l for l in out), 'macros; GlobalParameters: rewrote', n, 'calls')
