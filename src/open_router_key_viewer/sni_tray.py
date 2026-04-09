"""GNOME panel indicator via D-Bus StatusNotifierItem + XAyatanaLabel.

Uses PySide6.QtDBus to implement the SNI protocol natively, with no GTK
dependency.  Falls back gracefully when QtDBus is unavailable or when the
desktop does not run an SNI watcher (org.kde.StatusNotifierWatcher).
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import shiboken6
from PySide6.QtCore import ClassInfo, Property, QObject, QTimer, Signal, Slot
from PySide6.QtDBus import (
    QDBusAbstractAdaptor,
    QDBusArgument,
    QDBusConnection,
    QDBusInterface,
    QDBusMessage,
    QDBusObjectPath,
    QDBusVariant,
    QDBusVirtualObject,
)

import PySide6 as _PySide6

# ---------------------------------------------------------------------------
# ctypes bridge for correct QDBusArgument writes
# ---------------------------------------------------------------------------

class _QtDBusTypeHelper:
    """Work around PySide6's broken ``QDBusArgument.__lshift__`` overloads.

    PySide6 6.x routes Python ``int`` to D-Bus ``q`` (uint16) and ``str`` to
    ``as`` (string-array).  We call the correct C++ ``operator<<`` overloads
    directly via ctypes so that ``int`` maps to ``i`` (int32) and ``str`` to
    ``s`` (string).
    """

    _instance: _QtDBusTypeHelper | None = None

    class _ManagedQString:
        """Tiny RAII wrapper around a stack-allocated ``QString``."""

        _QSTRING_SIZE = 24  # sizeof(QString) on 64-bit Qt 6
        _resize_fn: ctypes._NamedFuncPointer | None = None

        def __init__(self, text: str, ctor: ctypes._NamedFuncPointer) -> None:
            self._constructed = False
            self._storage = (ctypes.c_char * self._QSTRING_SIZE)()
            self._utf16 = ctypes.create_string_buffer(
                text.encode("utf-16-le"), len(text) * 2,
            )
            ctor(
                ctypes.addressof(self._storage),
                ctypes.addressof(self._utf16),
                ctypes.c_longlong(len(text)),
            )
            self._constructed = True

        @property
        def ptr(self) -> int:
            return ctypes.addressof(self._storage)

        def __del__(self) -> None:
            if self._constructed and self._resize_fn is not None:
                self._resize_fn(ctypes.addressof(self._storage), ctypes.c_longlong(0))

    def __init__(self) -> None:
        lib_dir = os.path.join(os.path.dirname(_PySide6.__file__), "Qt", "lib")
        dbus_lib = ctypes.CDLL(os.path.join(lib_dir, "libQt6DBus.so.6"))
        core_lib = ctypes.CDLL(os.path.join(lib_dir, "libQt6Core.so.6"))

        self._lshift_int = dbus_lib._ZN13QDBusArgumentlsEi
        self._lshift_int.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._lshift_int.restype = ctypes.c_void_p

        self._lshift_uint = dbus_lib._ZN13QDBusArgumentlsEj
        self._lshift_uint.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._lshift_uint.restype = ctypes.c_void_p

        self._lshift_bool = dbus_lib._ZN13QDBusArgumentlsEb
        self._lshift_bool.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        self._lshift_bool.restype = ctypes.c_void_p

        self._lshift_str = dbus_lib._ZN13QDBusArgumentlsERK7QString
        self._lshift_str.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._lshift_str.restype = ctypes.c_void_p

        self._qstring_ctor = core_lib._ZN7QStringC1EPK5QCharx
        self._qstring_ctor.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_longlong,
        ]
        self._qstring_ctor.restype = None

        # QString::resize(qsizetype) — used to free internal buffer (destructor is inlined)
        qstring_resize = core_lib._ZN7QString6resizeEx
        qstring_resize.argtypes = [ctypes.c_void_p, ctypes.c_longlong]
        qstring_resize.restype = None
        self._ManagedQString._resize_fn = qstring_resize

    @classmethod
    def get(cls) -> _QtDBusTypeHelper:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # -- primitive writers --------------------------------------------------

    def _ptr(self, arg: QDBusArgument) -> int:  # noqa: PLR6301
        return shiboken6.getCppPointer(arg)[0]

    def write_int32(self, arg: QDBusArgument, value: int) -> None:
        self._lshift_int(self._ptr(arg), ctypes.c_int(value))

    def write_uint32(self, arg: QDBusArgument, value: int) -> None:
        self._lshift_uint(self._ptr(arg), ctypes.c_uint(value))

    def write_bool(self, arg: QDBusArgument, value: bool) -> None:
        self._lshift_bool(self._ptr(arg), ctypes.c_bool(value))

    def write_string(self, arg: QDBusArgument, value: str) -> list:
        """Write a ``QString`` and return refs that must stay alive."""
        qs = self._ManagedQString(value, self._qstring_ctor)
        self._lshift_str(self._ptr(arg), qs.ptr)
        return [qs]

    # -- dbusmenu layout builder --------------------------------------------

    def build_menu_layout(
        self,
        items: list[tuple[int, dict[str, str | bool]]],
    ) -> QDBusArgument:
        """Build a ``(ia{sv}av)`` GetLayout response for a flat menu.

        *items* is ``[(id, {prop: value, ...}), ...]`` where id 0 is root.
        """
        refs: list[object] = []
        arg = QDBusArgument()
        root_id, root_props = items[0]
        self._write_layout_item(arg, root_id, root_props, items[1:], refs)
        arg._refs = refs  # prevent GC
        return arg

    def _write_layout_item(
        self,
        arg: QDBusArgument,
        item_id: int,
        props: dict[str, str | bool],
        children: list[tuple[int, dict[str, str | bool]]],
        refs: list[object],
    ) -> None:
        arg.beginStructure()
        self.write_int32(arg, item_id)

        # a{sv} — properties map
        # Key type: QString (metatype 10)
        # Value type: QDBusVariant
        from PySide6.QtCore import QMetaType
        variant_meta = QMetaType.fromName(b"QDBusVariant")
        arg.beginMap(QMetaType(10), variant_meta)
        for k, v in props.items():
            arg.beginMapEntry()
            refs.extend(self.write_string(arg, k))
            if isinstance(v, bool):
                arg << QDBusVariant(v)
            elif isinstance(v, str):
                arg << QDBusVariant(v)
            else:
                arg << QDBusVariant(str(v))
            arg.endMapEntry()
        arg.endMap()

        # av — children variant array
        arg.beginArray(variant_meta)
        for child_id, child_props in children:
            child_arg = QDBusArgument()
            self._write_layout_item(child_arg, child_id, child_props, [], refs)
            arg << QDBusVariant(child_arg)
        arg.endArray()

        arg.endStructure()


# ---------------------------------------------------------------------------
# D-Bus menu (com.canonical.dbusmenu)
# ---------------------------------------------------------------------------

_DBUSMENU_IFACE = "com.canonical.dbusmenu"
_DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_DBUS_INTROSPECT_IFACE = "org.freedesktop.DBus.Introspectable"

_DBUSMENU_XML = """\
<interface name="com.canonical.dbusmenu">
  <method name="GetLayout">
    <arg type="i" direction="in" name="parentId"/>
    <arg type="i" direction="in" name="recursionDepth"/>
    <arg type="as" direction="in" name="propertyNames"/>
    <arg type="u" direction="out" name="revision"/>
    <arg type="(ia{sv}av)" direction="out" name="layout"/>
  </method>
  <method name="Event">
    <arg type="i" direction="in" name="id"/>
    <arg type="s" direction="in" name="eventId"/>
    <arg type="v" direction="in" name="data"/>
    <arg type="u" direction="in" name="timestamp"/>
  </method>
  <method name="AboutToShow">
    <arg type="i" direction="in" name="id"/>
    <arg type="b" direction="out" name="needUpdate"/>
  </method>
  <method name="GetGroupProperties">
    <arg type="ai" direction="in" name="ids"/>
    <arg type="as" direction="in" name="propertyNames"/>
    <arg type="a(ia{sv})" direction="out" name="properties"/>
  </method>
  <signal name="LayoutUpdated">
    <arg type="u" name="revision"/>
    <arg type="i" name="parent"/>
  </signal>
  <signal name="ItemsPropertiesUpdated">
    <arg type="a(ia{sv})" name="updatedProps"/>
    <arg type="a(ias)" name="removedProps"/>
  </signal>
  <property name="Version" type="u" access="read"/>
  <property name="TextDirection" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconThemePath" type="as" access="read"/>
