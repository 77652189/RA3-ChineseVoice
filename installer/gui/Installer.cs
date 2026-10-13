// 红警3 / 起义时刻 中文配音 MOD 安装器（WPF，用 Windows 自带的 .NET Framework 4 csc 编译，C# 5）
// 逻辑与 installer/installer.ps1 相同：不改版本号，只在 SkuDef 里插入加载行（先原样备份），卸载时用备份恢复。
// 布局：<exe 所在目录>\files\package.json、files\<ra3|uprising>\CNVoice_*.big、files\<game>\core\CNVoice_core_<字母>.big
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Markup;
using System.Windows.Media;
using Microsoft.Win32;

namespace CNVoiceInstaller
{
    class Comp
    {
        public string Id, Name, Letter, Kind;
        public CheckBox Box;
        public TextBlock State;
    }

    class Game
    {
        public string Dir, Kind;
        public CheckBox Box;
        public TextBlock State;
        public string Label { get { return Kind == "uprising" ? "起义时刻" : "红色警戒3"; } }
    }

    class Mod
    {
        static readonly Encoding Latin1 = Encoding.GetEncoding(28591);   // SkuDef 是纯 ASCII，按字节原样读写
        public const string BackupExt = ".cnvoice-backup";
        const string MarkerRe = @"add-big\s+Data\\(CNVoice\w*|ChineseVoice)\.big";
        static readonly string[] LegacyBigs = { "CNVoiceMod.big", "ChineseVoice.big" };
        static readonly Regex SkuRe = new Regex(@"^(RA3EP1|RA3)_([A-Za-z_]+)_(\d+)\.(\d+)\.SkuDef$", RegexOptions.IgnoreCase);
        static readonly Regex AudioLine = new Regex(@"^[ \t]*add-big[ \t]+Data\\EnglishAudio\.big[ \t]*\r?$", RegexOptions.Multiline | RegexOptions.IgnoreCase);
        static readonly Regex LangLine = new Regex(@"^[ \t]*add-big[ \t]+Data\\(Lang-[A-Za-z]+\d*|English|ChineseT|ChineseS|German|French|Spanish|Italian|Korean|Polish|Russian|Japanese|Dutch|Swedish|Norwegian|Czech|Hungarian|Portuguese|Brazilian)\.big[ \t]*\r?$", RegexOptions.Multiline | RegexOptions.IgnoreCase);
        static readonly Regex FirstAddBig = new Regex(@"^[ \t]*add-big[ \t]", RegexOptions.Multiline | RegexOptions.IgnoreCase);
        static readonly Regex AddConfig = new Regex(@"^[ \t]*add-config[ \t]+(\S+)", RegexOptions.Multiline | RegexOptions.IgnoreCase);
        const string LocaleBig = "ChineseT.big";   // 非繁中语言用简体文字时，还要加载繁中包里的字体映射

        public string Root, Version, CoreBig, CompBig, Edition, Build;
        public const string Marker = "CNVoice_installed.json";   // Data\ 里记录装的是哪个版本
        public List<Comp> Comps = new List<Comp>();
        public Dictionary<string, object> Games;
        public Action<string> Log = delegate { };

        public Mod(string root)
        {
            Root = root;
            var pkg = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(
                File.ReadAllText(Path.Combine(root, "package.json"), Encoding.UTF8));
            Version = (string)pkg["version"];
            Edition = pkg.ContainsKey("edition") ? (string)pkg["edition"] : "完整版";
            Build = pkg.ContainsKey("build") ? (string)pkg["build"] : Version;
            UpdateUrl = pkg.ContainsKey("update_url") ? (string)pkg["update_url"] : "";
            if (pkg.ContainsKey("update_mirrors")) Mirrors = ((object[])pkg["update_mirrors"]).Cast<string>().ToList();
            CoreBig = (string)pkg["core"];
            CompBig = (string)pkg["component_big"];
            Games = (Dictionary<string, object>)pkg["games"];
            foreach (Dictionary<string, object> c in (object[])pkg["components"])
                Comps.Add(new Comp {
                    Id = (string)c["id"], Name = (string)c["name"], Kind = (string)c["kind"],
                    Letter = c.ContainsKey("letter") ? (string)c["letter"] : null });
        }

        public string BigOf(string id) { return CompBig.Replace("{}", id); }

        /// 这个安装包里有没有这个游戏的文件（原版版 / 起义时刻版只带一个游戏）
        public bool Covers(string kind) { return kind != null && Games.ContainsKey(kind) && Directory.Exists(Path.Combine(Root, kind)); }

        public static string PackFor(string kind) { return kind == "uprising" ? "起义时刻" : "原版"; }
        static string Read(string p) { return File.ReadAllText(p, Latin1); }
        static void Write(string p, string t) { File.WriteAllText(p, t, Latin1); }

        // ------------------------------------------------------------ 找游戏
        public static string KindOf(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return null;
            if (File.Exists(Path.Combine(dir, "RA3EP1.exe")) || Directory.GetFiles(dir, "RA3EP1_*.SkuDef").Length > 0) return "uprising";
            if (File.Exists(Path.Combine(dir, "RA3.exe")) || Directory.GetFiles(dir, "RA3_*.SkuDef").Length > 0) return "ra3";
            return null;
        }

        static void RegistryDirs(RegistryKey key, int depth, List<string> found)
        {
            if (key == null || depth < 0) return;
            foreach (var name in key.GetSubKeyNames())
            {
                try
                {
                    using (var sub = key.OpenSubKey(name))
                    {
                        if (sub == null) continue;
                        if (Regex.IsMatch(name, @"Red Alert 3|Red Alert\(tm\) 3", RegexOptions.IgnoreCase))
                            foreach (var v in new[] { "Install Dir", "InstallDir", "Install Location" })
                            {
                                var s = sub.GetValue(v) as string;
                                if (!string.IsNullOrEmpty(s)) found.Add(s);
                            }
                        RegistryDirs(sub, depth - 1, found);
                    }
                }
                catch { }
            }
        }

