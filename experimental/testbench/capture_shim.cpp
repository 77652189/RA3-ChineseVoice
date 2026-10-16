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

// ---------------------------------------------------------------- synthetic keys
// Posted WM_KEYDOWN does not skip movies: the game polls the keyboard. We patch its imports of GetAsyncKeyState /
// GetKeyState so that, while a request is active, the requested key reads as held down. Request: a file "key.req"
// in the shot folder holding a virtual-key code (decimal); it is held for 300 ms, then released.
typedef SHORT(WINAPI *GetKeyFn)(int);
static GetKeyFn o_GetAsyncKeyState, o_GetKeyState;
static volatile int g_fake_vk;
static volatile DWORD g_fake_until;
static int g_vk_seen[256];

static bool faked(int vk)
{
    if (vk > 0 && vk < 256 && g_vk_seen[vk]++ == 0) logf("game polls vk %d\n", vk);
    return g_fake_vk && vk == g_fake_vk && GetTickCount() < g_fake_until;
}
static SHORT WINAPI h_GetAsyncKeyState(int vk) { return faked(vk) ? (SHORT)0x8001 : o_GetAsyncKeyState(vk); }
static SHORT WINAPI h_GetKeyState(int vk) { return faked(vk) ? (SHORT)0xFF80 : o_GetKeyState(vk); }

// replace a function the main module imports from user32.dll
static void hook_import(const char *fn, void *hook, void **orig)
{
    BYTE *base = (BYTE *)GetModuleHandleW(0);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    for (IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base + dir.VirtualAddress); d->Name; d++)
    {
        if (lstrcmpiA((char *)(base + d->Name), "user32.dll")) continue;
        IMAGE_THUNK_DATA *names = (IMAGE_THUNK_DATA *)(base + (d->OriginalFirstThunk ? d->OriginalFirstThunk : d->FirstThunk));
        IMAGE_THUNK_DATA *iat = (IMAGE_THUNK_DATA *)(base + d->FirstThunk);
        for (; names->u1.AddressOfData; names++, iat++)
        {
            if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal)) continue;
            if (lstrcmpA(((IMAGE_IMPORT_BY_NAME *)(base + names->u1.AddressOfData))->Name, fn)) continue;
            DWORD old;
            VirtualProtect(&iat->u1.Function, sizeof(void *), PAGE_READWRITE, &old);
            *orig = (void *)iat->u1.Function;
            iat->u1.Function = (ULONG_PTR)hook;
            VirtualProtect(&iat->u1.Function, sizeof(void *), old, &old);
            logf("hooked import %s\n", fn);
            return;
        }
    }
    logf("import %s not found\n", fn);
}

// Hot-patch a user32 export in place (Windows' "mov edi,edi" prologue with 5 spare bytes before it), so every caller
// goes through the hook, also code that found the function with GetProcAddress. *orig = function + 2.
static bool hotpatch(const char *fn, void *hook, void **orig)
{
    BYTE *f = (BYTE *)GetProcAddress(GetModuleHandleW(L"user32.dll"), fn);
    DWORD old;
    if (f && f[0] == 0xE9)
    {
        // someone (the Steam overlay watches hotkeys) already put a jmp here: chain in front of it
        BYTE *target = f + 5 + *(LONG *)(f + 1);
        VirtualProtect(f, 5, PAGE_EXECUTE_READWRITE, &old);
        *orig = target;
        *(LONG *)(f + 1) = (LONG)((BYTE *)hook - (f + 5));
        VirtualProtect(f, 5, old, &old);
        FlushInstructionCache(GetCurrentProcess(), f, 5);
        logf("user32!%s already hooked (-> %p): chained in front\n", fn, (void *)target);
        return true;
    }
    if (!f || f[0] != 0x8B || f[1] != 0xFF) { logf("hotpatch %s: unknown prologue (%02x %02x)\n", fn, f ? f[0] : 0, f ? f[1] : 0); return false; }
    VirtualProtect(f - 5, 7, PAGE_EXECUTE_READWRITE, &old);
    *orig = f + 2;
    f[-5] = 0xE9;                                            // jmp hook
    *(DWORD *)(f - 4) = (DWORD)((BYTE *)hook - f);
    *(WORD *)f = 0xF9EB;                                     // jmp short -7 (to f-5)
    VirtualProtect(f - 5, 7, old, &old);
    FlushInstructionCache(GetCurrentProcess(), f - 5, 7);
    logf("hot-patched user32!%s\n", fn);
    return true;
}

