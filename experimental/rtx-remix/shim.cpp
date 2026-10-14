// CNVoice RA3 -> RTX Remix camera shim (32-bit d3d9.dll proxy)
//
// RA3 never calls SetTransform: the camera reaches the GPU only as vertex shader constants
// (EA RegisterMap.fxh: ViewProjection c119-c122, camera position c123). RTX Remix needs the fixed
// function VIEW / PROJECTION matrices to find the camera, so this proxy
//   - forwards everything to the Remix bridge, renamed to d3d9_remix.dll next to this file
//   - watches SetVertexShaderConstantF for c119-c123
//   - before each draw, splits ViewProjection into a view and a perspective projection and calls
//     SetTransform(VIEW / PROJECTION), WORLD = identity (vertex capture already gives world positions)
// Log: cnv_rtx_shim.log next to the dll (first frames' matrices, so the split can be checked offline).
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d9.h>
#include <math.h>
#include <stdio.h>

static HMODULE g_remix, g_system;
static FILE *g_log;
static int g_logged;

static void logf(const char *fmt, ...)
{
    if (!g_log) return;
    va_list a;
    va_start(a, fmt);
    vfprintf(g_log, fmt, a);
    va_end(a);
    fflush(g_log);
}

// ---------------------------------------------------------------- camera state
static float g_c[5][4];          // c119..c123 as the game last wrote them
static float g_light[7][4];      // c4 ambient, c5..c10 three directional lights (float3 Color, float3 Direction-to-light)
static bool g_dirty, g_have, g_lights_dirty;
static int g_frame, g_draws, g_pushes, g_total_draws;
static int g_mode;               // what Remix was last told: 0 nothing, 1 3D camera, 2 orthographic (UI, shadow map)
// object transform: c124-c127 = world matrix of rigid (non-skinned) meshes; skinned meshes write bones from c128
static float g_world[4][4];
static int g_world_kind;         // 1 rigid (g_world valid), 0 skinned / unknown (identity)
static int g_world_ver, g_world_sent = -1;

typedef HRESULT(STDMETHODCALLTYPE *SetVSConstF_t)(IDirect3DDevice9 *, UINT, const float *, UINT);
typedef SetVSConstF_t SetPSConstF_t;
typedef HRESULT(STDMETHODCALLTYPE *DrawPrim_t)(IDirect3DDevice9 *, D3DPRIMITIVETYPE, UINT, UINT);
typedef HRESULT(STDMETHODCALLTYPE *DrawIdx_t)(IDirect3DDevice9 *, D3DPRIMITIVETYPE, INT, UINT, UINT, UINT, UINT);
typedef HRESULT(STDMETHODCALLTYPE *DrawPrimUP_t)(IDirect3DDevice9 *, D3DPRIMITIVETYPE, UINT, const void *, UINT);
typedef HRESULT(STDMETHODCALLTYPE *DrawIdxUP_t)(IDirect3DDevice9 *, D3DPRIMITIVETYPE, UINT, UINT, UINT, const void *, D3DFORMAT, const void *, UINT);
typedef HRESULT(STDMETHODCALLTYPE *Present_t)(IDirect3DDevice9 *, const RECT *, const RECT *, HWND, const RGNDATA *);
typedef HRESULT(STDMETHODCALLTYPE *CreateDevice_t)(IDirect3D9 *, UINT, D3DDEVTYPE, HWND, DWORD, D3DPRESENT_PARAMETERS *, IDirect3DDevice9 **);

static SetVSConstF_t o_SetVSConstF;
static SetPSConstF_t o_SetPSConstF;
static DrawPrim_t o_DrawPrim;
static DrawIdx_t o_DrawIdx;
static DrawPrimUP_t o_DrawPrimUP;
static DrawIdxUP_t o_DrawIdxUP;
static Present_t o_Present;
static CreateDevice_t o_CreateDevice;

// M (row-vector convention, clip = [x y z 1] * M) from the registers; fxc packs float4x4 column-major,
// so register 119+c holds column c of M.
static void reg_matrix(float M[4][4], bool transposed)
{
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++)
            M[r][c] = transposed ? g_c[r][c] : g_c[c][r];
}

static float eye_w(const float M[4][4])
{
    const float *e = g_c[4];
    return e[0] * M[0][3] + e[1] * M[1][3] + e[2] * M[2][3] + M[3][3];
}