</interface>"""


class _DBusMenuObject(QDBusVirtualObject):

    def __init__(
        self,
        callbacks: dict[int, Callable[[], None]],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._callbacks = callbacks
        self._revision = 1

    def introspect(self, _path: str) -> str:
        return _DBUSMENU_XML

    def handleMessage(self, message: QDBusMessage, connection: QDBusConnection) -> bool:
        iface = message.interface()
        member = message.member()

        if iface == _DBUSMENU_IFACE:
            if member == "GetLayout":
                return self._reply_get_layout(message, connection)
            if member == "Event":
                return self._handle_event(message, connection)
            if member == "AboutToShow":
                reply = message.createReply([False])
                connection.send(reply)
                return True
            if member == "GetGroupProperties":
                reply = message.createReply()
                connection.send(reply)
                return True

        if iface == _DBUS_PROPS_IFACE:
            if member == "Get":
                return self._reply_property_get(message, connection)
            if member == "GetAll":
                return self._reply_property_getall(message, connection)

        if iface == _DBUS_INTROSPECT_IFACE and member == "Introspect":
            xml = f'<node>{_DBUSMENU_XML}</node>'
            reply = message.createReply([xml])
            connection.send(reply)
            return True

        return False

    def _reply_get_layout(
        self, message: QDBusMessage, connection: QDBusConnection,
    ) -> bool:
        helper = _QtDBusTypeHelper.get()
        items: list[tuple[int, dict[str, str | bool]]] = [
            (0, {"children-display": "submenu"}),
            (1, {"label": "刷新", "icon-name": "view-refresh", "enabled": True, "visible": True}),
            (2, {"label": "打开主窗口", "icon-name": "window-new", "enabled": True, "visible": True}),
            (3, {"type": "separator"}),
            (4, {"label": "退出", "icon-name": "application-exit", "enabled": True, "visible": True}),
        ]
        layout_arg = helper.build_menu_layout(items)

        reply = message.createReply()
        out_arg = QDBusArgument()
        helper.write_uint32(out_arg, self._revision)
        reply.setArguments([out_arg, layout_arg])
        connection.send(reply)
        return True

    def _handle_event(self, message: QDBusMessage, connection: QDBusConnection) -> bool:
        args = message.arguments()
        if len(args) >= 2:
            item_id = args[0]
            event_id = args[1]
            if event_id in ("clicked", "") and item_id in self._callbacks:
                self._callbacks[item_id]()
        connection.send(message.createReply())
        return True

    def _reply_property_get(
        self, message: QDBusMessage, connection: QDBusConnection,
    ) -> bool:
        args = message.arguments()
        prop = args[1] if len(args) >= 2 else ""
        value: object
        if prop == "Version":
            value = QDBusVariant(3)
        elif prop == "TextDirection":
            value = QDBusVariant("ltr")
        elif prop == "Status":
            value = QDBusVariant("normal")
        else:
            value = QDBusVariant("")
        reply = message.createReply([value])
        connection.send(reply)
        return True

    def _reply_property_getall(
        self, message: QDBusMessage, connection: QDBusConnection,
    ) -> bool:
        props = {
            "Version": QDBusVariant(3),
            "TextDirection": QDBusVariant("ltr"),
            "Status": QDBusVariant("normal"),
            "IconThemePath": QDBusVariant([]),
        }
        reply = message.createReply([props])
        connection.send(reply)
        return True


# ---------------------------------------------------------------------------
# SNI adaptor (org.kde.StatusNotifierItem)
# ---------------------------------------------------------------------------

_SNI_IFACE = "org.kde.StatusNotifierItem"

_SNI_XML = """\
<interface name="org.kde.StatusNotifierItem">
  <property name="Category" type="s" access="read"/>
  <property name="Id" type="s" access="read"/>
  <property name="Title" type="s" access="read"/>
  <property name="Status" type="s" access="read"/>
  <property name="IconName" type="s" access="read"/>
  <property name="Menu" type="o" access="read"/>
  <property name="ItemIsMenu" type="b" access="read"/>
  <property name="XAyatanaLabel" type="s" access="read"/>
  <property name="XAyatanaLabelGuide" type="s" access="read"/>
  <property name="XAyatanaOrderingIndex" type="u" access="read"/>
  <method name="Activate">
    <arg type="i" direction="in" name="x"/>
    <arg type="i" direction="in" name="y"/>
  </method>
  <method name="ContextMenu">
    <arg type="i" direction="in" name="x"/>
    <arg type="i" direction="in" name="y"/>
  </method>
  <method name="SecondaryActivate">
    <arg type="i" direction="in" name="x"/>
    <arg type="i" direction="in" name="y"/>
  </method>
  <signal name="NewTitle"/>
  <signal name="NewIcon"/>
  <signal name="NewStatus">
    <arg type="s"/>
  </signal>
  <signal name="XAyatanaNewLabel">
    <arg type="s" name="label"/>
    <arg type="s" name="guide"/>
  </signal>
