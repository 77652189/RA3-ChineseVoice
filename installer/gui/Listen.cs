// 试听：直接从安装包自带的 files\<game>\CNVoice_*.big 里取出一句配音，解码后播放（不另外附带音频）。
// 索引 files\listen_index.json 由 tools/listen_index.py 生成；格式见那边的说明。
// 解码与 ra3voice 下的 Python 实现一致：xas.py（EA-XAS v1）、snr.py（SNR/SNS）、refpack.py、eaxa.py（EA-XA v2 过场音轨）。
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;

namespace CNVoiceInstaller
{
    class VoiceLine
    {
        public string Cat, Group, Zh, En, Game, Big, Entry, Kind;
        public int Rate, Channels;
        public double Start, Length;
        public string Shown { get { return Zh; } }
        public string Sub { get { return En; } }
        public string Where { get { return Group; } }
    }

    static class AudioLib
    {
        // ---------------------------------------------------------------- BIG
        static readonly Dictionary<string, Dictionary<string, long[]>> Indexes = new Dictionary<string, Dictionary<string, long[]>>();

        static uint BE(byte[] b, int p) { return (uint)(b[p] << 24 | b[p + 1] << 16 | b[p + 2] << 8 | b[p + 3]); }

        public static byte[] ReadEntry(string bigPath, string name)
        {
            Dictionary<string, long[]> idx;
            lock (Indexes)
                if (!Indexes.TryGetValue(bigPath, out idx))
                {
                    idx = new Dictionary<string, long[]>(StringComparer.OrdinalIgnoreCase);
                    using (var f = File.OpenRead(bigPath))
                    {
                        var head = new byte[16];
                        f.Read(head, 0, 16);
                        var count = BE(head, 8);
                        var size = (int)BE(head, 12);
                        var buf = new byte[size];
                        Array.Copy(head, buf, 16);
                        f.Read(buf, 16, size - 16);
                        int p = 16;
                        for (int i = 0; i < count; i++)
                        {
                            long off = BE(buf, p), len = BE(buf, p + 4);
                            p += 8;
                            int s = p;
                            while (buf[p] != 0) p++;
                            idx[Encoding.GetEncoding(28591).GetString(buf, s, p - s)] = new[] { off, len };
                            p++;
                        }
                    }
                    Indexes[bigPath] = idx;
                }
            long[] e;
            if (!idx.TryGetValue(name, out e)) throw new Exception("安装包里没有这一句：" + name);
            var data = new byte[e[1]];
            using (var f = File.OpenRead(bigPath))
            {
                f.Seek(e[0], SeekOrigin.Begin);
                int got = 0;
                while (got < data.Length) { int n = f.Read(data, got, data.Length - got); if (n <= 0) break; got += n; }
            }
            return data;
        }

        // ---------------------------------------------------------------- RefPack
        public static bool IsRefPack(byte[] d) { return d.Length >= 5 && (d[0] & 0x3E) == 0x10 && d[1] == 0xFB; }

        public static byte[] RefPack(byte[] d)
        {
            int flags = d[0], p = 2, nb = (flags & 0x80) != 0 ? 4 : 3;
            int size = 0;
            for (int i = 0; i < nb; i++) size = size << 8 | d[p + i];
            p += nb;
            if ((flags & 0x01) != 0) p += nb;
            var o = new byte[size];
            int w = 0;
            while (p < d.Length)
            {
                int b0 = d[p], lit, n, off;
                if (b0 < 0x80) { int b1 = d[p + 1]; p += 2; lit = b0 & 3; n = ((b0 & 0x1C) >> 2) + 3; off = ((b0 & 0x60) << 3) + b1 + 1; }
                else if (b0 < 0xC0) { int b1 = d[p + 1], b2 = d[p + 2]; p += 3; lit = b1 >> 6; n = (b0 & 0x3F) + 4; off = ((b1 & 0x3F) << 8) + b2 + 1; }
                else if (b0 < 0xE0) { int b1 = d[p + 1], b2 = d[p + 2], b3 = d[p + 3]; p += 4; lit = b0 & 3; n = ((b0 & 0x0C) << 6) + b3 + 5; off = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1; }
                else if (b0 < 0xFC) { p++; lit = ((b0 & 0x1F) << 2) + 4; Array.Copy(d, p, o, w, lit); p += lit; w += lit; continue; }
                else { p++; lit = b0 & 3; Array.Copy(d, p, o, w, lit); w += lit; break; }
                Array.Copy(d, p, o, w, lit); p += lit; w += lit;
                int src = w - off;
                for (int i = 0; i < n; i++) o[w++] = o[src + i];
            }
            return o;
        }