// Split M = V * P with P a left-handed D3D perspective. Returns false if M does not look like one.
static bool split_view_projection(const float Min[4][4], D3DMATRIX &V, D3DMATRIX &P)
{
    float M[4][4];
    float s = sqrtf(Min[0][3] * Min[0][3] + Min[1][3] * Min[1][3] + Min[2][3] * Min[2][3]);
    if (s < 1e-6f) return false;
    for (int r = 0; r < 4; r++)
        for (int c = 0; c < 4; c++)
            M[r][c] = Min[r][c] / s;
    float x[3] = {M[0][0], M[1][0], M[2][0]}, y[3] = {M[0][1], M[1][1], M[2][1]}, z[3] = {M[0][3], M[1][3], M[2][3]};
    float xs = sqrtf(x[0] * x[0] + x[1] * x[1] + x[2] * x[2]);
    float ys = sqrtf(y[0] * y[0] + y[1] * y[1] + y[2] * y[2]);
    if (xs < 1e-6f || ys < 1e-6f) return false;
    for (int i = 0; i < 3; i++) { x[i] /= xs; y[i] /= ys; }
    // right-handed game camera: mirror x so the view is a proper rotation; the projection takes the sign
    float cx = y[1] * z[2] - y[2] * z[1], cy = y[2] * z[0] - y[0] * z[2], cz = y[0] * z[1] - y[1] * z[0];
    if (cx * x[0] + cy * x[1] + cz * x[2] < 0) { for (int i = 0; i < 3; i++) x[i] = -x[i]; xs = -xs; }
    float tx = M[3][0] / xs, ty = M[3][1] / ys, tz = M[3][3];
    float A = M[0][2] * z[0] + M[1][2] * z[1] + M[2][2] * z[2];
    float B = M[3][2] - A * tz;
    ZeroMemory(&V, sizeof(V));
    ZeroMemory(&P, sizeof(P));
    for (int i = 0; i < 3; i++) { V.m[i][0] = x[i]; V.m[i][1] = y[i]; V.m[i][2] = z[i]; }
    V.m[3][0] = tx; V.m[3][1] = ty; V.m[3][2] = tz; V.m[3][3] = 1;
    P.m[0][0] = xs; P.m[1][1] = ys; P.m[2][2] = A; P.m[2][3] = 1; P.m[3][2] = B;
    return true;
}

static void count_draw()
{
    g_draws++;
    if (++g_total_draws % 200000 == 0) logf("%d draws, %d camera pushes\n", g_total_draws, g_pushes);
}

static void set_identity(IDirect3DDevice9 *dev)
{
    D3DMATRIX I;
    ZeroMemory(&I, sizeof(I));
    I.m[0][0] = I.m[1][1] = I.m[2][2] = I.m[3][3] = 1;
    dev->SetTransform(D3DTS_WORLD, &I);
    dev->SetTransform(D3DTS_VIEW, &I);
    dev->SetTransform(D3DTS_PROJECTION, &I);   // orthographic: Remix keeps such draws as rasterized UI
}

// the game's sun / fill lights as fixed function lights, which Remix turns into its own lights
static void push_lights(IDirect3DDevice9 *dev)
{
    if (!g_lights_dirty) return;
    g_lights_dirty = false;
    static int logged;
    for (int i = 0; i < 3; i++)
    {
        const float *col = g_light[1 + 2 * i], *dir = g_light[2 + 2 * i];
        bool on = col[0] + col[1] + col[2] > 0.001f;
        if (on)
        {
            D3DLIGHT9 l;
            ZeroMemory(&l, sizeof(l));
            l.Type = D3DLIGHT_DIRECTIONAL;
            l.Diffuse.r = col[0]; l.Diffuse.g = col[1]; l.Diffuse.b = col[2]; l.Diffuse.a = 1;
            l.Specular = l.Diffuse;
            l.Direction.x = -dir[0]; l.Direction.y = -dir[1]; l.Direction.z = -dir[2];   // game stores the direction towards the light
            dev->SetLight(i, &l);
        }
        dev->LightEnable(i, on);
        if (logged < 6)
        {
            logged++;
            logf("light %d: color %g %g %g dir %g %g %g %s\n", i, col[0], col[1], col[2], dir[0], dir[1], dir[2], on ? "on" : "off");
        }
    }
}