</interface>"""


@ClassInfo({"D-Bus Interface": _SNI_IFACE, "D-Bus Introspection": _SNI_XML})
class _SNIAdaptor(QDBusAbstractAdaptor):
    NewTitle = Signal()
    NewIcon = Signal()
    NewStatus = Signal(str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._status = "Active"
        self._label = ""
        self._label_guide = ""
        self._icon_name = "open-router-key-viewer"
        self._on_activate: Callable[[], None] = lambda: None

    # -- constant properties ------------------------------------------------

    @Property(str, constant=True)
    def Category(self) -> str:
        return "ApplicationStatus"

    @Property(str, constant=True)
    def Id(self) -> str:
        return "open-router-key-viewer"

    @Property(str, constant=True)
    def Title(self) -> str:
        return "OpenRouter Key Viewer"

    @Property(str)
    def Status(self) -> str:
        return self._status

    @Property(str, constant=True)
    def IconName(self) -> str:
        return self._icon_name

    @Property(QDBusObjectPath, constant=True)
    def Menu(self) -> QDBusObjectPath:
        return QDBusObjectPath("/MenuBar")

    @Property(bool, constant=True)
    def ItemIsMenu(self) -> bool:
        return False

    # -- mutable Ayatana label properties -----------------------------------

    @Property(str)
    def XAyatanaLabel(self) -> str:
        return self._label

    @Property(str)
    def XAyatanaLabelGuide(self) -> str:
        return self._label_guide

    @Property(int)
    def XAyatanaOrderingIndex(self) -> int:
        return 0

    # -- methods ------------------------------------------------------------

    @Slot(int, int)
    def Activate(self, _x: int, _y: int) -> None:
        self._on_activate()

    @Slot(int, int)
    def ContextMenu(self, _x: int, _y: int) -> None:
        pass

    @Slot(int, int)
    def SecondaryActivate(self, _x: int, _y: int) -> None:
        pass

    # -- label updates (called by SNITray) ----------------------------------

    def set_label(self, text: str, guide: str) -> None:
        self._label = text
        self._label_guide = guide

    def set_status(self, status: str) -> None:
        self._status = status

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name


# ---------------------------------------------------------------------------
# Public orchestrator
# ---------------------------------------------------------------------------

_WATCHER_SERVICE = "org.kde.StatusNotifierWatcher"
_WATCHER_PATH = "/StatusNotifierWatcher"
_WATCHER_IFACE = "org.kde.StatusNotifierWatcher"


class SNITray(QObject):
    """GNOME panel indicator that shows a rotating text label next to an icon.

    Call :meth:`register` after construction.  If it returns ``False`` the
    desktop does not support the StatusNotifierItem protocol and the caller
    should fall back to ``QSystemTrayIcon``.
    """

    def __init__(
        self,
        *,
        activate: Callable[[], None],
        refresh: Callable[[], None],
        show_window: Callable[[], None],
        quit: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._activate = activate
        self._refresh = refresh
        self._show_window = show_window
        self._quit = quit
        self._bus: QDBusConnection | None = None
        self._service_name = ""
        self._sni_host: QObject | None = None
        self._sni_adaptor: _SNIAdaptor | None = None
        self._menu_obj: _DBusMenuObject | None = None
        self.is_active = False

    def register(self) -> bool:
        """Register on the session bus.  Returns ``True`` on success."""
        try:
            _QtDBusTypeHelper.get()
        except Exception:
            return False

        bus = QDBusConnection.sessionBus()
        if not bus.isConnected():
            return False

        watcher = QDBusInterface(_WATCHER_SERVICE, _WATCHER_PATH, _WATCHER_IFACE, bus)
        if not watcher.isValid():
            return False

        self._bus = bus
        self._service_name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"

        if not bus.registerService(self._service_name):
            return False

        self._sni_host = QObject()
        self._sni_adaptor = _SNIAdaptor(self._sni_host)
        self._sni_adaptor._on_activate = self._activate

        self._install_icon()

        self._menu_obj = _DBusMenuObject(
            callbacks={
                1: self._refresh,
                2: self._show_window,
                4: self._quit,
            },
        )

        if not bus.registerObject(
            "/StatusNotifierItem",
            self._sni_host,
            QDBusConnection.RegisterOption.ExportAdaptors,
        ):
            bus.unregisterService(self._service_name)
            return False

        if not bus.registerVirtualObject("/MenuBar", self._menu_obj):
            bus.unregisterObject("/StatusNotifierItem")
            bus.unregisterService(self._service_name)
            return False

        reply = watcher.call("RegisterStatusNotifierItem", self._service_name)
        if reply.type() == QDBusMessage.MessageType.ErrorMessage:
            bus.unregisterObject("/MenuBar")
            bus.unregisterObject("/StatusNotifierItem")
            bus.unregisterService(self._service_name)
            return False

        self.is_active = True
        return True

    def set_label(self, text: str, guide: str) -> None:
        """Update the text label displayed in the GNOME panel."""
        if self._sni_adaptor is None or self._bus is None:
            return
        self._sni_adaptor.set_label(text, guide)

        # GNOME's ubuntu-appindicators extension translates
        # "XAyatanaNewLabel" → refreshes XAyatanaLabel property.
        # "NewLabel" would be interpreted as refreshing "Label" (wrong).
        sig = QDBusMessage.createSignal(
            "/StatusNotifierItem",
            "org.kde.StatusNotifierItem",
            "XAyatanaNewLabel",
        )
        sig.setArguments([text, guide])
        self._bus.send(sig)

    def notify(self, title: str, body: str, urgency: str = "normal") -> None:
        """Show a desktop notification via ``notify-send``."""
        try:
            subprocess.Popen(  # noqa: S603
                ["notify-send", "-a", "OpenRouter Key Viewer",
                 "--urgency", urgency, title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def hide(self) -> None:
        """Hide the indicator by setting Status to Passive."""
        self._set_status("Passive")

    def show(self) -> None:
        """Show the indicator by setting Status to Active."""
        self._set_status("Active")

    def _set_status(self, status: str) -> None:
        if self._sni_adaptor is None or self._bus is None:
            return
        self._sni_adaptor.set_status(status)
        sig = QDBusMessage.createSignal(
            "/StatusNotifierItem",
            "org.kde.StatusNotifierItem",
            "NewStatus",
        )
        sig.setArguments([status])
        self._bus.send(sig)

    def unregister(self) -> None:
        """Clean up D-Bus registration."""
        if self._bus is not None:
            self._bus.unregisterObject("/MenuBar")
            self._bus.unregisterObject("/StatusNotifierItem")
            self._bus.unregisterService(self._service_name)
        self._sni_host = None
        self._sni_adaptor = None
        self._menu_obj = None
        self.is_active = False

    def _install_icon(self) -> None:
        """Copy the app icon to the XDG icon theme directory."""
        dest_dir = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
        dest = dest_dir / "open-router-key-viewer.svg"
        if dest.exists():
            return

        base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
        candidates = [
            base_dir / "assets" / "open-router-key-viewer.svg",
            Path(sys.argv[0]).resolve().parent / "assets" / "open-router-key-viewer.svg",
            Path.cwd() / "assets" / "open-router-key-viewer.svg",
        ]
        for src in candidates:
            if src.exists():
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    subprocess.Popen(
                        ["gtk-update-icon-cache", "-f", "-t",
                         str(dest_dir.parent.parent.parent)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                except OSError:
                    pass
                return

        self._sni_adaptor.set_icon_name("application-x-executable")