        public List<Game> FindGames(string exeDir)
        {
            var cands = new List<string>();
            foreach (var root in new[] { @"SOFTWARE\WOW6432Node\Electronic Arts", @"SOFTWARE\Electronic Arts", @"SOFTWARE\WOW6432Node\EA Games", @"SOFTWARE\EA Games" })
                try { using (var k = Registry.LocalMachine.OpenSubKey(root)) RegistryDirs(k, 2, cands); } catch { }
            try
            {
                string steam = null;
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam")) if (k != null) steam = k.GetValue("SteamPath") as string;
                if (!string.IsNullOrEmpty(steam))
                {
                    var libs = new List<string> { steam };
                    var vdf = Path.Combine(steam, @"steamapps\libraryfolders.vdf");
                    if (File.Exists(vdf))
                        foreach (Match m in Regex.Matches(File.ReadAllText(vdf), "\"path\"\\s+\"([^\"]+)\""))
                            libs.Add(m.Groups[1].Value.Replace(@"\\", @"\"));
                    foreach (var l in libs)
                        foreach (var n in new[] { "Command and Conquer Red Alert 3", "Command and Conquer Red Alert 3 Uprising" })
                            cands.Add(Path.Combine(l, "steamapps", "common", n));
                }
            }
            catch { }
            try { cands.Add(Path.GetDirectoryName(exeDir)); } catch { }   // 安装包解压在游戏目录里时
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var games = new List<Game>();
            foreach (var c in cands)
            {
                string full;
                try { full = Path.GetFullPath(c.Replace('/', '\\')).TrimEnd('\\'); } catch { continue; }
                if (!seen.Add(full)) continue;
                var kind = KindOf(full);
                if (kind != null) games.Add(new Game { Dir = full, Kind = kind });
            }
            return games;
        }

        public List<string> Installed(Game g)
        {
            return Comps.Where(c => File.Exists(Path.Combine(g.Dir, "Data", BigOf(c.Id)))).Select(c => c.Id).ToList();
        }

        public bool HasMarkers(Game g)
        {
            return Directory.GetFiles(g.Dir, "*.SkuDef").Any(f => Regex.IsMatch(Read(f), MarkerRe, RegexOptions.IgnoreCase));
        }

        // ------------------------------------------------------------ 卸载 / 安装
        public void Remove(Game g)
        {
            foreach (var f in Directory.GetFiles(g.Dir, "*.SkuDef"))
            {
                var text = Read(f);
                if (!Regex.IsMatch(text, MarkerRe, RegexOptions.IgnoreCase)) continue;
                var backup = f + BackupExt;
                if (File.Exists(backup))
                {
                    File.Copy(backup, f, true);       // 被本 MOD 插过行的原版配置：用安装时的备份原样恢复
                    File.Delete(backup);
                }
                else if (text.Contains("add-config") && text.Split('\n').Length <= 4)
                    File.Delete(f);                    // 旧版本 MOD 新建的“版本号 +1”配置
                else
                {
                    // 没有备份的原版配置：只去掉本 MOD 的行（紧跟文字包的繁中字体映射行也是本 MOD 加的）
                    text = Regex.Replace(text, @"(?m)^([ \t]*add-big\s+Data\\CNVoice_text\.big[ \t]*\r?\n)[ \t]*add-big\s+Data\\" + Regex.Escape(LocaleBig) + @"[ \t]*\r?\n", "$1");
                    Write(f, Regex.Replace(text, @"(?m)^[ \t]*" + MarkerRe + @"[ \t]*\r?\n", ""));
                }
            }
            var data = Path.Combine(g.Dir, "Data");
            var marker = Path.Combine(data, Marker);
            if (File.Exists(marker)) File.Delete(marker);
            var bigs = Directory.GetFiles(data, "CNVoice*.big").Select(Path.GetFileName).Concat(LegacyBigs).Distinct();
            foreach (var b in bigs)
            {
                var p = Path.Combine(data, b);
                if (File.Exists(p)) File.Delete(p);
            }
        }

        static void InsertLines(string path, int at, IEnumerable<string> lines)
        {
            var text = Read(path);
            var eol = text.Contains("\r\n") ? "\r\n" : "\n";
            var backup = path + BackupExt;
            if (!File.Exists(backup)) Write(backup, text);
            Write(path, text.Substring(0, at) + string.Concat(lines.Select(l => l + eol)) + text.Substring(at));
        }

        string Files(Game g) { return Path.Combine(Root, g.Kind); }

        void CopyComp(Game g, string id)
        {
            var src = Path.Combine(Files(g), BigOf(id));
            if (!File.Exists(src)) throw new Exception("安装包里缺少 " + g.Kind + "\\" + BigOf(id));
            Log("  复制 " + BigOf(id));
            File.Copy(src, Path.Combine(g.Dir, "Data", BigOf(id)), true);
        }

        void SetVoice(Game g, List<Comp> want)
        {
            // 带字母的组件改语音，需要和组合完全对应的长度表；过场视频这类整文件替换的没有字母
            var letters = string.Concat(Comps.Where(c => want.Contains(c) && !string.IsNullOrEmpty(c.Letter)).Select(c => c.Letter));
            var core = Path.Combine(Files(g), "core", "CNVoice_core_" + letters + ".big");
            if (letters.Length > 0 && !File.Exists(core)) throw new Exception("安装包里缺少 " + g.Kind + "\\core\\CNVoice_core_" + letters + ".big");
            foreach (var c in want) CopyComp(g, c.Id);
            if (letters.Length > 0) File.Copy(core, Path.Combine(g.Dir, "Data", CoreBig), true);
            var lines = want.Select(c => @"add-big Data\" + BigOf(c.Id)).ToList();
            if (letters.Length > 0) lines.Add(@"add-big Data\" + CoreBig);
            // 不新建配置、不改版本号：在每种语言最底层的配置里，紧挨着英文语音包那一行的前面插入
            int made = 0;
            foreach (var f in Directory.GetFiles(g.Dir, "*.SkuDef").Where(f => SkuRe.IsMatch(Path.GetFileName(f))))
            {
                var m = AudioLine.Match(Read(f));
                if (!m.Success) continue;
                InsertLines(f, m.Index, lines);
                Log("  已写入 " + Path.GetFileName(f) + "（原文件已备份）");
                made++;
            }
            if (made == 0) throw new Exception("没有找到使用英文语音的语言配置");
        }

        void SetText(Game g, List<Comp> want)
        {
            foreach (var c in want) CopyComp(g, c.Id);
            // 字符串表要压过官方语言包：插在加载语言包的那份配置最前面；新版本配置 add-config 引用旧版本，
            // 只改链条上最靠前、带语言包的那份，同一个包不重复加载
            var skus = Directory.GetFiles(g.Dir, "*.SkuDef").Where(f => SkuRe.IsMatch(Path.GetFileName(f))).ToList();
            var hasLang = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var next = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var f in skus)
            {
                var t = Read(f);
                var name = Path.GetFileName(f);
                if (LangLine.IsMatch(t)) hasLang.Add(name);
                var m = AddConfig.Match(t);
                if (m.Success) next[name] = m.Groups[1].Value;
            }
            var covered = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var n in hasLang)
            {
                var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                string cur;
                next.TryGetValue(n, out cur);
                while (cur != null && seen.Add(cur))
                {
                    covered.Add(cur);
                    string nx;
                    cur = next.TryGetValue(cur, out nx) ? nx : null;
                }
            }
            var haveLocale = File.Exists(Path.Combine(g.Dir, "Data", LocaleBig));
            int made = 0;
            foreach (var f in skus)
            {
                var name = Path.GetFileName(f);
                if (!hasLang.Contains(name) || covered.Contains(name)) continue;
                var lang = SkuRe.Match(name).Groups[2].Value;
                var lines = want.Select(c => @"add-big Data\" + BigOf(c.Id)).ToList();
                if (!lang.Equals("chinese_t", StringComparison.OrdinalIgnoreCase) && haveLocale) lines.Add(@"add-big Data\" + LocaleBig);
                InsertLines(f, FirstAddBig.Match(Read(f)).Index, lines);
                Log("  简体文字已写入 " + name + "（原文件已备份）");
                made++;
            }
            if (made == 0) throw new Exception("没有找到加载语言包的配置");
        }

        /// 让这个游戏里装着的组件正好等于 want（空 = 完全卸载，恢复原版）
        public void Apply(Game g, List<Comp> want)
        {
            Remove(g);
            if (want.Count == 0) return;
            try
            {
                var voice = want.Where(c => c.Kind != "text").ToList();
                var text = want.Where(c => c.Kind == "text").ToList();
                if (voice.Count > 0) SetVoice(g, voice);
                if (text.Count > 0) SetText(g, text);
                WriteMarker(g, Version, Build, Build, want.Select(c => c.Id));
                try { ReapplyCached(g); } catch (Exception ex) { Log("  （已下载的更新没能重新应用：" + ex.Message + "）"); }
            }
            catch
            {
                Remove(g);
                throw;
            }
        }

        public string AudioWarning(Game g)
        {
            var audio = Path.Combine(g.Dir, "Data", "EnglishAudio.big");
            if (!File.Exists(audio)) return "这个游戏没有英文语音包（EnglishAudio.big），语音部分不适用";
            object info;
            if (Games.TryGetValue(g.Kind, out info))
            {
                var d = (Dictionary<string, object>)info;
                object size;
                if (d.TryGetValue("EnglishAudio.big size", out size) && Convert.ToInt64(size) != new FileInfo(audio).Length)
                    return "你的 EnglishAudio.big 和制作 MOD 时用的版本不同，可能出现无声，可随时卸载";
            }
            return null;
        }

        // ------------------------------------------------------------ 故障诊断
        public class Check
        {
            public int Level;            // 0 正常 / 1 注意 / 2 有问题
            public string Title, Detail;
            public Check(int level, string title, string detail) { Level = level; Title = title; Detail = detail; }
        }

        static readonly string[] OfficialBig = { "maps", "core", "lang-", "english", "chinese", "german", "french", "spanish", "italian",
            "korean", "polish", "russian", "japanese", "dutch", "swedish", "norwegian", "czech", "hungarian", "portuguese", "brazilian",
            "apt", "terrain", "staticstream", "globalstream", "libraries", "shaders", "misc", "wbdata", "englishaudio", "englishmovieaudio" };

        /// 按 add-config 展开一份配置，得到实际加载的包（越靠前优先级越高）
        List<string> Chain(string dir, string sku)
        {
            var bigs = new List<string>();
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var cur = sku;
            while (cur != null && seen.Add(cur))
            {
                var p = Path.Combine(dir, cur);
                if (!File.Exists(p)) break;
                string next = null;
                foreach (var raw in Read(p).Split('\n'))
                {
                    var line = raw.Trim();
                    var m = Regex.Match(line, @"^add-big\s+(\S+)", RegexOptions.IgnoreCase);
                    if (m.Success) bigs.Add(Path.GetFileName(m.Groups[1].Value));
                    m = Regex.Match(line, @"^add-config\s+(\S+)", RegexOptions.IgnoreCase);
                    if (m.Success) next = m.Groups[1].Value;
                }
                cur = next;
            }
            return bigs;
        }

        static string Sha1(string path)
        {
            using (var s = File.OpenRead(path)) using (var h = System.Security.Cryptography.SHA1.Create())
                return BitConverter.ToString(h.ComputeHash(s)).Replace("-", "");
        }

        public List<Check> Diagnose(Game g)
        {
            var r = new List<Check>();
            var data = Path.Combine(g.Dir, "Data");
            r.Add(new Check(0, "找到游戏", g.Label + "：" + g.Dir));
            if (!Covers(g.Kind))
            {
                r.Add(new Check(2, "安装包版本不对", "这个安装包是「" + Edition + "」，不含" + g.Label + "的文件。请下载「" + PackFor(g.Kind) + "」版或「完整版」。"));
                return r;
            }
            // 游戏正在运行？
            var running = System.Diagnostics.Process.GetProcesses().Where(p =>
            {
                try { var n = p.ProcessName.ToLowerInvariant(); return n.StartsWith("ra3") || n.StartsWith("ra3ep1") || n.Contains(".game"); }
                catch { return false; }
            }).Select(p => p.ProcessName).Distinct().ToList();
            if (running.Count > 0) r.Add(new Check(1, "游戏正在运行", "安装或卸载前请先完全退出游戏（" + string.Join(", ", running) + "）。"));
            // 写入权限
            try
            {
                var t = Path.Combine(data, ".cnvoice_write_test");
                File.WriteAllText(t, "x"); File.Delete(t);
                r.Add(new Check(0, "有写入权限", "可以修改游戏文件夹。"));
            }
            catch { r.Add(new Check(2, "没有写入权限", "请右键安装器，选择“以管理员身份运行”。")); }
            // 英文语音包
            var audio = Path.Combine(data, "EnglishAudio.big");
            var warn = AudioWarning(g);
            if (!File.Exists(audio)) r.Add(new Check(2, "没有英文语音包", "这个游戏安装的不是英文语音（例如俄语、德语版本），语音部分无法使用，简体文字仍可使用。"));
            else if (warn != null) r.Add(new Check(1, "英文语音包和制作时不同", warn));
            else r.Add(new Check(0, "英文语音包正常", "EnglishAudio.big 与制作 MOD 时的版本一致。"));
            // 已安装的组件：文件完整？
            var have = Installed(g);
            if (have.Count == 0)
            {
                r.Add(new Check(1, "还没有安装本 MOD", "勾选要安装的内容，点“安装 / 更新”。"));
            }
            string installedBuild = null, installedVersion = null;
            try
            {
                var mk = Path.Combine(data, Marker);
                if (File.Exists(mk))
                {
                    var d = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(mk, Encoding.UTF8));
                    installedBuild = d.ContainsKey("build") ? (string)d["build"] : null;
                    installedVersion = d.ContainsKey("version") ? (string)d["version"] : null;
                }
            }
            catch { }
            bool otherVersion = have.Count > 0 && installedBuild != Build;
            if (otherVersion)
                r.Add(new Check(1, "装的是另一个版本", "游戏里是 " + (installedVersion != null ? "v" + installedVersion + "（" + installedBuild + "）" : "较早的版本")
                                    + "，这个安装包是 v" + Version + "（" + Build + "）。点“安装 / 更新”即可换成这个版本。"));
            else if (have.Count > 0)
                r.Add(new Check(0, "版本一致", "已安装 v" + Version + "（" + Build + "）。"));
            foreach (var id in have)
            {
                if (otherVersion) break;          // sizes are expected to differ between versions
                var c = Comps.First(x => x.Id == id);
                var src = Path.Combine(Root, g.Kind, BigOf(id));
                var dst = Path.Combine(data, BigOf(id));
                if (File.Exists(src) && new FileInfo(src).Length != new FileInfo(dst).Length)
                    r.Add(new Check(2, c.Name + "：文件不完整", BigOf(id) + " 和安装包里的大小不同，可能复制中断或文件损坏。请重新点“安装 / 更新”。"));
            }
            // 语音长度表和组件是否对应
            var letters = string.Concat(Comps.Where(c => have.Contains(c.Id) && !string.IsNullOrEmpty(c.Letter)).Select(c => c.Letter));
            var core = Path.Combine(data, CoreBig);
            if (letters.Length > 0)
            {
                var want = Path.Combine(Root, g.Kind, "core", "CNVoice_core_" + letters + ".big");
                if (!File.Exists(core)) r.Add(new Check(2, "缺少语音长度表", "会导致中文语音无声或报错。请重新点“安装 / 更新”。"));
                else if (!otherVersion && File.Exists(want) && Sha1(want) != Sha1(core))
                    r.Add(new Check(2, "语音长度表和已装内容不匹配", "可能出现无声、截断或报错。请重新点“安装 / 更新”。"));
                else if (otherVersion)
                    r.Add(new Check(1, "语音长度表来自另一个版本", "更新到这个版本后会一起换成对应的长度表。"));
                else r.Add(new Check(0, "语音长度表正确", "和已安装的语音组件对应。"));
            }
            // 配置是否真的加载了这些包（Steam“验证完整性”会把配置还原）
            var skus = Directory.GetFiles(g.Dir, "*.SkuDef").Select(Path.GetFileName).Where(n => SkuRe.IsMatch(n)).ToList();
            var langs = skus.GroupBy(n => SkuRe.Match(n).Groups[2].Value.ToLowerInvariant());
            foreach (var lang in langs)
            {
                var top = lang.OrderBy(n => int.Parse(SkuRe.Match(n).Groups[3].Value) * 1000 + int.Parse(SkuRe.Match(n).Groups[4].Value)).Last();
                var chain = Chain(g.Dir, top);
                var langName = lang.Key == "chinese_t" ? "繁体中文" : lang.Key == "english" ? "英文" : lang.Key;
                var missing = have.Where(id => !chain.Contains(BigOf(id), StringComparer.OrdinalIgnoreCase)).ToList();
                int audioAt = chain.FindIndex(b => b.Equals("EnglishAudio.big", StringComparison.OrdinalIgnoreCase));
                var late = have.Where(id => Comps.First(c => c.Id == id).Kind != "text" && audioAt >= 0
                                            && chain.FindIndex(b => b.Equals(BigOf(id), StringComparison.OrdinalIgnoreCase)) > audioAt).ToList();
                if (have.Count > 0 && missing.Count == have.Count)
                    r.Add(new Check(2, langName + "版没有加载本 MOD", "MOD 文件还在，但游戏配置被还原了（常见于 Steam“验证游戏文件完整性”之后）。请重新点“安装 / 更新”。"));
                else if (missing.Count > 0)
                    r.Add(new Check(2, langName + "版有内容没加载", "没有加载：" + string.Join("、", missing.Select(id => Comps.First(c => c.Id == id).Name)) + "。请重新点“安装 / 更新”。"));
                else if (late.Count > 0)
                    r.Add(new Check(2, langName + "版加载顺序不对", "中文语音排在英文语音之后，不会生效。请重新点“安装 / 更新”。"));
                else if (have.Count > 0)
                    r.Add(new Check(0, langName + "版已加载", "启动 " + top + " 时会读取本 MOD 的全部 " + have.Count + " 项内容。"));
                var others = chain.Where(b => !b.StartsWith("CNVoice", StringComparison.OrdinalIgnoreCase)
                                              && !OfficialBig.Any(o => b.ToLowerInvariant().StartsWith(o))).Distinct().ToList();
                if (others.Count > 0)
                    r.Add(new Check(1, langName + "版还加载了其它包", string.Join("、", others) + "。如果是其它 MOD，可能和本 MOD 冲突。"));
            }
            // 启动方式
            var opts = SteamLaunchOptions(g.Kind == "uprising" ? "24800" : "17480");
            if (opts.Any(o => o.IndexOf("-modconfig", StringComparison.OrdinalIgnoreCase) >= 0 || o.IndexOf("-mod ", StringComparison.OrdinalIgnoreCase) >= 0))
                r.Add(new Check(2, "Steam 启动参数里有 -modconfig", "用其它 MOD 启动时不会加载本 MOD。请在 Steam → 属性 → 启动选项里删掉它。"));
            else if (opts.Count > 0)
                r.Add(new Check(0, "Steam 启动参数", string.Join(" / ", opts) + "（不影响本 MOD）"));
            // 高帧率补丁 / 其它 d3d9.dll
            bool fps = File.Exists(Path.Combine(data, "CnCFpsUnlocker.dll"));
            foreach (var d in new[] { Path.Combine(data, "d3d9.dll"), Path.Combine(g.Dir, "d3d9.dll") })
                if (File.Exists(d) && !fps)
                    r.Add(new Check(1, "发现其它 d3d9.dll", d + "。可能是 DXVK、ReShade 等工具，和高帧率补丁不能同时使用。"));
            if (fps) r.Add(new Check(0, "高帧率补丁已安装", "SAGE-Unlocked（帧率在 Data\\SAGEUnlocked.ini 里设置）。"));
            return r;
        }

        static List<string> SteamLaunchOptions(string app)
        {
            var found = new List<string>();
            try
            {
                string steam = null;
                using (var k = Registry.CurrentUser.OpenSubKey(@"Software\Valve\Steam")) if (k != null) steam = k.GetValue("SteamPath") as string;
                if (string.IsNullOrEmpty(steam)) return found;
                var ud = Path.Combine(steam, "userdata");
                if (!Directory.Exists(ud)) return found;
                foreach (var u in Directory.GetDirectories(ud))
                {
                    var cfg = Path.Combine(u, "config", "localconfig.vdf");
                    if (!File.Exists(cfg)) continue;
                    var t = File.ReadAllText(cfg);
                    var m = Regex.Match(t, "\"" + app + "\"\\s*\\{(.*?)\\n\\t\\t\\t\\t\\}", RegexOptions.Singleline);
                    if (!m.Success) continue;
                    var lo = Regex.Match(m.Groups[1].Value, "\"LaunchOptions\"\\s*\"([^\"]*)\"");
                    if (lo.Success && lo.Groups[1].Value.Trim().Length > 0) found.Add(lo.Groups[1].Value.Trim());
                }
            }
            catch { }
            return found.Distinct().ToList();
        }

        public string Report(List<Game> games)
        {
            var sb = new StringBuilder();
            sb.AppendLine("红警3中文配音 MOD 诊断报告 v" + Version + "（" + Edition + "）  " + DateTime.Now.ToString("yyyy-MM-dd HH:mm"));
            sb.AppendLine("系统：" + Environment.OSVersion.VersionString + (Environment.Is64BitOperatingSystem ? " 64 位" : ""));
            foreach (var g in games)
            {
                sb.AppendLine();
                foreach (var c in Diagnose(g))
                    sb.AppendLine((c.Level == 0 ? "[正常] " : c.Level == 1 ? "[注意] " : "[问题] ") + c.Title + " —— " + c.Detail);
            }
            return sb.ToString();
        }

        // ------------------------------------------------------------ 在线更新
        // 托管目录：<UpdateUrl 所在目录>/manifest.json + 同目录下扁平命名的 <game>_CNVoice_patch_<组件>.big、<game>_CNVoice_core_<字母>.big（GitHub Release 附件）
        // manifest.json = { "patches": [ ra3cv.py patch 生成的 patch.json, ... ] }。补丁对它的 base（正式版 build）是累积的。
        public string UpdateUrl;
        public List<string> Mirrors = new List<string>();   // URL 前缀：直连失败后依次尝试（如 GitHub 下载加速）

        public Dictionary<string, object> ReadMarker(Game g)
        {
            try
            {
                var mk = Path.Combine(g.Dir, "Data", Marker);
                if (File.Exists(mk)) return (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(File.ReadAllText(mk, Encoding.UTF8));
            }
            catch { }
            return null;
        }

        void WriteMarker(Game g, string version, string build, string bas, IEnumerable<string> comps)
        {
            File.WriteAllText(Path.Combine(g.Dir, "Data", Marker), new JavaScriptSerializer().Serialize(new Dictionary<string, object> {
                { "version", version }, { "build", build }, { "base", bas }, { "edition", Edition }, { "components", comps.ToArray() } }), new UTF8Encoding(false));
        }

        public static object[] Patches(string manifestJson)
        {
            var m = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(manifestJson);
            return m.ContainsKey("patches") ? (object[])m["patches"] : new object[0];
        }

        IEnumerable<string> Candidates(string url)
        {
            yield return url;
            foreach (var m in Mirrors) yield return m + url;
        }

        /// 读取托管的版本清单（直连不通就走备用地址），顺便更新备用地址列表
        public object[] LoadManifest()
        {
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            Exception last = null;
            foreach (var u in Candidates(UpdateUrl).ToList())
            {
                try
                {
                    var json = new System.Net.WebClient { Encoding = Encoding.UTF8 }.DownloadString(u);
                    var m = (Dictionary<string, object>)new JavaScriptSerializer().DeserializeObject(json);
                    if (m.ContainsKey("mirrors")) Mirrors = ((object[])m["mirrors"]).Cast<string>().ToList();
                    return Patches(json);
                }
                catch (Exception e) { last = e; }
            }
            throw last ?? new Exception("没有可用的更新地址");
        }

        public string BaseUrl { get { return UpdateUrl.Substring(0, UpdateUrl.LastIndexOf('/') + 1); } }

        /// 去掉已装的旧补丁（文件和配置里的行），新补丁总是在干净的正式版上整套重装
        public void RemovePatches(Game g)
        {
            var data = Path.Combine(g.Dir, "Data");
            foreach (var f in Directory.GetFiles(data, "CNVoice_patch_*.big")) File.Delete(f);
            foreach (var sku in Directory.GetFiles(g.Dir, "*.SkuDef"))
            {
                var t = Read(sku);
                var n = Regex.Replace(t, @"(?m)^[ \t]*add-big\s+Data\\CNVoice_patch_\w+\.big[ \t]*\r?\n", "");
                if (n != t) Write(sku, n);
            }
        }

        /// 这个游戏能用的最新补丁（base 要和装的正式版一致，build 要比装的新），没有就 null
        public Dictionary<string, object> PatchFor(Game g, object[] patches)
        {
            var mk = ReadMarker(g);
            if (mk == null || Installed(g).Count == 0) return null;
            var bas = mk.ContainsKey("base") ? (string)mk["base"] : (string)mk["build"];
            var cur = (string)mk["build"];
            Dictionary<string, object> best = null;
            foreach (Dictionary<string, object> p in patches)
            {
                if ((string)p["base"] != bas || string.CompareOrdinal((string)p["build"], cur) <= 0) continue;
                var games = (Dictionary<string, object>)p["games"];
                if (!games.ContainsKey(g.Kind)) continue;
                if (best == null || string.CompareOrdinal((string)p["build"], (string)best["build"]) > 0) best = p;
            }
            return best;
        }

        /// 这次更新要下载的文件：[(相对路径, 大小, sha256)]，只含玩家装了的组件 + 对应的语音长度表
        public List<Tuple<string, long, string>> PatchFiles(Game g, Dictionary<string, object> patch)
        {
            var have = Installed(g);
            var game = (Dictionary<string, object>)((Dictionary<string, object>)patch["games"])[g.Kind];
            var list = new List<Tuple<string, long, string>>();
            foreach (Dictionary<string, object> f in (object[])game["files"])
                if (have.Contains((string)f["component"]))
                    list.Add(Tuple.Create((string)patch["build"] + "/" + (string)f["path"], Convert.ToInt64(f["size"]), (string)f["sha256"]));
            var letters = string.Concat(Comps.Where(c => have.Contains(c.Id) && !string.IsNullOrEmpty(c.Letter)).Select(c => c.Letter));
            var cores = (Dictionary<string, object>)game["core"];
            if (letters.Length > 0 && cores.ContainsKey(letters))
            {
                var c = (Dictionary<string, object>)cores[letters];
                list.Add(Tuple.Create((string)patch["build"] + "/" + (string)c["path"], Convert.ToInt64(c["size"]), (string)c["sha256"]));
            }
            return list;
        }

        public string Cache { get { return Path.Combine(Root, "updates"); } }

        static string Sha256(string path)
        {
            using (var s = File.OpenRead(path)) using (var h = System.Security.Cryptography.SHA256.Create())
                return BitConverter.ToString(h.ComputeHash(s)).Replace("-", "").ToLowerInvariant();
        }

        /// 下载到 files\updates\（已下载且校验通过的跳过），返回本地路径
        public string Fetch(string baseUrl, Tuple<string, long, string> f, Action<long> progress)
        {
            var local = Path.Combine(Cache, f.Item1.Replace('/', '\\'));
            if (File.Exists(local) && Sha256(local) == f.Item3) { progress(f.Item2); return local; }
            Directory.CreateDirectory(Path.GetDirectoryName(local));
            var tmp = local + ".part";
            System.Net.ServicePointManager.SecurityProtocol |= System.Net.SecurityProtocolType.Tls12;
            var asset = f.Item1.Substring(f.Item1.IndexOf('/') + 1);   // 缓存按 <build>/ 分目录，托管处是扁平文件名
            Exception last = null;
            bool ok = false;
            foreach (var url in Candidates(baseUrl + asset).ToList())
            {
                long got = 0;
                try
                {
                    var req = (System.Net.HttpWebRequest)System.Net.WebRequest.Create(url);
                    req.UserAgent = "RA3-CNVoice-Installer/" + Version;
                    using (var resp = req.GetResponse()) using (var src = resp.GetResponseStream()) using (var dst = File.Create(tmp))
                    {
                        var buf = new byte[1 << 16];
                        int n;
                        while ((n = src.Read(buf, 0, buf.Length)) > 0) { dst.Write(buf, 0, n); got += n; progress(n); }
                    }
                    ok = true;
                    break;
                }
                catch (Exception e) { last = e; progress(-got); }
            }
            if (!ok) throw new Exception("下载失败：" + asset + "（" + (last == null ? "" : last.Message) + "）");
            if (Sha256(tmp) != f.Item3) { File.Delete(tmp); throw new Exception("下载的文件校验失败：" + f.Item1 + "，请稍后重试。"); }
            if (File.Exists(local)) File.Delete(local);
            File.Move(tmp, local);
            return local;
        }

        /// 把已下载的补丁装进游戏：补丁包放在各自组件的正前方，语音长度表换成补丁里的
        public void ApplyPatch(Game g, Dictionary<string, object> patch)
        {
            var data = Path.Combine(g.Dir, "Data");
            var have = Installed(g);
            var game = (Dictionary<string, object>)((Dictionary<string, object>)patch["games"])[g.Kind];
            var build = (string)patch["build"];
            RemovePatches(g);
            foreach (Dictionary<string, object> f in (object[])game["files"])
            {
                var comp = (string)f["component"];
                if (!have.Contains(comp)) continue;
                var name = (string)f["name"];
                File.Copy(Path.Combine(Cache, build, ((string)f["path"]).Replace('/', '\\')), Path.Combine(data, name), true);
                var compLine = new Regex(@"^[ \t]*add-big[ \t]+Data\\" + Regex.Escape(BigOf(comp)) + @"[ \t]*\r?$", RegexOptions.Multiline | RegexOptions.IgnoreCase);
                foreach (var sku in Directory.GetFiles(g.Dir, "*.SkuDef"))
                {
                    var text = Read(sku);
                    var m = compLine.Match(text);
                    if (!m.Success || text.IndexOf(@"add-big Data\" + name, StringComparison.OrdinalIgnoreCase) >= 0) continue;
                    InsertLines(sku, m.Index, new[] { @"add-big Data\" + name });
                }
                Log("  已更新 " + Comps.First(c => c.Id == comp).Name);
            }
            var letters = string.Concat(Comps.Where(c => have.Contains(c.Id) && !string.IsNullOrEmpty(c.Letter)).Select(c => c.Letter));
            var cores = (Dictionary<string, object>)game["core"];
            if (letters.Length > 0 && cores.ContainsKey(letters))
                File.Copy(Path.Combine(Cache, build, ((string)((Dictionary<string, object>)cores[letters])["path"]).Replace('/', '\\')),
                          Path.Combine(data, CoreBig), true);
            var mk = ReadMarker(g);
            var bas = mk != null && mk.ContainsKey("base") ? (string)mk["base"] : Build;
            WriteMarker(g, (string)patch["version"], build, bas, have);
        }

        /// 增减组件后，把本地已下载过的最新补丁重新叠上去（不用再下载）；缺文件就跳过，等下次“检查更新”
        public void ReapplyCached(Game g)
        {
            if (!Directory.Exists(Cache)) return;
            var patches = Directory.GetFiles(Cache, "patch.json", SearchOption.AllDirectories)
                .Select(p => { try { return new JavaScriptSerializer().DeserializeObject(File.ReadAllText(p, Encoding.UTF8)); } catch { return null; } })
                .Where(p => p != null).ToArray();
            var patch = PatchFor(g, patches);
            if (patch == null) return;
            foreach (var f in PatchFiles(g, patch))
            {
                var local = Path.Combine(Cache, f.Item1.Replace('/', '\\'));
                if (!File.Exists(local) || Sha256(local) != f.Item3) return;
            }
            ApplyPatch(g, patch);
        }

        public void SavePatchInfo(Dictionary<string, object> patch)
        {
            var dir = Path.Combine(Cache, (string)patch["build"]);
            Directory.CreateDirectory(dir);
            File.WriteAllText(Path.Combine(dir, "patch.json"), new JavaScriptSerializer().Serialize(patch), new UTF8Encoding(false));
        }

        public int Lines(Game g, string id)
        {
            object info, comps, n;
            if (Games.TryGetValue(g.Kind, out info) && ((Dictionary<string, object>)info).TryGetValue("components", out comps)
                && ((Dictionary<string, object>)comps).TryGetValue(id, out n)) return Convert.ToInt32(n);
            return 0;
        }
    }

    class App
    {
        static readonly Dictionary<string, string[]> Info = new Dictionary<string, string[]> {
            { "allied",    new[] { "盟军单位语音",     "选中、移动、攻击时的语音" } },
            { "soviet",    new[] { "苏联单位语音",     "动员兵、天启坦克、基洛夫……" } },
            { "empire",    new[] { "帝国单位语音",     "帝国武士、海啸坦克、鬼王……" } },
            { "eva",       new[] { "战场播报",         "三个阵营的 EVA 播报员" } },
            { "commander", new[] { "指挥官语音",       "友军指挥官、士兵闲聊" } },
            { "mission",   new[] { "剧情对白",         "任务对话、单位介绍、教学关" } },
            { "movie",     new[] { "过场视频配音",     "过场动画、简报、视频通话" } },
            { "text",      new[] { "简体中文文字",     "界面、说明、字幕改为简体" } },
        };

        const string Xaml = @"
<Window xmlns='http://schemas.microsoft.com/winfx/2006/xaml/presentation'
        xmlns:x='http://schemas.microsoft.com/winfx/2006/xaml'
        Title='红色警戒3 中文配音' Width='900' Height='620' WindowStyle='None' AllowsTransparency='True'
        Background='Transparent' ResizeMode='NoResize' WindowStartupLocation='CenterScreen'
        FontFamily='Microsoft YaHei UI' TextOptions.TextFormattingMode='Display'>
  <Window.Resources>
    <SolidColorBrush x:Key='Red' Color='#D7262E'/>
    <SolidColorBrush x:Key='Fg' Color='#ECEEF1'/>
    <SolidColorBrush x:Key='Dim' Color='#8A9099'/>
    <Style TargetType='CheckBox'>
      <Setter Property='Foreground' Value='{StaticResource Fg}'/>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='CheckBox'>
            <Grid Background='Transparent'>
              <Grid.ColumnDefinitions><ColumnDefinition Width='Auto'/><ColumnDefinition/></Grid.ColumnDefinitions>
              <Border x:Name='box' Width='20' Height='20' CornerRadius='4' BorderThickness='1.5' BorderBrush='#4A505A' Background='#1C1F24' VerticalAlignment='Top' Margin='0,2,12,0'>
                <Path x:Name='tick' Data='M4,10 L8.5,14 L16,5.5' Stroke='White' StrokeThickness='2.2' StrokeStartLineCap='Round' StrokeEndLineCap='Round' Visibility='Collapsed'/>
              </Border>
              <ContentPresenter Grid.Column='1'/>
            </Grid>
            <ControlTemplate.Triggers>
              <Trigger Property='IsChecked' Value='True'>
                <Setter TargetName='box' Property='Background' Value='#D7262E'/>
                <Setter TargetName='box' Property='BorderBrush' Value='#D7262E'/>
                <Setter TargetName='tick' Property='Visibility' Value='Visible'/>
              </Trigger>
              <Trigger Property='IsMouseOver' Value='True'>
                <Setter TargetName='box' Property='BorderBrush' Value='#E8484F'/>
              </Trigger>
              <Trigger Property='IsEnabled' Value='False'>
                <Setter Property='Opacity' Value='0.45'/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <Style x:Key='Btn' TargetType='Button'>
      <Setter Property='Foreground' Value='{StaticResource Fg}'/>
      <Setter Property='Background' Value='#262A31'/>
      <Setter Property='FontSize' Value='14'/>
      <Setter Property='Height' Value='40'/>
      <Setter Property='Padding' Value='22,0'/>
      <Setter Property='Cursor' Value='Hand'/>
      <Setter Property='Template'>
        <Setter.Value>
          <ControlTemplate TargetType='Button'>
            <Border x:Name='b' CornerRadius='6' Background='{TemplateBinding Background}' Padding='{TemplateBinding Padding}'>
              <ContentPresenter HorizontalAlignment='Center' VerticalAlignment='Center'/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property='IsMouseOver' Value='True'><Setter TargetName='b' Property='Opacity' Value='0.85'/></Trigger>
              <Trigger Property='IsPressed' Value='True'><Setter TargetName='b' Property='Opacity' Value='0.7'/></Trigger>
              <Trigger Property='IsEnabled' Value='False'><Setter TargetName='b' Property='Opacity' Value='0.4'/></Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
  </Window.Resources>
  <Border CornerRadius='12' BorderBrush='#2C3038' BorderThickness='1'>
    <Border.Background>
      <LinearGradientBrush StartPoint='0,0' EndPoint='1,1'>
        <GradientStop Color='#1A1D22' Offset='0'/>
        <GradientStop Color='#0F1114' Offset='1'/>
      </LinearGradientBrush>
    </Border.Background>
    <Grid>
      <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition/><RowDefinition Height='Auto'/></Grid.RowDefinitions>
      <!-- 顶栏 -->
      <Grid x:Name='Header' Background='Transparent' Margin='28,22,18,0'>
        <StackPanel Orientation='Horizontal'>
          <Border Width='6' Height='46' CornerRadius='3' Background='{StaticResource Red}' Margin='0,0,16,0'/>
          <StackPanel>
            <TextBlock Text='红色警戒3 · 中文配音' FontSize='24' FontWeight='Bold' Foreground='{StaticResource Fg}'/>
            <TextBlock x:Name='Sub' FontSize='12.5' Foreground='{StaticResource Dim}' Margin='1,4,0,0'/>
          </StackPanel>
        </StackPanel>
        <StackPanel Orientation='Horizontal' HorizontalAlignment='Right' VerticalAlignment='Top' Margin='0,7,52,0'>
          <TextBlock x:Name='Upd' Text='检查更新' FontSize='13' Foreground='#C9CDD3' Cursor='Hand' Margin='0,0,22,0'/>
          <TextBlock x:Name='Diag' Text='故障诊断' FontSize='13' Foreground='#C9CDD3' Cursor='Hand'/>
        </StackPanel>
        <Button x:Name='Close' Content='✕' HorizontalAlignment='Right' VerticalAlignment='Top' Width='36' Height='32' Padding='0'
                Style='{StaticResource Btn}' Background='Transparent' FontSize='14'/>
      </Grid>
      <!-- 主体 -->
      <Grid Grid.Row='1' Margin='28,22,28,0'>
        <Grid.ColumnDefinitions><ColumnDefinition Width='300'/><ColumnDefinition Width='24'/><ColumnDefinition/></Grid.ColumnDefinitions>
        <DockPanel>
          <TextBlock DockPanel.Dock='Top' Text='游戏' FontSize='13' Foreground='{StaticResource Dim}' Margin='2,0,0,10'/>
          <StackPanel DockPanel.Dock='Bottom'>
            <TextBlock x:Name='Pick' Text='＋ 手动选择游戏目录' FontSize='13' Foreground='#C9CDD3' Cursor='Hand' Margin='4,4,0,14'/>
            <Border CornerRadius='8' Background='#16181C' BorderBrush='#24272D' BorderThickness='1' Padding='14,12'>
              <TextBlock TextWrapping='Wrap' FontSize='12' LineHeight='19' Foreground='#7D838C'>装好后从 Steam / EA App 正常启动即可。不改版本号，不影响联机选 1.12 / 1.13。随时可以回来增减内容或全部卸载，原文件都有备份。</TextBlock>
            </Border>
          </StackPanel>
          <ScrollViewer VerticalScrollBarVisibility='Auto'><StackPanel x:Name='GameList'/></ScrollViewer>
        </DockPanel>
        <DockPanel Grid.Column='2'>
          <Grid DockPanel.Dock='Top' Margin='2,0,0,10'>
            <TextBlock Text='要安装的内容' FontSize='13' Foreground='{StaticResource Dim}'/>
            <TextBlock x:Name='All' Text='全选' HorizontalAlignment='Right' FontSize='13' Foreground='#C9CDD3' Cursor='Hand'/>
          </Grid>
          <UniformGrid x:Name='CompList' Columns='2' VerticalAlignment='Top'/>
        </DockPanel>
      </Grid>
      <!-- 底栏 -->
      <Grid Grid.Row='2' Margin='28,16,28,24'>
        <Grid.RowDefinitions><RowDefinition Height='Auto'/><RowDefinition Height='Auto'/></Grid.RowDefinitions>
        <ProgressBar x:Name='Bar' Height='3' Minimum='0' Maximum='1' Foreground='{StaticResource Red}' Background='#22262C' BorderThickness='0' Margin='0,0,0,14'/>
        <Grid Grid.Row='1'>
          <TextBlock x:Name='Status' VerticalAlignment='Center' FontSize='13' Foreground='{StaticResource Dim}' TextTrimming='CharacterEllipsis' Margin='0,0,300,0'/>
          <StackPanel Orientation='Horizontal' HorizontalAlignment='Right'>
            <Button x:Name='Uninstall' Content='全部卸载' Style='{StaticResource Btn}' Margin='0,0,12,0'/>
            <Button x:Name='Install' Content='安装 / 更新' Style='{StaticResource Btn}' Background='{StaticResource Red}' FontWeight='Bold'/>
          </StackPanel>
        </Grid>
      </Grid>
    </Grid>
  </Border>
</Window>";

        Window win;
        Mod mod;
        List<Game> games = new List<Game>();
        string exeDir;

        T Find<T>(string name) where T : class { return win.FindName(name) as T; }

        [STAThread]
        static int Main(string[] args)
        {
            // 测试用命令行（不显示界面）：--dirs "<目录1>|<目录2>" --components all|none|a,b,c
            int di = Array.IndexOf(args, "--dirs");
            if (di >= 0 && Array.IndexOf(args, "--diagnose") >= 0)
            {
                var m = new Mod(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "files"));
                var gs = args[di + 1].Split('|').Select(d => new Game { Dir = d.TrimEnd('\\'), Kind = Mod.KindOf(d) }).ToList();
                var bytes = Encoding.UTF8.GetBytes(m.Report(gs));   // winexe: no console to set an encoding on
                using (var o = Console.OpenStandardOutput()) o.Write(bytes, 0, bytes.Length);
                return 0;
            }
            if (di >= 0 && Array.IndexOf(args, "--update") >= 0)
            {
                var m = new Mod(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "files"));
                m.Log = Console.WriteLine;
                var patches = m.LoadManifest();
                var baseUrl = m.BaseUrl;
                foreach (var d in args[di + 1].Split('|'))
                {
                    var g = new Game { Dir = d.TrimEnd('\\'), Kind = Mod.KindOf(d) };
                    var p = m.PatchFor(g, patches);
                    if (p == null) { Console.WriteLine(g.Kind + ": up to date"); continue; }
                    m.SavePatchInfo(p);
                    foreach (var f in m.PatchFiles(g, p)) m.Fetch(baseUrl, f, n => { });
                    m.ApplyPatch(g, p);
                    Console.WriteLine(g.Kind + ": updated to " + p["version"] + " (" + p["build"] + ")");
                }
                return 0;
            }
            if (di >= 0) return Cli(args[di + 1], args[Array.IndexOf(args, "--components") + 1]);
            var app = new Application();
            var a = new App();
            int si = Array.IndexOf(args, "--snapshot");   // 把界面渲染成 PNG 后退出（检查外观用）
            if (si >= 0) a.snapshot = args[si + 1];
            app.DispatcherUnhandledException += (s, e) =>
            {
                MessageBox.Show(e.Exception.Message, "出错了", MessageBoxButton.OK, MessageBoxImage.Error);
                e.Handled = true;
            };
            a.Start(app);
            return 0;
        }

        string snapshot;

        static int Cli(string dirs, string comps)
        {
            var mod = new Mod(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "files"));
            mod.Log = Console.WriteLine;
            var want = comps == "all" ? mod.Comps.ToList()
                     : comps == "none" ? new List<Comp>()
                     : mod.Comps.Where(c => comps.Split(',').Contains(c.Id)).ToList();
            int bad = 0;
            foreach (var d in dirs.Split('|'))
            {
                var g = new Game { Dir = d.TrimEnd('\\'), Kind = Mod.KindOf(d) };
                if (!mod.Covers(g.Kind)) { Console.WriteLine(g.Kind + ": not in this package (" + mod.Edition + ")"); continue; }
                try { mod.Apply(g, want); Console.WriteLine(g.Kind + ": " + string.Join(",", mod.Installed(g))); }
                catch (Exception e) { Console.WriteLine(g.Kind + " ERROR " + e.Message); bad++; }
            }
            return bad;
        }

        void SaveSnapshot()
        {
            var root = (FrameworkElement)win.Content;
            var bmp = new System.Windows.Media.Imaging.RenderTargetBitmap((int)root.ActualWidth * 2, (int)root.ActualHeight * 2, 192, 192, PixelFormats.Pbgra32);
            bmp.Render(root);
            var enc = new System.Windows.Media.Imaging.PngBitmapEncoder();
            enc.Frames.Add(System.Windows.Media.Imaging.BitmapFrame.Create(bmp));
            using (var f = File.Create(snapshot)) enc.Save(f);
            win.Close();
        }

        void Start(Application app)
        {
            exeDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
            var files = Path.Combine(exeDir, "files");
            if (!File.Exists(Path.Combine(files, "package.json")))
            {
                MessageBox.Show("没有找到 files 文件夹。\n请先把整个压缩包解压，再运行解压出来的安装程序（不要在压缩包里直接双击）。",
                    "红色警戒3 中文配音", MessageBoxButton.OK, MessageBoxImage.Warning);
                return;
            }
            mod = new Mod(files);
            win = (Window)XamlReader.Parse(Xaml);
            Find<TextBlock>("Sub").Text = "AI 普通话配音 · 简体中文文字 · v" + mod.Version + " · "
                + (mod.Edition == "完整版" ? "完整版（原版 + 起义时刻）" : mod.Edition + "专用") + " · 社区非盈利作品";
            Find<Grid>("Header").MouseLeftButtonDown += (s, e) => { if (e.ButtonState == MouseButtonState.Pressed) win.DragMove(); };
            Find<Button>("Close").Click += (s, e) => win.Close();
            Find<TextBlock>("Diag").MouseLeftButtonUp += (s, e) => ShowDiagnosis();
            if (string.IsNullOrEmpty(mod.UpdateUrl)) Find<TextBlock>("Upd").Visibility = Visibility.Collapsed;
            Find<TextBlock>("Upd").MouseLeftButtonUp += (s, e) => CheckUpdates(true);
            Find<Button>("Install").Click += (s, e) => Run(false);
            Find<Button>("Uninstall").Click += (s, e) => Run(true);
            Find<TextBlock>("Pick").MouseLeftButtonUp += (s, e) => PickFolder();
            Find<TextBlock>("All").MouseLeftButtonUp += (s, e) =>
            {
                bool all = mod.Comps.All(c => c.Box.IsChecked == true);
                foreach (var c in mod.Comps) c.Box.IsChecked = !all;
            };
            mod.Log = msg => win.Dispatcher.BeginInvoke(new Action(() => Find<TextBlock>("Status").Text = msg.Trim()));
            foreach (var g in mod.FindGames(exeDir)) AddGame(g);
            BuildComps();
            Refresh();
            if (snapshot != null)
            {
                win.ShowInTaskbar = false;
                win.WindowStartupLocation = WindowStartupLocation.Manual;
                win.Left = -3000;
                win.ContentRendered += (s, e) => SaveSnapshot();
            }
            app.Run(win);
        }

        void AddGame(Game g)
        {
            if (games.Any(x => string.Equals(x.Dir, g.Dir, StringComparison.OrdinalIgnoreCase))) return;
            games.Add(g);
            var card = new Border { CornerRadius = new CornerRadius(8), Background = Brush("#1E2126"), BorderBrush = Brush("#2C3038"),
                                    BorderThickness = new Thickness(1), Padding = new Thickness(16, 14, 16, 14), Margin = new Thickness(0, 0, 0, 10) };
            var stack = new StackPanel();
            stack.Children.Add(new TextBlock { Text = g.Label, FontSize = 16, FontWeight = FontWeights.SemiBold, Foreground = Brush("#ECEEF1") });
            stack.Children.Add(new TextBlock { Text = ShortPath(g.Dir), ToolTip = g.Dir, FontSize = 11.5, Foreground = Brush("#7D838C"),
                                               TextTrimming = TextTrimming.CharacterEllipsis, Margin = new Thickness(0, 4, 0, 6), MaxWidth = 220 });
            g.State = new TextBlock { FontSize = 12.5, Foreground = Brush("#9AA0A8"), TextWrapping = TextWrapping.Wrap, MaxWidth = 230 };
            stack.Children.Add(g.State);
            g.Box = new CheckBox { Content = stack, IsChecked = mod.Covers(g.Kind) };
            if (!mod.Covers(g.Kind)) g.Box.IsHitTestVisible = false;   // 这个包里没有它的文件：不能勾选，只显示提示
            card.Child = g.Box;
            Find<StackPanel>("GameList").Children.Add(card);
        }

        void BuildComps()
        {
            var list = Find<System.Windows.Controls.Primitives.UniformGrid>("CompList");
            foreach (var c in mod.Comps)
            {
                string[] info;
                if (!Info.TryGetValue(c.Id, out info)) info = new[] { c.Name, "" };
                var card = new Border { CornerRadius = new CornerRadius(8), Background = Brush("#1E2126"), BorderBrush = Brush("#2C3038"),
                                        BorderThickness = new Thickness(1), Padding = new Thickness(14, 11, 12, 11), Margin = new Thickness(0, 0, 10, 10) };
                var stack = new StackPanel();
                var title = new DockPanel { LastChildFill = true };
                c.State = new TextBlock { FontSize = 11, Foreground = Brush("#5FBF7F"), VerticalAlignment = VerticalAlignment.Center };
                DockPanel.SetDock(c.State, Dock.Right);
                title.Children.Add(c.State);
                title.Children.Add(new TextBlock { Text = info[0], FontSize = 14.5, FontWeight = FontWeights.SemiBold, Foreground = Brush("#ECEEF1") });
                stack.Children.Add(title);
                stack.Children.Add(new TextBlock { Text = info[1], FontSize = 11.5, Foreground = Brush("#8A9099"), TextTrimming = TextTrimming.CharacterEllipsis, Margin = new Thickness(0, 3, 0, 0) });
                c.Box = new CheckBox { Content = stack, IsChecked = true, HorizontalContentAlignment = HorizontalAlignment.Stretch };
                card.Child = c.Box;
                list.Children.Add(card);
            }
        }

        static string ShortPath(string dir)
        {
            // 卡片标题已经写了是哪个游戏，这里只标来源；完整路径放在鼠标悬停提示里
            if (dir.IndexOf("steamapps", StringComparison.OrdinalIgnoreCase) >= 0) return "Steam 版";
            if (dir.IndexOf("Origin", StringComparison.OrdinalIgnoreCase) >= 0 || dir.IndexOf("EA Games", StringComparison.OrdinalIgnoreCase) >= 0) return "EA App / Origin 版";
            return dir;
        }

        static SolidColorBrush Brush(string hex) { return (SolidColorBrush)new BrushConverter().ConvertFromString(hex); }

        void Refresh()
        {
            var any = new HashSet<string>();
            foreach (var g in games)
            {
                var have = mod.Installed(g);
                if (!mod.Covers(g.Kind))
                {
                    g.State.Text = "这个安装包不含" + g.Label + "的文件。请下载「" + Mod.PackFor(g.Kind) + "」版或「完整版」。";
                    g.State.Foreground = Brush("#E0A84F");
                    continue;
                }
                foreach (var id in have) any.Add(id);
                g.State.Text = have.Count == 0 ? "未安装本 MOD" : "已安装 " + have.Count + " 项";
                g.State.Foreground = Brush(have.Count == 0 ? "#9AA0A8" : "#5FBF7F");
            }
            foreach (var c in mod.Comps)
            {
                c.State.Text = any.Contains(c.Id) ? "已安装" : "";
                if (any.Count > 0) c.Box.IsChecked = any.Contains(c.Id);
            }
            var status = Find<TextBlock>("Status");
            status.Foreground = Brush("#8A9099");
            if (games.Count == 0)
                status.Text = "没有自动找到游戏，请点左边的“手动选择游戏目录”。";
            else if (!games.Any(g => mod.Covers(g.Kind)))
            {
                status.Text = "下错版本了：这个安装包是「" + mod.Edition + "」，和你电脑上的游戏对不上，请换一个安装包。";
                status.Foreground = Brush("#E0A84F");
            }
            else
                status.Text = any.Count > 0 ? "勾选要保留的内容，取消勾选的会被卸载。" : "勾选要安装的内容，然后点“安装”。";
        }

        static object[] Patches(string json) { return Mod.Patches(json); }

        async void CheckUpdates(bool userAsked)
        {
            var status = Find<TextBlock>("Status");
            var targets = games.Where(g => mod.Covers(g.Kind) && mod.Installed(g).Count > 0).ToList();
            if (targets.Count == 0) { if (userAsked) status.Text = "还没有安装本 MOD，先点“安装 / 更新”。"; return; }
            status.Text = "正在检查更新……";
            object[] patches;
            try
            {
                patches = await Task.Run(() => mod.LoadManifest());
            }
            catch (Exception ex) { if (userAsked) status.Text = "检查更新失败（网络不通或服务器暂时不可用）：" + ex.Message; else status.Text = ""; return; }
            var todo = targets.Select(g => Tuple.Create(g, mod.PatchFor(g, patches))).Where(t => t.Item2 != null).ToList();
            if (todo.Count == 0) { if (userAsked) status.Text = "已经是最新版本。"; else Refresh(); return; }
            long total = todo.Sum(t => mod.PatchFiles(t.Item1, t.Item2).Sum(f => f.Item2));
            var first = todo[0].Item2;
            var msg = "发现新版本 v" + first["version"] + "（" + first["build"] + "）\n\n" + first["notes"] + "\n\n需要下载约 "
                      + Math.Max(1, total / 1000000) + " MB，现在更新吗？";
            if (MessageBox.Show(win, msg, "红色警戒3 中文配音 · 更新", MessageBoxButton.YesNo) != MessageBoxResult.Yes) { status.Text = ""; return; }
            foreach (var b in new[] { "Install", "Uninstall", "Close" }) Find<Button>(b).IsEnabled = false;
            var bar = Find<ProgressBar>("Bar");
            long done = 0;
            var baseUrl = mod.BaseUrl;
            try
            {
                foreach (var t in todo)
                {
                    var g = t.Item1; var p = t.Item2;
                    status.Text = g.Label + "：正在下载更新……";
                    mod.SavePatchInfo(p);
                    await Task.Run(() =>
                    {
                        foreach (var f in mod.PatchFiles(g, p))
                            mod.Fetch(baseUrl, f, n => { done += n; win.Dispatcher.BeginInvoke(new Action(() => bar.Value = Math.Min(1.0, (double)done / Math.Max(1, total)))); });
                        mod.ApplyPatch(g, p);
                    });
                }
                status.Text = "更新完成！正常启动游戏即可。";
                status.Foreground = Brush("#5FBF7F");
            }
            catch (UnauthorizedAccessException) { MessageBox.Show(win, "没有写入权限，请右键安装程序选择“以管理员身份运行”。", "更新没有完成"); }
            catch (Exception ex) { MessageBox.Show(win, ex.Message, "更新没有完成"); status.Text = "更新没有完成，可以稍后再试。"; }
            foreach (var b in new[] { "Install", "Uninstall", "Close" }) Find<Button>(b).IsEnabled = true;
            Refresh();
        }

        void ShowDiagnosis()
        {
            var w = new Window { Title = "故障诊断", Width = 760, Height = 620, WindowStartupLocation = WindowStartupLocation.CenterOwner,
                                 Owner = win, Background = Brush("#15171B"), FontFamily = new FontFamily("Microsoft YaHei UI"), ResizeMode = ResizeMode.CanResize };
            var root = new DockPanel { Margin = new Thickness(22) };
            var head = new TextBlock { Text = "故障诊断", FontSize = 22, FontWeight = FontWeights.Bold, Foreground = Brush("#ECEEF1"), Margin = new Thickness(0, 0, 0, 4) };
            var sub = new TextBlock { Text = "检查常见的“装了没效果”原因。看到红色或黄色的条目，按右边的建议处理即可。", FontSize = 12.5,
                                      Foreground = Brush("#8A9099"), Margin = new Thickness(0, 0, 0, 14), TextWrapping = TextWrapping.Wrap };
            DockPanel.SetDock(head, Dock.Top); DockPanel.SetDock(sub, Dock.Top);
            root.Children.Add(head); root.Children.Add(sub);
            var bar = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
            var copy = new Button { Content = "复制诊断报告", Style = (Style)win.FindResource("Btn"), Margin = new Thickness(0, 0, 12, 0) };
            var close = new Button { Content = "关闭", Style = (Style)win.FindResource("Btn"), Background = Brush("#D7262E") };
            bar.Children.Add(copy); bar.Children.Add(close);
            DockPanel.SetDock(bar, Dock.Bottom);
            root.Children.Add(bar);
            var list = new StackPanel();
            var scroll = new ScrollViewer { Content = list, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
            root.Children.Add(scroll);
            var targets = games.Count > 0 ? games : new List<Game>();
            if (targets.Count == 0)
                list.Children.Add(new TextBlock { Text = "没有找到游戏。请先在主界面点“手动选择游戏目录”。", Foreground = Brush("#E0A84F"), FontSize = 14 });
            foreach (var g in targets)
            {
                list.Children.Add(new TextBlock { Text = g.Label, FontSize = 16, FontWeight = FontWeights.SemiBold, Foreground = Brush("#ECEEF1"),
                                                  Margin = new Thickness(0, 10, 0, 6) });
                foreach (var c in mod.Diagnose(g))
                {
                    var color = c.Level == 0 ? "#5FBF7F" : c.Level == 1 ? "#E0A84F" : "#E8484F";
                    var row = new Grid { Margin = new Thickness(0, 0, 0, 8) };
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(28) });
                    row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(210) });
                    row.ColumnDefinitions.Add(new ColumnDefinition());
                    var icon = new TextBlock { Text = c.Level == 0 ? "✓" : c.Level == 1 ? "!" : "✗", Foreground = Brush(color), FontSize = 15, FontWeight = FontWeights.Bold };
                    var title = new TextBlock { Text = c.Title, Foreground = Brush("#ECEEF1"), FontSize = 13.5, TextWrapping = TextWrapping.Wrap };
                    var detail = new TextBlock { Text = c.Detail, Foreground = Brush(c.Level == 0 ? "#8A9099" : "#C9CDD3"), FontSize = 12.5, TextWrapping = TextWrapping.Wrap };
                    Grid.SetColumn(title, 1); Grid.SetColumn(detail, 2);
                    row.Children.Add(icon); row.Children.Add(title); row.Children.Add(detail);
                    list.Children.Add(row);
                }
            }
            copy.Click += (s, e) => { Clipboard.SetText(mod.Report(targets)); copy.Content = "已复制，可以直接粘贴发给作者"; };
            close.Click += (s, e) => w.Close();
            w.Content = root;
            w.ShowDialog();
            Refresh();
        }

        void PickFolder()
        {
            var dlg = new System.Windows.Forms.FolderBrowserDialog { Description = "选择《红色警戒3》或《起义时刻》的安装文件夹（里面有 RA3.exe 或 RA3EP1.exe）" };
            if (dlg.ShowDialog() != System.Windows.Forms.DialogResult.OK) return;
            var kind = Mod.KindOf(dlg.SelectedPath);
            if (kind == null) { MessageBox.Show(win, "这个文件夹里没有找到红警3或起义时刻。", "红色警戒3 中文配音"); return; }
            AddGame(new Game { Dir = dlg.SelectedPath.TrimEnd('\\'), Kind = kind });
            Refresh();
        }

        async void Run(bool uninstall)
        {
            var targets = games.Where(g => g.Box.IsChecked == true && mod.Covers(g.Kind)).ToList();
            if (targets.Count == 0) { Find<TextBlock>("Status").Text = "请先勾选至少一个游戏。"; return; }
            var want = uninstall ? new List<Comp>() : mod.Comps.Where(c => c.Box.IsChecked == true).ToList();
            if (uninstall && MessageBox.Show(win, "确定要完全卸载，恢复原版吗？", "红色警戒3 中文配音", MessageBoxButton.YesNo) != MessageBoxResult.Yes) return;
            foreach (var b in new[] { "Install", "Uninstall", "Close" }) Find<Button>(b).IsEnabled = false;
            var bar = Find<ProgressBar>("Bar");
            bar.Value = 0;
            var errors = new List<string>();
            var warnings = new List<string>();
            for (int i = 0; i < targets.Count; i++)
            {
                var g = targets[i];
                mod.Log(g.Label + "：" + (want.Count == 0 ? "正在恢复原版……" : "正在安装……"));
                try
                {
                    if (want.Any(c => c.Kind != "text"))
                    {
                        var w = mod.AudioWarning(g);
                        if (w != null) warnings.Add(g.Label + "：" + w);
                    }
                    await Task.Run(() => mod.Apply(g, want));
                }
                catch (UnauthorizedAccessException)
                {
                    errors.Add(g.Label + "：没有写入权限，请右键安装程序选择“以管理员身份运行”");
                }
                catch (Exception ex)
                {
                    errors.Add(g.Label + "：" + ex.Message);
                }
                bar.Value = (i + 1.0) / targets.Count;
            }
            Refresh();
            foreach (var b in new[] { "Install", "Uninstall", "Close" }) Find<Button>(b).IsEnabled = true;
            var status = Find<TextBlock>("Status");
            if (errors.Count > 0)
            {
                status.Text = "有问题，详见提示。";
                MessageBox.Show(win, string.Join("\n", errors), "没有全部完成", MessageBoxButton.OK, MessageBoxImage.Warning);
            }
            else
            {
                status.Text = want.Count == 0 ? "已完全卸载，游戏恢复原版。" : "完成！从 Steam / EA App 正常启动游戏即可。";
                status.Foreground = Brush("#5FBF7F");
                if (warnings.Count > 0) MessageBox.Show(win, string.Join("\n", warnings), "提示", MessageBoxButton.OK, MessageBoxImage.Information);
            }
        }
    }
}
