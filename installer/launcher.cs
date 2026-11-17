// Barrens Voice.exe: what a player finds in the install folder, with the app's icon - it starts the
// launcher of the current version (app\current, a junction bv/update.py points at each version).
// Compiled by tools/installer.py with the C# compiler of the .NET Framework every Windows 10/11 has.
using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Windows.Forms;

static class BarrensVoice
{
    [STAThread]
    static int Main(string[] args)
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string current = Path.Combine(root, "app", "current");
        string pythonw = Path.Combine(current, ".venv", "Scripts", "pythonw.exe");
        string script = Path.Combine(current, "companion", "BarrensVoice.pyw");
        if (!File.Exists(pythonw) || !File.Exists(script))
        {
            MessageBox.Show("Barrens Voice установлен не до конца: нет " + (File.Exists(pythonw) ? script : pythonw) +
                            ".\n\nУстановите его заново.", "Barrens Voice", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        var start = new ProcessStartInfo(pythonw)
        {
            Arguments = "\"" + script + "\"" + string.Concat(args.Select(a => " \"" + a.Replace("\"", "\\\"") + "\"")),
            WorkingDirectory = Path.Combine(current, "companion"),
            UseShellExecute = false,
        };
        Process.Start(start);
        return 0;
    }
}
