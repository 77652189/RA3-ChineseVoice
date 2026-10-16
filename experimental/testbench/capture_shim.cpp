// CNVoice RA3 test bench: 32-bit d3d9.dll proxy that saves frames without the window having to be on screen.
//
// Lives only in the test bench copy of the game (experimental/testbench/make_bench.ps1), never in the Steam folder.
// Forwards everything to d3d9_next.dll next to it (the bench's renamed SAGE-Unlocked d3d9.dll, so the bench runs
// like the player's game) or, without one, to the system d3d9. Hooks IDirect3DDevice9::Present:
//   - a file "shot.req" in the shot folder: the next frame is saved as shot_<ms>.bmp, then the request is deleted
//     (its first line, if any, becomes the file name instead)
//   - CNV_SHOT_MS=<n>: also save a frame every n ms
//   - cnv_testbench.log: device setup and frames presented per second (does the game keep drawing in background?)
// Shot folder: CNV_SHOT_DIR, default <dll folder>\..\shots.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d9.h>
#include <stdio.h>
#include <stdlib.h>

static HMODULE g_next, g_system;
static FILE *g_log;
static WCHAR g_dir[MAX_PATH];
static DWORD g_every, g_t0, g_last_shot, g_sec_start;
static int g_frames_this_sec, g_frame;

static void logf(const char *fmt, ...)
{
    if (!g_log) return;
    va_list a;
    va_start(a, fmt);
    fprintf(g_log, "%9lu ", GetTickCount() - g_t0);
    vfprintf(g_log, fmt, a);
    va_end(a);
    fflush(g_log);
}

typedef HRESULT(STDMETHODCALLTYPE *Present_t)(IDirect3DDevice9 *, const RECT *, const RECT *, HWND, const RGNDATA *);
typedef HRESULT(STDMETHODCALLTYPE *CreateDevice_t)(IDirect3D9 *, UINT, D3DDEVTYPE, HWND, DWORD, D3DPRESENT_PARAMETERS *, IDirect3DDevice9 **);
typedef HRESULT(STDMETHODCALLTYPE *EndScene_t)(IDirect3DDevice9 *);
typedef HRESULT(STDMETHODCALLTYPE *SwapPresent_t)(IDirect3DSwapChain9 *, const RECT *, const RECT *, HWND, const RGNDATA *, DWORD);
static Present_t o_Present;
static CreateDevice_t o_CreateDevice;
static EndScene_t o_EndScene;
static SwapPresent_t o_SwapPresent;
static void **g_dev_vt;
static IDirect3DDevice9 *g_dev;
static int g_presents, g_endscenes, g_swappresents, g_repatched;

static bool write_bmp(const WCHAR *path, const D3DLOCKED_RECT &lr, UINT w, UINT h)
{
    FILE *f = _wfopen(path, L"wb");
    if (!f) return false;
    DWORD row = (w * 3 + 3) & ~3u;
    BITMAPFILEHEADER fh = {0x4D42, (DWORD)(sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER) + row * h), 0, 0,
                           sizeof(BITMAPFILEHEADER) + sizeof(BITMAPINFOHEADER)};
    BITMAPINFOHEADER ih = {sizeof(ih), (LONG)w, (LONG)h, 1, 24, BI_RGB, row * h};
    fwrite(&fh, sizeof fh, 1, f);
    fwrite(&ih, sizeof ih, 1, f);
    BYTE *line = (BYTE *)calloc(row, 1);
    for (UINT y = 0; y < h; y++)       // BMP rows go bottom-up; X8R8G8B8 is B,G,R,X in memory
    {
        const BYTE *src = (const BYTE *)lr.pBits + (size_t)(h - 1 - y) * lr.Pitch;
        for (UINT x = 0; x < w; x++)
        {
            line[x * 3 + 0] = src[x * 4 + 0];
            line[x * 3 + 1] = src[x * 4 + 1];
            line[x * 3 + 2] = src[x * 4 + 2];
        }
        fwrite(line, row, 1, f);
    }
    free(line);
    fclose(f);
    return true;
}

