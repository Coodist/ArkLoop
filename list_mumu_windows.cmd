@echo off
chcp 65001 >nul
setlocal
set "ps=%TEMP%\list_mumu_windows.ps1"

>"%ps%" echo Add-Type -TypeDefinition @'
>>"%ps%" echo using System;
>>"%ps%" echo using System.Runtime.InteropServices;
>>"%ps%" echo using System.Text;
>>"%ps%" echo public class MuMuWinLister {
>>"%ps%" echo     [DllImport("user32.dll", CharSet = CharSet.Unicode)]
>>"%ps%" echo     static extern IntPtr FindWindow(string lpClassName, string lpWindowName);
>>"%ps%" echo     delegate bool EnumChildProc(IntPtr hwnd, IntPtr lParam);
>>"%ps%" echo     [DllImport("user32.dll")]
>>"%ps%" echo     static extern bool EnumChildWindows(IntPtr hWndParent, EnumChildProc lpEnumFunc, IntPtr lParam);
>>"%ps%" echo     [DllImport("user32.dll", CharSet = CharSet.Unicode)]
>>"%ps%" echo     static extern int GetClassName(IntPtr hWnd, StringBuilder lpClassName, int nMaxCount);
>>"%ps%" echo     [DllImport("user32.dll", CharSet = CharSet.Unicode)]
>>"%ps%" echo     static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
>>"%ps%" echo     [DllImport("user32.dll")]
>>"%ps%" echo     static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
>>"%ps%" echo     [StructLayout(LayoutKind.Sequential)]
>>"%ps%" echo     struct RECT { public int Left, Top, Right, Bottom; }
>>"%ps%" echo     static bool Callback(IntPtr hwnd, IntPtr lParam) {
>>"%ps%" echo         var cls = new StringBuilder(256);
>>"%ps%" echo         var txt = new StringBuilder(256);
>>"%ps%" echo         GetClassName(hwnd, cls, 256);
>>"%ps%" echo         GetWindowText(hwnd, txt, 256);
>>"%ps%" echo         RECT rc;
>>"%ps%" echo         GetWindowRect(hwnd, out rc);
>>"%ps%" echo         Console.WriteLine("h=0x{0:X8} | class={1,-30} | title={2,-30} | size={3}x{4}", hwnd.ToInt64(), cls.ToString(), txt.ToString(), rc.Right - rc.Left, rc.Bottom - rc.Top);
>>"%ps%" echo         return true;
>>"%ps%" echo     }
>>"%ps%" echo     public static void List(string parentTitle) {
>>"%ps%" echo         IntPtr parent = FindWindow(null, parentTitle);
>>"%ps%" echo         if (parent == IntPtr.Zero) { Console.WriteLine("Parent not found: " + parentTitle); return; }
>>"%ps%" echo         Console.WriteLine("Parent: 0x{0:X8} ({1})", parent.ToInt64(), parentTitle);
>>"%ps%" echo         EnumChildWindows(parent, Callback, IntPtr.Zero);
>>"%ps%" echo     }
>>"%ps%" echo }
>>"%ps%" echo '@
>>"%ps%" echo [MuMuWinLister]::List("MuMu模拟器12")

powershell -NoProfile -ExecutionPolicy Bypass -File "%ps%"
echo.
echo 按任意键退出...
pause >nul
