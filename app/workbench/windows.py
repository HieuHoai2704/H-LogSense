"""Windows Explorer identity and shortcuts for the desktop launcher."""

from ctypes import POINTER, Structure, WinDLL, byref, c_int, c_void_p, sizeof, windll
from ctypes import wintypes
from pathlib import Path
import sys

APP_ID = "HieuHoai.HLogsen.Workbench"
ICON = Path(__file__).resolve().parents[1] / "static" / "h-logsen.ico"


def identify_process():
    if windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID):
        raise RuntimeError("Could not register H-logsen with the Windows taskbar.")


class _FrameMargins(Structure):
    _fields_ = [(side, c_int) for side in ("left", "right", "top", "bottom")]


def set_window_glass(window, enabled):
    form = window.native
    if form is None or form.IsDisposed:
        return False
    from System import Boolean, Func
    from System.Drawing import Color, ColorTranslator

    dwm = WinDLL("dwmapi")
    dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, c_void_p, wintypes.DWORD]
    dwm.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, POINTER(_FrameMargins)]

    def apply():
        hwnd = form.Handle.ToInt64()
        if enabled:
            # DWMWA_SYSTEMBACKDROP_TYPE / DWMSBT_TRANSIENTWINDOW (Desktop Acrylic).
            backdrop = c_int(3)
            if dwm.DwmSetWindowAttribute(hwnd, 38, byref(backdrop), sizeof(backdrop)) != 0:
                return False
            if dwm.DwmExtendFrameIntoClientArea(hwnd, byref(_FrameMargins(-1, -1, -1, -1))) != 0:
                form.update_title_bar_theme()
                return False
            dark = c_int(1)
            dwm.DwmSetWindowAttribute(hwnd, 20, byref(dark), sizeof(dark))
            form.BackColor = Color.Black
            form.webview.DefaultBackgroundColor = Color.Transparent
        else:
            # Restore pywebview's normal shadow margins and Windows title bar theme.
            dwm.DwmExtendFrameIntoClientArea(hwnd, byref(_FrameMargins(1, 1, 1, 1)))
            form.update_title_bar_theme()
            background = ColorTranslator.FromHtml(window.background_color)
            form.BackColor = background
            form.webview.DefaultBackgroundColor = background
        return True

    return bool(form.Invoke(Func[Boolean](apply)))


def install_shortcuts():
    import pythoncom
    from win32com.propsys import propsys, pscon
    from win32com.shell import shell, shellcon

    executable = Path(sys.executable).with_name("pythonw.exe")
    if not executable.is_file() or not ICON.is_file():
        raise RuntimeError("Install H-logsen before creating shortcuts.")
    def new_link():
        return pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None, pythoncom.CLSCTX_INPROC_SERVER,
                                          shell.IID_IShellLink)

    for location in (shellcon.CSIDL_DESKTOPDIRECTORY, shellcon.CSIDL_PROGRAMS):
        directory = Path(shell.SHGetFolderPath(0, location, 0, 0))
        path = directory / "H-logsen.lnk"
        if path.exists():
            existing = new_link()
            existing.QueryInterface(pythoncom.IID_IPersistFile).Load(str(path))
            target, _ = existing.GetPath(0)
            app_id = existing.QueryInterface(propsys.IID_IPropertyStore).GetValue(pscon.PKEY_AppUserModel_ID).GetValue()
            if app_id != APP_ID and Path(target).name.casefold() != "h-logsen-desktop.exe":
                print(f"Skipped existing shortcut: {path}")
                continue
        link = new_link()
        properties = link.QueryInterface(propsys.IID_IPropertyStore)
        link.SetPath(str(executable))
        link.SetArguments("-I -m app.workbench --desktop")
        link.SetWorkingDirectory(str(executable.parents[2]))
        link.SetDescription("H-logsen desktop workbench")
        link.SetIconLocation(str(ICON), 0)
        properties.SetValue(pscon.PKEY_AppUserModel_ID, propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
        properties.Commit()
        link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), 1)
        print(f"H-logsen shortcut: {path}")


if __name__ == "__main__":
    install_shortcuts()