static void shoot(IDirect3DDevice9 *d, const WCHAR *name)
{
    IDirect3DSurface9 *bb = 0, *rt = 0, *sys = 0;
    D3DSURFACE_DESC desc;
    HRESULT hr = d->GetBackBuffer(0, 0, D3DBACKBUFFER_TYPE_MONO, &bb);
    if (FAILED(hr)) { logf("shot: GetBackBuffer 0x%08lx\n", hr); return; }
    bb->GetDesc(&desc);
    IDirect3DSurface9 *src = bb;
    // a multisampled back buffer cannot be read back directly: resolve it into a plain render target first
    if (desc.MultiSampleType != D3DMULTISAMPLE_NONE &&
        SUCCEEDED(d->CreateRenderTarget(desc.Width, desc.Height, desc.Format, D3DMULTISAMPLE_NONE, 0, FALSE, &rt, 0)) &&
        SUCCEEDED(d->StretchRect(bb, 0, rt, 0, D3DTEXF_NONE)))
        src = rt;
    hr = d->CreateOffscreenPlainSurface(desc.Width, desc.Height, desc.Format, D3DPOOL_SYSTEMMEM, &sys, 0);
    if (SUCCEEDED(hr)) hr = d->GetRenderTargetData(src, sys);
    D3DLOCKED_RECT lr;
    if (SUCCEEDED(hr) && SUCCEEDED(hr = sys->LockRect(&lr, 0, D3DLOCK_READONLY)))
    {
        WCHAR path[MAX_PATH];
        wsprintfW(path, L"%s\\%s.bmp", g_dir, name);
        bool ok = (desc.Format == D3DFMT_X8R8G8B8 || desc.Format == D3DFMT_A8R8G8B8) && write_bmp(path, lr, desc.Width, desc.Height);
        sys->UnlockRect();
        logf("shot %ls %ux%u fmt %d ms %d -> %s\n", name, desc.Width, desc.Height, desc.Format, desc.MultiSampleType, ok ? "ok" : "FAILED");
    }
    else
        logf("shot: readback 0x%08lx (fmt %d ms %d)\n", hr, desc.Format, desc.MultiSampleType);
    if (sys) sys->Release();
    if (rt) rt->Release();
    bb->Release();
}

static void on_frame(IDirect3DDevice9 *d, HWND w)
{
    DWORD now = GetTickCount();
    g_frame++;
    g_frames_this_sec++;
    if (now - g_sec_start >= 1000)
    {
        HWND fg = GetForegroundWindow();
        DWORD pid = 0;
        if (fg) GetWindowThreadProcessId(fg, &pid);
        logf("fps %d (frame %d; Present %d, SwapChain::Present %d, EndScene %d, re-hooked %d; foreground %s)\n",
             g_frames_this_sec, g_frame, g_presents, g_swappresents, g_endscenes, g_repatched,
             pid == GetCurrentProcessId() ? "game" : "other");
        g_frames_this_sec = 0;
        g_sec_start = now;
    }
    WCHAR req[MAX_PATH], name[MAX_PATH] = L"";
    wsprintfW(req, L"%s\\shot.req", g_dir);
    FILE *f = _wfopen(req, L"r");
    if (f)
    {
        char line[200] = "";
        if (fgets(line, sizeof line, f))
        {
            for (char *p = line; *p; p++)
                if (*p == '\r' || *p == '\n' || *p == '\\' || *p == '/' || *p == ':') *p = 0;
            MultiByteToWideChar(CP_UTF8, 0, line, -1, name, MAX_PATH);
        }
        fclose(f);
        DeleteFileW(req);
        if (!name[0]) wsprintfW(name, L"shot_%lu", now - g_t0);
        shoot(d, name);
    }
    else if (g_every && now - g_last_shot >= g_every)
    {
        g_last_shot = now;
        wsprintfW(name, L"auto_%07lu", now - g_t0);
        shoot(d, name);
    }
}

static HRESULT STDMETHODCALLTYPE h_Present(IDirect3DDevice9 *d, const RECT *a, const RECT *b, HWND w, const RGNDATA *r)
{
    g_presents++;
    on_frame(d, w);
    return o_Present(d, a, b, w, r);
}

static HRESULT STDMETHODCALLTYPE h_SwapPresent(IDirect3DSwapChain9 *sc, const RECT *a, const RECT *b, HWND w, const RGNDATA *r, DWORD fl)
{
    g_swappresents++;
    if (g_dev) on_frame(g_dev, w);
    return o_SwapPresent(sc, a, b, w, r, fl);
}

template <class T> static void patch(void **vt, int index, T hook, T &orig)
{
    DWORD old;
    VirtualProtect(&vt[index], sizeof(void *), PAGE_EXECUTE_READWRITE, &old);
    orig = (T)vt[index];
    vt[index] = (void *)hook;
    VirtualProtect(&vt[index], sizeof(void *), old, &old);
}

static HRESULT STDMETHODCALLTYPE h_Present(IDirect3DDevice9 *, const RECT *, const RECT *, HWND, const RGNDATA *);

static HRESULT STDMETHODCALLTYPE h_EndScene(IDirect3DDevice9 *d)
{
    g_endscenes++;
    if (g_dev_vt && g_dev_vt[17] != (void *)h_Present)
    {
        patch(g_dev_vt, 17, h_Present, o_Present);   // chain to whatever is there now
        if (g_repatched++ < 5) logf("Present hook was overwritten, hooked again over %p\n", (void *)o_Present);
    }
    // nobody presents through a hooked path: fall back to taking frames at the end of each scene
    if (g_endscenes > 300 && !g_presents && !g_swappresents) on_frame(d, 0);
    return o_EndScene(d);
}

