"""AI route for the CNV light tank: text -> concept image (HunyuanDiT) -> 3D shape (Hunyuan3D-2), GPU-throttled.

The shape is untextured on purpose: cnv_lighttank.py's Blender bake (panel seams, grime, team mask) textures it
afterwards, so both versions of the tank get the same RA3 look and only the geometry differs.

  work/downloads/ra3gen_env/python.exe -I -X utf8 experimental/units/ai_lighttank.py concept [seeds...]
  work/downloads/ra3gen_env/python.exe -I -X utf8 experimental/units/ai_lighttank.py shape <concept.png> [seed]

Output in work/units/lighttank_ai/. Weights cache in work/downloads/hf (HF_HOME). gpu_limit.json (project root)
is honoured per denoising step: duty cycle and VRAM cap, read live through ra3voice/throttle.py.
Hunyuan3D / HunyuanDiT: Tencent Hunyuan non-commercial community licence (fine for a free mod; it excludes the
EU, UK and South Korea).
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DL = os.path.join(ROOT, 'work', 'downloads')
OUT = os.path.join(ROOT, 'work', 'units', 'lighttank_ai')
os.environ.setdefault('HF_HOME', os.path.join(DL, 'hf'))
os.environ.setdefault('HY3DGEN_MODELS', os.path.join(DL, 'hf', 'hy3dgen'))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(DL, 'hy3d_src', 'Hunyuan3D-2'))
import torch                                     # noqa: E402
from ra3voice import throttle                    # noqa: E402

# HunyuanDiT keeps only the first 60 characters of a prompt and appends ",白色背景,3D风格,最佳质量" itself
PROMPT = '未来盟军轻型坦克,银白色金属装甲,宽大分段履带,低矮圆润炮塔,单根长炮管,青色发光灯,前侧方视角,完整车身'


class Pace:
    """Per-step duty cycle: after each step sleep so GPU time / wall time = gpu_limit.json duty."""

    def __init__(self):
        self.t = time.time()

    def step(self, *_, **__):
        torch.cuda.synchronize()
        busy = time.time() - self.t
        duty = float(throttle.config().get('duty', 1.0))
        if 0 < duty < 1:
            time.sleep(busy * (1 - duty) / duty)
        self.t = time.time()
        return _[-1] if _ and isinstance(_[-1], dict) else {}


def concept(seeds):
    from diffusers import AutoPipelineForText2Image
    pipe = AutoPipelineForText2Image.from_pretrained(
        'Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled', torch_dtype=torch.float16,
        enable_pag=True, pag_applied_layers=['blocks.(16|17|18|19)'])
    pipe.enable_model_cpu_offload()             # text encoders and DiT take turns on the GPU (VRAM cap)
    pos = ',白色背景,3D风格,最佳质量'
    neg = '文本,特写,裁剪,出框,最差质量,低质量,JPEG伪影,重复,残缺,变异,畸形,模糊,糟糕的比例,卡通,玩具,人物'
    os.makedirs(OUT, exist_ok=True)
    for seed in seeds:
        pace = Pace()
        g = torch.Generator('cpu').manual_seed(seed)
        img = pipe(prompt=PROMPT[:60] + pos, negative_prompt=neg, num_inference_steps=25, pag_scale=1.3,
                   width=1024, height=1024, generator=g,
                   callback_on_step_end=lambda p, i, t, kw: pace.step(kw)).images[0]
        path = os.path.join(OUT, f'concept_{seed}.png')
        img.save(path)
        print('concept', path, flush=True)


def dino_keys(sd):
    """Hunyuan3D's checkpoint has DINOv2 weights in the transformers 4 layout; transformers 5 renamed them and
    split the SwiGLU input (same mapping as transformers' conversion_mapping.py 'Dinov2Model')."""
    out = {}
    for k, v in sd.items():
        for a, b in (('attention.attention.query', 'attention.q_proj'), ('attention.attention.key', 'attention.k_proj'),
                     ('attention.attention.value', 'attention.v_proj'), ('attention.output.dense', 'attention.o_proj'),
                     ('mlp.weights_out', 'mlp.down_proj')):
            k = k.replace(a, b)
        if 'mlp.weights_in.' in k:
            gate, up = v.chunk(2, dim=0)
            out[k.replace('weights_in', 'gate_proj')] = gate
            out[k.replace('weights_in', 'up_proj')] = up
        else:
            out[k] = v
    return out


def shape(image_path, seed=0):
    from PIL import Image
    from hy3dgen.rembg import BackgroundRemover
    from hy3dgen.shapegen.models import SingleImageEncoder
    load = SingleImageEncoder.load_state_dict
    SingleImageEncoder.load_state_dict = lambda self, sd, *a, **k: load(self, dino_keys(sd), *a, **k)
    from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline, FaceReducer, FloaterRemover, \
        DegenerateFaceRemover
    image = Image.open(image_path).convert('RGB')
    image = BackgroundRemover()(image)
    stem = os.path.splitext(os.path.basename(image_path))[0]
    image.save(os.path.join(OUT, stem + '_cut.png'))
    pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2', subfolder='hunyuan3d-dit-v2-0',
                                                            dtype=torch.float16, variant='fp16')
    pace = Pace()
    mesh = pipe(image=image, num_inference_steps=50, octree_resolution=320, num_chunks=4000,
                generator=torch.manual_seed(seed), callback=pace.step, callback_steps=1)[0]
    for fix in (FloaterRemover(), DegenerateFaceRemover()):
        mesh = fix(mesh)
    mesh.export(os.path.join(OUT, f'{stem}_s{seed}_raw.glb'))
    mesh = FaceReducer()(mesh, max_facenum=40000)          # Blender decimates to game budget later
    path = os.path.join(OUT, f'{stem}_s{seed}.obj')
    mesh.export(path)
    print('shape', path, len(mesh.faces), 'faces', flush=True)


if __name__ == '__main__':
    throttle.setup(torch)
    os.makedirs(OUT, exist_ok=True)
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == 'concept':
        concept([int(a) for a in args] or [0, 1, 2, 3])
    elif cmd == 'shape':
        shape(args[0], int(args[1]) if len(args) > 1 else 0)