        // ---------------------------------------------------------------- EA-XAS v1 (SNR codec 4)
        static readonly int[] C0 = { 0, 240, 460, 392 }, C1 = { 0, 0, -208, -220 };

        static void XasFrame(byte[] fr, int at, short[] dst, int dstAt)
        {
            for (int g = 0; g < 4; g++)
            {
                int w0 = (short)(fr[at + 4 * g] | fr[at + 4 * g + 1] << 8), w1 = (short)(fr[at + 4 * g + 2] | fr[at + 4 * g + 3] << 8);
                int k = w0 & 0xF, shift = 20 - (w1 & 0xF), c0 = C0[k], c1 = C1[k];
                int s2 = w0 & ~0xF, s1 = w1 & ~0xF;
                int o = dstAt + g * 32;
                dst[o] = (short)s2; dst[o + 1] = (short)s1;
                int idx = 2;
                for (int row = 0; row < 15; row++)
                {
                    int b = fr[at + 16 + row * 4 + g];
                    for (int h = 0; h < 2; h++)
                    {
                        int nib = h == 0 ? b >> 4 : b & 0xF;
                        int lvl = ((nib & 8) != 0 ? nib - 16 : nib) << shift;
                        int v = (lvl + s1 * c0 + s2 * c1 + 0x80) >> 8;
                        v = Math.Max(-32768, Math.Min(32767, v));
                        dst[o + idx++] = (short)v;
                        s2 = s1; s1 = v;
                    }
                }
            }
        }

        /// SNR header (8 bytes) + SNS blocks -> mono samples (multi-channel clips are averaged)
        public static short[] Snr(byte[] data, out int rate)
        {
            uint h0 = BE(data, 0), h1 = BE(data, 4);
            int ch = (int)((h0 >> 18) & 0x3F) + 1;
            rate = (int)(h0 & 0x3FFFF);
            int total = (int)(h1 & 0x3FFFFFFF);
            var pay = new MemoryStream();
            int p = 8;
            while (p + 8 <= data.Length)
            {
                uint bh = BE(data, p);
                int size = (int)(bh & 0xFFFFFF);
                if (size < 8) break;
                pay.Write(data, p + 8, Math.Min(size, data.Length - p) - 8);
                p += size;
                if (bh >> 24 == 0x80) break;
            }
            var body = pay.ToArray();
            int frames = body.Length / (76 * ch);
            var mono = new short[Math.Min(total, frames * 128)];
            var tmp = new short[128];
            var acc = new int[128];
            for (int f = 0; f < frames; f++)
            {
                Array.Clear(acc, 0, 128);
                for (int c = 0; c < ch; c++)
                {
                    XasFrame(body, (f * ch + c) * 76, tmp, 0);
                    for (int i = 0; i < 128; i++) acc[i] += tmp[i];
                }
                for (int i = 0; i < 128 && f * 128 + i < mono.Length; i++) mono[f * 128 + i] = (short)Math.Round(acc[i] / (double)ch);
            }
            return mono;
        }

        // ---------------------------------------------------------------- EA-XA v2 (movie .snd)
        static readonly int[] E1 = { 0, 240, 460, 392 }, E2 = { 0, 0, -208, -220 };