static void push_camera(IDirect3DDevice9 *dev)
{
    if (!g_dirty || !g_have) return;
    g_dirty = false;
    // orthographic ViewProjection (menus, in-game UI, the sun's shadow map): register 122 = 4th column = (0,0,0,1).
    // Hand it over unchanged so Remix sees an orthographic projection and keeps those draws as UI.
    if (fabsf(g_c[3][0]) < 1e-6f && fabsf(g_c[3][1]) < 1e-6f && fabsf(g_c[3][2]) < 1e-6f && fabsf(g_c[3][3] - 1) < 1e-6f)
    {
        D3DMATRIX O;
        float Mo[4][4];
        reg_matrix(Mo, false);
        memcpy(O.m, Mo, sizeof(Mo));
        set_identity(dev);
        dev->SetTransform(D3DTS_PROJECTION, &O);
        g_mode = 2;
        return;
    }
    g_pushes++;
    float M0[4][4], M1[4][4];
    reg_matrix(M0, false);
    reg_matrix(M1, true);
    float w0 = fabsf(eye_w(M0)), w1 = fabsf(eye_w(M1));
    const float (*M)[4] = w0 <= w1 ? M0 : M1;
    D3DMATRIX V, P, I;
    if (!split_view_projection(M, V, P))
    {
        static int fails;
        if (fails++ < 4)
        {
            logf("push %d: split failed, raw c119-c123:\n", g_pushes);
            for (int r = 0; r < 5; r++) logf("  c%d %10.4f %10.4f %10.4f %10.4f\n", 119 + r, g_c[r][0], g_c[r][1], g_c[r][2], g_c[r][3]);
        }
        return;
    }
    // water reflection renders with a camera mirrored below the surface: near / far come out invalid. Skip it
    // (Remix rasterizes those off-screen targets anyway), keep the main camera.
    float zn = -P.m[3][2] / P.m[2][2], zf = P.m[2][2] * zn / (P.m[2][2] - 1);
    if (!(zn > 0 && zf > zn)) return;
    (void)I;
    dev->SetTransform(D3DTS_VIEW, &V);
    dev->SetTransform(D3DTS_PROJECTION, &P);
    g_mode = 1;
    g_world_sent = -1;      // re-send the object transform
    push_lights(dev);
    static int ok;
    ok++;
    if (ok <= 3 || ok == 1000 || ok == 20000)	// first successful splits, then two later samples
    {
        g_logged++;
        logf("split ok, push %d frame %d draw %d: layout %s (eye w %g / %g)\n", g_pushes, g_frame, g_draws, w0 <= w1 ? "column-major" : "row-major", w0, w1);
        logf("  eye %g %g %g\n", g_c[4][0], g_c[4][1], g_c[4][2]);
        for (int r = 0; r < 4; r++) logf("  M %10.4f %10.4f %10.4f %10.4f\n", M[r][0], M[r][1], M[r][2], M[r][3]);
        for (int r = 0; r < 4; r++) logf("  V %10.4f %10.4f %10.4f %10.4f\n", V.m[r][0], V.m[r][1], V.m[r][2], V.m[r][3]);
        logf("  P xs %g ys %g A %g B %g -> near %g far %g\n", P.m[0][0], P.m[1][1], P.m[2][2], P.m[3][2],
             -P.m[3][2] / P.m[2][2], P.m[2][2] * (-P.m[3][2] / P.m[2][2]) / (P.m[2][2] - 1));
    }
}

// per draw, in 3D mode: the rigid mesh's world matrix (Remix then rebuilds object-space vertices from the capture and
// can track the object across frames); skinned meshes keep identity because their captured vertices already are world space
static void push_world(IDirect3DDevice9 *dev)
{
    if (g_mode != 1 || g_world_sent == g_world_ver) return;
    g_world_sent = g_world_ver;
    D3DMATRIX W;
    ZeroMemory(&W, sizeof(W));
    if (g_world_kind == 1)
    {
        // float4x4 packed column-major: register 124+c = column c; the last column of an affine matrix is (0,0,0,1)
        bool columns = fabsf(g_world[3][0]) < 1e-5f && fabsf(g_world[3][1]) < 1e-5f && fabsf(g_world[3][2]) < 1e-5f && fabsf(g_world[3][3] - 1) < 1e-5f;
        for (int r = 0; r < 4; r++)
            for (int c = 0; c < 4; c++)
                W.m[r][c] = columns ? g_world[c][r] : g_world[r][c];
        if (!columns) { W.m[0][3] = W.m[1][3] = W.m[2][3] = 0; W.m[3][3] = 1; }
        static int logged;
        if (logged < 3)
        {
            logged++;
            logf("world (%s):\n", columns ? "column-major" : "rows");
            for (int r = 0; r < 4; r++) logf("  W %10.4f %10.4f %10.4f %10.4f\n", W.m[r][0], W.m[r][1], W.m[r][2], W.m[r][3]);
        }
    }
    else
        W.m[0][0] = W.m[1][1] = W.m[2][2] = W.m[3][3] = 1;
    dev->SetTransform(D3DTS_WORLD, &W);
}