// SAGE-Unlocked swaps the device's vtable pointer for its own copy some time after CreateDevice, which bypasses
// hooks put into the original table: watch the pointer and hook whatever table the device uses now.
static DWORD WINAPI watch_vtable(LPVOID)
{
    void **seen = g_dev_vt;
    for (;;)
    {
        Sleep(100);
        void **vt = *(void ***)g_dev;
        if (vt != seen)
        {
            logf("device vtable moved %p -> %p, hooking the new one\n", (void *)seen, (void *)vt);
            seen = g_dev_vt = vt;
        }
        if (vt[17] != (void *)h_Present) patch(vt, 17, h_Present, o_Present), g_repatched++;
        if (vt[42] != (void *)h_EndScene) patch(vt, 42, h_EndScene, o_EndScene), g_repatched++;
    }
}

static HRESULT STDMETHODCALLTYPE h_CreateDevice(IDirect3D9 *d3d, UINT ad, D3DDEVTYPE type, HWND wnd, DWORD flags,
                                                D3DPRESENT_PARAMETERS *pp, IDirect3DDevice9 **out)
{
    HRESULT hr = o_CreateDevice(d3d, ad, type, wnd, flags, pp, out);
    logf("CreateDevice hr=0x%08lx %ux%u windowed %d fmt %d ms %d\n", hr, pp ? pp->BackBufferWidth : 0,
         pp ? pp->BackBufferHeight : 0, pp ? pp->Windowed : -1, pp ? pp->BackBufferFormat : -1, pp ? pp->MultiSampleType : -1);
    if (SUCCEEDED(hr) && out && *out && !o_Present)
    {
        g_dev = *out;
        g_dev_vt = *(void ***)*out;
        patch(g_dev_vt, 17, h_Present, o_Present);
        patch(g_dev_vt, 42, h_EndScene, o_EndScene);
        IDirect3DSwapChain9 *sc = 0;
        if (SUCCEEDED(g_dev->GetSwapChain(0, &sc)) && sc)
        {
            patch(*(void ***)sc, 3, h_SwapPresent, o_SwapPresent);
            sc->Release();
        }
        logf("device %p hooks: Present, EndScene, SwapChain::Present\n", (void *)g_dev);
        CreateThread(0, 0, watch_vtable, 0, 0, 0);
    }
    return hr;
}

// ---------------------------------------------------------------- exports
typedef IDirect3D9 *(WINAPI *Create9_t)(UINT);

extern "C" IDirect3D9 *WINAPI Direct3DCreate9(UINT sdk)
{
    Create9_t real = (Create9_t)GetProcAddress(g_next ? g_next : g_system, "Direct3DCreate9");
    IDirect3D9 *d3d = real ? real(sdk) : 0;
    logf("Direct3DCreate9(%u) -> %p via %s\n", sdk, d3d, g_next ? "d3d9_next.dll" : "system d3d9");
    if (d3d && !o_CreateDevice)
        patch(*(void ***)d3d, 16, h_CreateDevice, o_CreateDevice);
    return d3d;
}

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
    g_t0 = g_sec_start = GetTickCount();
    WCHAR here[MAX_PATH], path[MAX_PATH];
    GetModuleFileNameW(inst, here, MAX_PATH);
    *wcsrchr(here, L'\\') = 0;
    if (!GetEnvironmentVariableW(L"CNV_SHOT_DIR", g_dir, MAX_PATH)) wsprintfW(g_dir, L"%s\\..\\shots", here);
    CreateDirectoryW(g_dir, 0);
    WCHAR every[32];
    if (GetEnvironmentVariableW(L"CNV_SHOT_MS", every, 32)) g_every = (DWORD)_wtoi(every);
    wsprintfW(path, L"%s\\cnv_testbench.log", g_dir);
    g_log = _wfopen(path, L"w");
    wsprintfW(path, L"%s\\d3d9_next.dll", here);
    g_next = LoadLibraryW(path);
    GetSystemDirectoryW(path, MAX_PATH);
    lstrcatW(path, L"\\d3d9.dll");
    g_system = LoadLibraryW(path);
    logf("CNVoice test bench shim: next %p, system d3d9 %p, shots in %ls, every %lu ms\n", g_next, g_system, g_dir, g_every);
#define RESOLVE(n) real_##n = (g_next ? (void *)GetProcAddress(g_next, #n) : 0); \
    if (!real_##n && g_system) real_##n = (void *)GetProcAddress(g_system, #n);
    FORWARDS(RESOLVE)
    return TRUE;
}
