// FxLoad.exe [--pool] <file.fxo>... : load each compiled effect with the game's D3DX (d3dx9_35, 32-bit) on a real
// device, the way RA3 does, and print OK / the HRESULT and compiler errors. With --pool all effects share one
// D3DX effect pool (RA3 shares "shared" parameters across its shaders).
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;

static class FxLoad
{
    [DllImport("d3d9.dll")] static extern IntPtr Direct3DCreate9(uint sdk);
    [DllImport("d3dx9_35.dll")] static extern int D3DXCreateEffect(IntPtr dev, byte[] data, uint len, IntPtr macros, IntPtr include,
                                                                   uint flags, IntPtr pool, out IntPtr effect, out IntPtr errors);
    [DllImport("d3dx9_35.dll")] static extern int D3DXCreateEffectPool(out IntPtr pool);

    [StructLayout(LayoutKind.Sequential)]
    struct PresentParams
    {
        public uint W, H, Format, Count, MsType, MsQuality, Swap; public IntPtr Wnd; public int Windowed, AutoDepth;
        public uint DepthFormat, Flags, Refresh, Interval;
    }
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate int CreateDeviceFn(IntPtr self, uint adapter, uint type, IntPtr wnd, uint flags, ref PresentParams pp, out IntPtr dev);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate IntPtr BufPtrFn(IntPtr self);
    [UnmanagedFunctionPointer(CallingConvention.StdCall)]
    delegate uint ReleaseFn(IntPtr self);

    static T Vt<T>(IntPtr obj, int slot) where T : class
    {
        IntPtr vt = Marshal.ReadIntPtr(obj);
        return (T)(object)Marshal.GetDelegateForFunctionPointer(Marshal.ReadIntPtr(vt, slot * IntPtr.Size), typeof(T));
    }

    [STAThread]
    static int Main(string[] args)
    {
        var form = new Form { Width = 64, Height = 64, ShowInTaskbar = false };
        var d3d = Direct3DCreate9(32);
        var pp = new PresentParams { W = 64, H = 64, Format = 22 /*X8R8G8B8*/, Count = 1, Swap = 1 /*DISCARD*/, Wnd = form.Handle,
                                     Windowed = 1, AutoDepth = 1, DepthFormat = 75 /*D24S8*/ };
        IntPtr dev;
        int hr = Vt<CreateDeviceFn>(d3d, 16)(d3d, 0, 1 /*HAL*/, form.Handle, 0x40 /*HARDWARE_VERTEXPROCESSING*/, ref pp, out dev);
        if (hr < 0) { Console.WriteLine("CreateDevice failed 0x" + hr.ToString("X8")); return 2; }
        IntPtr pool = IntPtr.Zero;
        int bad = 0;
        foreach (var a in args)
        {
            if (a == "--pool") { D3DXCreateEffectPool(out pool); continue; }
            var data = File.ReadAllBytes(a);
            IntPtr fx, err;
            hr = D3DXCreateEffect(dev, data, (uint)data.Length, IntPtr.Zero, IntPtr.Zero, 0, pool, out fx, out err);
            string msg = "";
            if (err != IntPtr.Zero) msg = Marshal.PtrToStringAnsi(Vt<BufPtrFn>(err, 3)(err));
            Console.WriteLine((hr < 0 ? "FAIL 0x" + hr.ToString("X8") : "OK  ") + "  " + Path.GetFileName(a) + (msg.Length > 0 ? "  | " + msg.Trim().Replace("\n", " / ") : ""));
            if (hr < 0) bad++;
            // keep effects alive so pooled shared parameters stay registered, like the game
        }
        return bad;
    }
}