static void watch_world(UINT start, const float *data, UINT count)
{
    for (UINT i = 0; i < count; i++)
    {
        UINT reg = start + i;
        if (reg >= 124 && reg <= 127)
        {
            memcpy(g_world[reg - 124], data + 4 * i, 16);
            g_world_kind = 1;
            g_world_ver++;
        }
        else if (reg >= 128 && g_world_kind != 0)
        {
            g_world_kind = 0;
            g_world_ver++;
        }
    }
}

static void watch_lights(UINT start, const float *data, UINT count)
{
    for (UINT i = 0; i < count; i++)
    {
        UINT reg = start + i;
        if (reg >= 4 && reg <= 10 && memcmp(g_light[reg - 4], data + 4 * i, 16))
        {
            memcpy(g_light[reg - 4], data + 4 * i, 16);
            g_lights_dirty = true;
        }
    }
}

static HRESULT STDMETHODCALLTYPE h_SetVSConstF(IDirect3DDevice9 *dev, UINT start, const float *data, UINT count)
{
    for (UINT i = 0; i < count; i++)
    {
        UINT reg = start + i;
        if (reg >= 119 && reg <= 123)
        {
            memcpy(g_c[reg - 119], data + 4 * i, 16);
            g_dirty = true;
            if (reg == 122) g_have = true;
        }
    }
    watch_lights(start, data, count);
    watch_world(start, data, count);
    return o_SetVSConstF(dev, start, data, count);
}

static HRESULT STDMETHODCALLTYPE h_SetPSConstF(IDirect3DDevice9 *dev, UINT start, const float *data, UINT count)
{
    watch_lights(start, data, count);
    return o_SetPSConstF(dev, start, data, count);
}

static HRESULT STDMETHODCALLTYPE h_DrawPrim(IDirect3DDevice9 *d, D3DPRIMITIVETYPE t, UINT a, UINT b)
{ count_draw(); push_camera(d); push_world(d); return o_DrawPrim(d, t, a, b); }
static HRESULT STDMETHODCALLTYPE h_DrawIdx(IDirect3DDevice9 *d, D3DPRIMITIVETYPE t, INT a, UINT b, UINT c, UINT e, UINT f)
{ count_draw(); push_camera(d); push_world(d); return o_DrawIdx(d, t, a, b, c, e, f); }
static HRESULT STDMETHODCALLTYPE h_DrawPrimUP(IDirect3DDevice9 *d, D3DPRIMITIVETYPE t, UINT a, const void *b, UINT c)
{ count_draw(); push_camera(d); push_world(d); return o_DrawPrimUP(d, t, a, b, c); }
static HRESULT STDMETHODCALLTYPE h_DrawIdxUP(IDirect3DDevice9 *d, D3DPRIMITIVETYPE t, UINT a, UINT b, UINT c, const void *e, D3DFORMAT f, const void *g, UINT h)
{ count_draw(); push_camera(d); push_world(d); return o_DrawIdxUP(d, t, a, b, c, e, f, g, h); }
static HRESULT STDMETHODCALLTYPE h_Present(IDirect3DDevice9 *d, const RECT *a, const RECT *b, HWND c, const RGNDATA *e)
{
    if (g_frame < 3 || g_frame % 600 == 0) logf("frame %d: %d draws, camera regs seen %d\n", g_frame, g_draws, (int)g_have);
    g_frame++;
    g_draws = 0;
    g_dirty = true;   // re-send the camera at least once per frame
    return o_Present(d, a, b, c, e);
}