        /// a window of a movie's dialogue: the centre channel of 5.1 (plus some of the front pair), or both of stereo
        public static short[] Movie(byte[] d, double start, double length, out int rate)
        {
            int nch = 1; rate = 48000;
            int p = 0;
            // SCHl header tags (PT): 0x82 channels, 0x84 sample rate
            int hsize = (int)BitConverter.ToUInt32(d, 4);
            int q = 8;
            while (q < hsize && d[q] != 0xFD) q++;
            q++;
            while (q + 1 < hsize && d[q] != 0xFF)
            {
                int t = d[q], n = d[q + 1], v = 0;
                for (int i = 0; i < n; i++) v = v << 8 | d[q + 2 + i];
                if (t == 0x82) nch = v; else if (t == 0x84) rate = v;
                q += 2 + n;
            }
            int from = (int)(start * rate), want = (int)(length * rate);
            var mix = new double[want];
            var h1 = new int[nch]; var h2 = new int[nch];
            int[] use = nch == 6 ? new[] { 0, 1, 2 } : Enumerable.Range(0, nch).ToArray();
            double[] gain = nch == 6 ? new[] { 0.35, 1.0, 0.35 } : Enumerable.Repeat(1.0 / nch, nch).ToArray();
            int pos = 0;
            p = 0;
            while (p + 8 <= d.Length && pos < from + want)
            {
                string tag = Encoding.ASCII.GetString(d, p, 4);
                int size = (int)BitConverter.ToUInt32(d, p + 4);
                if (size <= 0) break;
                if (tag == "SCDl")
                {
                    int ns = (int)BE(d, p + 8);
                    int baseOff = p + 0x0C + 4 * nch;
                    var offs = new int[nch + 1];
                    for (int c = 0; c < nch; c++) offs[c] = (int)BE(d, p + 0x0C + 4 * c);
                    offs[nch] = p + size - baseOff;
                    for (int u = 0; u < use.Length; u++)
                    {
                        int c = use[u];
                        int a = baseOff + offs[c], end = baseOff + offs[c + 1], n = 0;
                        while (n < ns && a < end)
                        {
                            int k = Math.Min(28, ns - n);
                            if (d[a] == 0xEE)
                            {
                                h1[c] = (short)(d[a + 1] << 8 | d[a + 2]); h2[c] = (short)(d[a + 3] << 8 | d[a + 4]);
                                for (int i = 0; i < k; i++) Put(mix, pos + n + i - from, (short)(d[a + 5 + 2 * i] << 8 | d[a + 6 + 2 * i]) * gain[u]);
                                a += 61;
                            }
                            else
                            {
                                int info = d[a], c1 = E1[info >> 4], c2 = E2[info >> 4], shift = (info & 0x0F) + 8;
                                for (int i = 0; i < k; i++)
                                {
                                    int b = d[a + 1 + i / 2];
                                    int nib = i % 2 == 0 ? b >> 4 : b & 0x0F;
                                    int s = ((nib << 28) - ((nib & 8) << 29)) >> shift;
                                    s = (s + c1 * h1[c] + c2 * h2[c]) >> 8;
                                    s = Math.Max(-32768, Math.Min(32767, s));
                                    h2[c] = h1[c]; h1[c] = s;
                                    Put(mix, pos + n + i - from, s * gain[u]);
                                }
                                a += 15;
                            }
                            n += 28;
                        }
                    }
                    pos += ns;
                }
                if (tag == "SCEl") break;
                p += size;
            }
            double peak = mix.Length == 0 ? 1 : Math.Max(1, mix.Max(x => Math.Abs(x)));
            double g = peak > 32000 ? 32000 / peak : 1;
            return mix.Select(x => (short)Math.Round(x * g)).ToArray();
        }

        static void Put(double[] mix, int i, double v) { if (i >= 0 && i < mix.Length) mix[i] += v; }

        // ---------------------------------------------------------------- one line -> WAV bytes
        public static byte[] Wav(VoiceLine l, string root)
        {
            var blob = ReadEntry(Path.Combine(root, l.Game, l.Big), l.Entry);
            int rate;
            short[] pcm;
            if (l.Kind == "m") pcm = Movie(blob, l.Start, l.Length, out rate);
            else
            {
                if (l.Kind == "s")
                {
                    var sns = IsRefPack(blob) ? RefPack(blob) : blob;
                    int n = 0, p = 0;
                    while (p + 8 <= sns.Length) { n += (int)BE(sns, p + 4); int sz = (int)(BE(sns, p) & 0xFFFFFF); if (sz < 8) break; p += sz; }
                    var full = new byte[8 + sns.Length];
                    uint w0 = (uint)(4 << 24 | (l.Channels - 1) << 18 | l.Rate);
                    full[0] = (byte)(w0 >> 24); full[1] = (byte)(w0 >> 16); full[2] = (byte)(w0 >> 8); full[3] = (byte)w0;
                    full[4] = (byte)(n >> 24); full[5] = (byte)(n >> 16); full[6] = (byte)(n >> 8); full[7] = (byte)n;
                    Array.Copy(sns, 0, full, 8, sns.Length);
                    blob = full;
                }
                else if (IsRefPack(blob)) blob = RefPack(blob);
                pcm = Snr(blob, out rate);
            }
            var ms = new MemoryStream();
            var w = new BinaryWriter(ms);
            w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + pcm.Length * 2); w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
            w.Write(16); w.Write((short)1); w.Write((short)1); w.Write(rate); w.Write(rate * 2); w.Write((short)2); w.Write((short)16);
            w.Write(Encoding.ASCII.GetBytes("data")); w.Write(pcm.Length * 2);
            foreach (var s in pcm) w.Write(s);
            return ms.ToArray();
        }

