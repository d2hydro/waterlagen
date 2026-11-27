// Windows x64 host for the local Runmaker. Build with build.cmd.
using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;

internal static class Runmaker
{
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)]
    private static extern int SetCurrentProcessExplicitAppUserModelID(string id);

    private static bool IsWebLink(Uri uri)
    {
        return uri.Scheme == Uri.UriSchemeHttp || uri.Scheme == Uri.UriSchemeHttps;
    }

    [STAThread]
    private static int Main(string[] args)
    {
        Uri page;
        if (args.Length != 1 || !Uri.TryCreate(args[0], UriKind.Absolute, out page)
            || page.Scheme != Uri.UriSchemeHttp || page.Host != "127.0.0.1")
            return 2;

        SetCurrentProcessExplicitAppUserModelID("Waterlagen.Runmaker");
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        int result = 0;
        using (var window = new Form())
        using (var icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath))
        using (var view = new WebView2())
        {
            window.AutoScaleMode = AutoScaleMode.Dpi;
            window.Text = "Waterlagen · Runmaker";
            window.Icon = icon;
            window.StartPosition = FormStartPosition.CenterScreen;
            window.Size = new Size(1200, 820);
            window.MinimumSize = new Size(640, 480);
            view.Dock = DockStyle.Fill;
            view.CreationProperties = new CoreWebView2CreationProperties {
                UserDataFolder = Path.Combine(Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData), "Waterlagen", "WebView2")
            };
            window.Controls.Add(view);
            window.Shown += async (sender, e) => {
                try
                {
                    window.TopMost = true;
                    window.Activate();
                    window.TopMost = false;
                    await view.EnsureCoreWebView2Async(null);
                    if (window.IsDisposed) return;
                    view.CoreWebView2.NavigationStarting += (s, navigation) => {
                        Uri target;
                        navigation.Cancel = !Uri.TryCreate(navigation.Uri, UriKind.Absolute, out target)
                            || target.GetLeftPart(UriPartial.Authority) != page.GetLeftPart(UriPartial.Authority);
                    };
                    view.CoreWebView2.NewWindowRequested += (s, request) => {
                        request.Handled = true;
                        Uri link;
                        if (request.IsUserInitiated && Uri.TryCreate(request.Uri, UriKind.Absolute, out link)
                            && IsWebLink(link))
                            Process.Start(new ProcessStartInfo(link.AbsoluteUri) { UseShellExecute = true });
                    };
                    view.Source = page;
                }
                catch (Exception error)
                {
                    if (window.IsDisposed) return;
                    result = 1;
                    MessageBox.Show(window, "De kaart kan niet worden geopend. Controleer of Microsoft Edge WebView2 Runtime is geïnstalleerd.\n\n" +
                        error.Message, window.Text, MessageBoxButtons.OK, MessageBoxIcon.Error);
                    window.Close();
                }
            };
            Application.Run(window);
        }
        return result;
    }
}