template <class T> static void patch(void **vt, int index, T hook, T &orig)
{
    DWORD old;
    VirtualProtect(&vt[index], sizeof(void *), PAGE_EXECUTE_READWRITE, &old);
    orig = (T)vt[index];
    vt[index] = (void *)hook;
    VirtualProtect(&vt[index], sizeof(void *), old, &old);
}

static HRESULT STDMETHODCALLTYPE h_CreateDevice(IDirect3D9 *d3d, UINT ad, D3DDEVTYPE type, HWND wnd, DWORD flags,
                                                D3DPRESENT_PARAMETERS *pp, IDirect3DDevice9 **out)
{
    HRESULT hr = o_CreateDevice(d3d, ad, type, wnd, flags, pp, out);
    logf("CreateDevice hr=0x%08lx %ux%u\n", hr, pp ? pp->BackBufferWidth : 0, pp ? pp->BackBufferHeight : 0);
    if (SUCCEEDED(hr) && out && *out && !o_SetVSConstF)
    {
        void **vt = *(void ***)*out;
        // IDirect3DDevice9 vtable slots
        patch(vt, 17, h_Present, o_Present);
        patch(vt, 81, h_DrawPrim, o_DrawPrim);
        patch(vt, 82, h_DrawIdx, o_DrawIdx);
        patch(vt, 83, h_DrawPrimUP, o_DrawPrimUP);
        patch(vt, 84, h_DrawIdxUP, o_DrawIdxUP);
        patch(vt, 94, h_SetVSConstF, o_SetVSConstF);
        patch(vt, 109, h_SetPSConstF, o_SetPSConstF);
        logf("device hooks installed\n");
    }
    return hr;
}

// ---------------------------------------------------------------- exports
typedef IDirect3D9 *(WINAPI *Create9_t)(UINT);

extern "C" IDirect3D9 *WINAPI Direct3DCreate9(UINT sdk)
{
    Create9_t real = (Create9_t)GetProcAddress(g_remix, "Direct3DCreate9");
    IDirect3D9 *d3d = real ? real(sdk) : 0;
    logf("Direct3DCreate9(%u) -> %p\n", sdk, d3d);
    if (d3d && !o_CreateDevice)
        patch(*(void ***)d3d, 16, h_CreateDevice, o_CreateDevice);
    return d3d;
}

// everything else goes straight through: to Remix when it has the export, otherwise to the system d3d9
#define FORWARDS(X) X(D3DPERF_BeginEvent) X(D3DPERF_EndEvent) X(D3DPERF_GetStatus) X(D3DPERF_QueryRepeatFrame) \
    X(D3DPERF_SetMarker) X(D3DPERF_SetOptions) X(D3DPERF_SetRegion) X(DebugSetLevel) X(DebugSetMute) \
    X(Direct3D9EnableMaximizedWindowedModeShim) X(Direct3DCreate9Ex) X(Direct3DCreate9On12) \
    X(Direct3DCreate9On12Ex) X(Direct3DShaderValidatorCreate9) X(PSGPError) X(PSGPSampleTexture)
#define PTR(n) extern "C" void *real_##n = 0;
FORWARDS(PTR)
#define STUB(n) extern "C" __declspec(naked) void stub_##n() { __asm jmp dword ptr [real_##n] }
FORWARDS(STUB)

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID)
{
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(inst);
    WCHAR dir[MAX_PATH], path[MAX_PATH];
    GetModuleFileNameW(inst, dir, MAX_PATH);
    *wcsrchr(dir, L'\\') = 0;
    wsprintfW(path, L"%s\\cnv_rtx_shim.log", dir);
    g_log = _wfopen(path, L"w");
    wsprintfW(path, L"%s\\d3d9_remix.dll", dir);
    g_remix = LoadLibraryW(path);
    GetSystemDirectoryW(path, MAX_PATH);
    lstrcatW(path, L"\\d3d9.dll");
    g_system = LoadLibraryW(path);
    logf("CNVoice RTX shim: remix %p, system d3d9 %p\n", g_remix, g_system);
#define RESOLVE(n) real_##n = (g_remix ? (void *)GetProcAddress(g_remix, #n) : 0); \
    if (!real_##n && g_system) real_##n = (void *)GetProcAddress(g_system, #n);
    FORWARDS(RESOLVE)
    return TRUE;
}