typedef BOOL(WINAPI *GetKbState_t)(PBYTE);
static GetKbState_t o_GetKeyboardState;
static int g_kbstate_calls;
static BOOL WINAPI h_GetKeyboardState(PBYTE s)
{
    BOOL r = o_GetKeyboardState(s);
    if (g_kbstate_calls++ == 0) logf("game calls GetKeyboardState\n");
    if (r && g_fake_vk && GetTickCount() < g_fake_until) s[g_fake_vk] |= 0x80;
    return r;
}

// what key messages the game actually takes out of its queue
typedef BOOL(WINAPI *PeekMsg_t)(LPMSG, HWND, UINT, UINT, UINT);
typedef BOOL(WINAPI *GetMsg_t)(LPMSG, HWND, UINT, UINT);
static PeekMsg_t o_PeekMessageA;
static GetMsg_t o_GetMessageA;
static int g_keymsgs;
static void seen_msg(const MSG *m)
{
    if ((m->message >= WM_KEYFIRST && m->message <= WM_KEYLAST) || m->message == WM_INPUT)
        if (g_keymsgs++ < 40) logf("game took msg 0x%04x wParam %u lParam %08lx\n", m->message, (UINT)m->wParam, (DWORD)m->lParam);
}
static BOOL WINAPI h_PeekMessageA(LPMSG m, HWND h, UINT a, UINT b, UINT rm)
{
    BOOL r = o_PeekMessageA(m, h, a, b, rm);
    if (r && (rm & PM_REMOVE)) seen_msg(m);
    return r;
}
static BOOL WINAPI h_GetMessageA(LPMSG m, HWND h, UINT a, UINT b)
{
    BOOL r = o_GetMessageA(m, h, a, b);
    if (r > 0) seen_msg(m);
    return r;
}

// the bench must not take the user's desktop: refuse the game's requests to come to the front (logged)
typedef BOOL(WINAPI *HwndFn_t)(HWND);
static HwndFn_t o_SetForegroundWindow, o_BringWindowToTop;
static int g_front_blocked;
static BOOL WINAPI h_SetForegroundWindow(HWND h)
{
    if (g_front_blocked++ < 10) logf("blocked SetForegroundWindow(%p)\n", (void *)h);
    return TRUE;
}
static BOOL WINAPI h_BringWindowToTop(HWND h)
{
    if (g_front_blocked++ < 10) logf("blocked BringWindowToTop(%p)\n", (void *)h);
    return TRUE;
}

static void poll_key_request()
{
    WCHAR req[MAX_PATH];
    wsprintfW(req, L"%s\\key.req", g_dir);
    FILE *f = _wfopen(req, L"r");
    if (!f) return;
    int vk = 0;
    fscanf(f, "%d", &vk);
    fclose(f);
    DeleteFileW(req);
    g_fake_vk = vk;
    g_fake_until = GetTickCount() + 300;
    logf("key request: vk %d held 300 ms\n", vk);
}

// SAGE-Unlocked swaps the device's vtable pointer for its own copy some time after CreateDevice, which bypasses
// hooks put into the original table: watch the pointer and hook whatever table the device uses now.
static DWORD WINAPI watch_vtable(LPVOID)
{
    void **seen = g_dev_vt;
    for (int tick = 0;; tick++)
    {
        Sleep(100);
        poll_key_request();
        if (tick == 200)
            logf("loaded: dinput8 %p, dinput %p, xinput1_3 %p\n", (void *)GetModuleHandleW(L"dinput8.dll"),
                 (void *)GetModuleHandleW(L"dinput.dll"), (void *)GetModuleHandleW(L"xinput1_3.dll"));
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
        hotpatch("GetAsyncKeyState", (void *)h_GetAsyncKeyState, (void **)&o_GetAsyncKeyState);
        hotpatch("GetKeyState", (void *)h_GetKeyState, (void **)&o_GetKeyState);
        hotpatch("GetKeyboardState", (void *)h_GetKeyboardState, (void **)&o_GetKeyboardState);
        hotpatch("SetForegroundWindow", (void *)h_SetForegroundWindow, (void **)&o_SetForegroundWindow);
        hotpatch("BringWindowToTop", (void *)h_BringWindowToTop, (void **)&o_BringWindowToTop);
        hook_import("PeekMessageA", (void *)h_PeekMessageA, (void **)&o_PeekMessageA);
        hook_import("GetMessageA", (void *)h_GetMessageA, (void **)&o_GetMessageA);
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