        /// 测试用：把索引里每隔 step 句解码成 <out>\<序号>.wav（对照 Python 解码器检查）
        public static int Dump(string root, string outDir, int step)
        {
            var lines = LoadIndex(root);
            Directory.CreateDirectory(outDir);
            int n = 0;
            for (int i = 0; i < lines.Count; i += step) { File.WriteAllBytes(Path.Combine(outDir, i + ".wav"), Wav(lines[i], root)); n++; }
            return n;
        }

        public static List<VoiceLine> LoadIndex(string root)
        {
            var path = Path.Combine(root, "listen_index.json");
            var js = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
            var d = (Dictionary<string, object>)js.DeserializeObject(File.ReadAllText(path, Encoding.UTF8));
            var lines = new List<VoiceLine>();
            foreach (object[] e in (object[])d["lines"])
                lines.Add(new VoiceLine {
                    Cat = (string)e[0], Group = (string)e[1], Zh = (string)e[2], En = (string)e[3], Game = (string)e[4],
                    Big = (string)e[5], Entry = (string)e[6], Kind = (string)e[7], Rate = Convert.ToInt32(e[8]),
                    Channels = Convert.ToInt32(e[9]), Start = Convert.ToDouble(e[10]), Length = Convert.ToDouble(e[11]) });
            return lines;
        }
    }

    class ListenWindow
    {
        const string Xaml = @"
<Window xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'
        xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'
        Title='试听全部配音' Width='1000' Height='680' Background='#15171B' FontFamily='Microsoft YaHei UI'
        WindowStartupLocation='CenterOwner' TextOptions.TextFormattingMode='Display'>
  <Window.Resources>
    <Style TargetType='ListBoxItem'>
      <Setter Property='Foreground' Value='#ECEEF1'/>
      <Setter Property='Padding' Value='0'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='ListBoxItem'>
            <Border x:Name='b' Background='Transparent' CornerRadius='6' Padding='{TemplateBinding Padding}'>
              <ContentPresenter/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='Background' Value='#22262D'/></Trigger>
              <Trigger Property='IsSelected' Value='True'><Setter TargetName='b' Property='Background' Value='#3A1C1F'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style TargetType='TreeViewItem'>
      <Setter Property='Foreground' Value='#C9CDD3'/>
      <Setter Property='Padding' Value='2,3'/>
      <Setter Property='FontSize' Value='13'/>
    </Style>
  </Window.Resources>
  <Grid Background='#15171B'>
  <Grid Margin='20'>
    <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='Auto'/><RowDefinition/><RowDefinition Height='Auto'/></Grid.RowDefinitions>
    <TextBlock Text='试听全部配音' FontSize='22' FontWeight='Bold' Foreground='#ECEEF1'/>
    <TextBlock Grid.Row='1' x:Name='Hint' FontSize='12.5' Foreground='#8A9099' Margin='0,4,0,12' TextWrapping='Wrap'
               Text='左边选单位、关卡或过场，右边点一句就播放。也可以直接在搜索框里输入台词、单位名或人名。'/>
    <Grid Grid.Row='2'>
      <Grid.ColumnDefinitions><ColumnDefinition Width='300'/><ColumnDefinition Width='16'/><ColumnDefinition/></Grid.ColumnDefinitions>
      <Border Background='#1C1F24' CornerRadius='8' Padding='6'>
        <TreeView x:Name='Tree' Background='Transparent' BorderThickness='0'/>
      </Border>
      <DockPanel Grid.Column='2'>
        <Border DockPanel.Dock='Top' Background='#1C1F24' CornerRadius='8' Padding='10,6' Margin='0,0,0,10'>
          <Grid>
            <TextBox x:Name='Q' Background='Transparent' BorderThickness='0' Foreground='#ECEEF1' CaretBrush='#ECEEF1' FontSize='14'/>
            <TextBlock x:Name='QHint' Text='搜索：台词、单位、人名，例如 谭雅 / 基洛夫 / 查丹科' Foreground='#5C626B' FontSize='14' IsHitTestVisible='False'/>
          </Grid>
        </Border>
        <TextBlock DockPanel.Dock='Top' x:Name='Title' FontSize='15' FontWeight='SemiBold' Foreground='#ECEEF1' Margin='2,0,0,8'/>
        <ListBox x:Name='List' Background='Transparent' BorderThickness='0' ScrollViewer.HorizontalScrollBarVisibility='Disabled'
                 VirtualizingStackPanel.IsVirtualizing='True' VirtualizingStackPanel.VirtualizationMode='Recycling'>
          <ListBox.ItemTemplate>
            <DataTemplate>
              <Grid Margin='8,7'>
                <Grid.ColumnDefinitions><ColumnDefinition Width='34'/><ColumnDefinition/></Grid.ColumnDefinitions>
                <Border Width='26' Height='26' CornerRadius='13' Background='#D7262E' VerticalAlignment='Top' HorizontalAlignment='Left'>
                  <TextBlock Text='&#x25B6;' Foreground='White' FontSize='11' HorizontalAlignment='Center' VerticalAlignment='Center' Margin='2,0,0,0'/>
                </Border>
                <StackPanel Grid.Column='1'>
                  <TextBlock Text='{Binding Shown}' FontSize='15' Foreground='#ECEEF1' TextWrapping='Wrap'/>
                  <TextBlock Text='{Binding Sub}' FontSize='12' Foreground='#8A9099' TextWrapping='Wrap'/>
                  <TextBlock Text='{Binding Where}' FontSize='11.5' Foreground='#6F7680'/>
                </StackPanel>
              </Grid>
            </DataTemplate>
          </ListBox.ItemTemplate>
        </ListBox>
      </DockPanel>
    </Grid>
    <TextBlock Grid.Row='3' x:Name='Status' FontSize='12.5' Foreground='#8A9099' Margin='0,10,0,0'/>
  </Grid>
  </Grid>
</Window>";

        Window win;
        List<VoiceLine> all;
        string root;
        System.Media.SoundPlayer player;
        int playId;
        public static string Snapshot;   // 测试：把窗口渲染成 PNG 后关闭

        T Find<T>(string n) where T : class { return win.FindName(n) as T; }
        static SolidColorBrush Brush(string hex) { return (SolidColorBrush)new BrushConverter().ConvertFromString(hex); }

        public static void Show(Window owner, string filesRoot)
        {
            List<VoiceLine> lines;
            try { lines = AudioLib.LoadIndex(filesRoot); }
            catch (Exception ex) { MessageBox.Show(owner, "没有找到试听索引（files\\listen_index.json）：" + ex.Message, "试听"); return; }
            new ListenWindow { all = lines, root = filesRoot }.Open(owner);
        }

        void Open(Window owner)
        {
            win = (Window)System.Windows.Markup.XamlReader.Parse(Xaml);
            win.Owner = owner;
            var tree = Find<TreeView>("Tree");
            foreach (var cat in all.Select(l => l.Cat).Distinct())
            {
                var lines = all.Where(l => l.Cat == cat).ToList();
                var node = new TreeViewItem { Header = cat + "（" + lines.Count + " 句）", FontSize = 14, FontWeight = FontWeights.SemiBold, Foreground = Brush("#ECEEF1") };
                // 过场和剧情的分组很多：再按“·”前的部分分一层（例如 盟军战役 第3关）
                var deep = cat == "过场视频" || cat == "剧情对白" || cat == "单位语音";
                if (deep)
                    foreach (var head in lines.Select(l => l.Group.Split('·')[0].Trim()).Distinct())
                    {
                        var sub = new TreeViewItem { Header = head, Foreground = Brush("#C9CDD3") };
                        foreach (var g in lines.Where(l => l.Group.Split('·')[0].Trim() == head).Select(l => l.Group).Distinct())
                            sub.Items.Add(Leaf(g, lines));
                        if (sub.Items.Count == 1) node.Items.Add(Leaf(lines.First(l => l.Group.Split('·')[0].Trim() == head).Group, lines));
                        else node.Items.Add(sub);
                    }
                else
                    foreach (var g in lines.Select(l => l.Group).Distinct()) node.Items.Add(Leaf(g, lines));
                if (tree.Items.Count == 0) node.IsExpanded = true;
                tree.Items.Add(node);
            }
            var list = Find<ListBox>("List");
            // 点一句就播放（再点同一句会重播）；键盘上下选中后按回车或空格播放
            list.PreviewMouseLeftButtonUp += (s, e) => win.Dispatcher.BeginInvoke(new Action(() => { var l = list.SelectedItem as VoiceLine; if (l != null) Play(l); }));
            list.KeyUp += (s, e) => { var l = list.SelectedItem as VoiceLine; if (l != null && (e.Key == Key.Enter || e.Key == Key.Space)) Play(l); };
            var q = Find<TextBox>("Q");
            q.TextChanged += (s, e) =>
            {
                Find<TextBlock>("QHint").Visibility = q.Text.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
                var t = q.Text.Trim();
                if (t.Length == 0) return;
                var hits = all.Where(l => l.Zh.Contains(t) || l.Group.Contains(t) || l.En.IndexOf(t, StringComparison.OrdinalIgnoreCase) >= 0).Take(500).ToList();
                ShowLines("搜索“" + t + "”：" + (hits.Count >= 500 ? "前 500 句" : hits.Count + " 句"), hits);
            };
            Find<TextBlock>("Status").Text = "共 " + all.Count + " 句。点一句播放，再点别的会换成那一句。";
            var first = all.First();
            ShowLines(first.Group, all.Where(l => l.Group == first.Group).ToList());
            win.Closed += (s, e) => { if (player != null) player.Stop(); };
            if (Snapshot != null)
            {
                win.ShowInTaskbar = false; win.WindowStartupLocation = WindowStartupLocation.Manual; win.Left = -3000;
                win.ContentRendered += (s, e) => win.Dispatcher.BeginInvoke(new Action(() =>
                {
                    var r = (FrameworkElement)win.Content;
                    var bmp = new System.Windows.Media.Imaging.RenderTargetBitmap((int)r.ActualWidth * 2, (int)r.ActualHeight * 2, 192, 192, PixelFormats.Pbgra32);
                    bmp.Render(r);
                    var enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
                    enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
                    using (var f = File.Create(Snapshot)) enc.Save(f);
                    win.Close();
                }), System.Windows.Threading.DispatcherPriority.ApplicationIdle);
            }
            win.ShowDialog();
        }

        TreeViewItem Leaf(string group, List<VoiceLine> lines)
        {
            var items = lines.Where(l => l.Group == group).ToList();
            var label = group.Contains("·") && (lines[0].Cat == "过场视频" || lines[0].Cat == "剧情对白" || lines[0].Cat == "单位语音") ? group.Substring(group.IndexOf('·') + 1).Trim() : group;
            if (label.Length == 0) label = group;
            var leaf = new TreeViewItem { Header = label + "  " + items.Count, Foreground = Brush("#C9CDD3") };
            leaf.Selected += (s, e) => { e.Handled = true; ShowLines(group, items); };
            return leaf;
        }

        void ShowLines(string title, List<VoiceLine> items)
        {
            Find<TextBlock>("Title").Text = title;
            var list = Find<ListBox>("List");
            list.ItemsSource = items;
            if (items.Count > 0) list.ScrollIntoView(items[0]);
        }

        void Play(VoiceLine l)
        {
            var id = ++playId;
            var status = Find<TextBlock>("Status");
            status.Text = "正在播放：" + l.Zh;
            Task.Run(() => AudioLib.Wav(l, root)).ContinueWith(t =>
            {
                if (id != playId) return;
                if (t.Exception != null) { status.Text = "这一句播放失败：" + t.Exception.InnerException.Message; return; }
                if (player != null) player.Stop();
                player = new System.Media.SoundPlayer(new MemoryStream(t.Result));
                player.Play();
            }, TaskScheduler.FromCurrentSynchronizationContext());
        }
    }
}
