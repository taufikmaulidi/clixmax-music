"""Integrasi media OS: lagu yang sedang diputar tampil di panel media sistem, dan tombol media bekerja.

Windows: System Media Transport Controls (panel volume, layar kunci, tombol media). Sudah diuji.
Linux:   MPRIS lewat D-Bus (applet media desktop, playerctl, tombol media). Belum diuji di desktop.
macOS:   MPNowPlayingInfoCenter (Pusat Kontrol, tombol media). Belum diuji.
Bila semuanya gagal di Windows, tombol media tetap ditangkap lewat system.watch_media_keys.
"""
import threading
import traceback

from . import system
from .config import log_error


class _Smtc:
    kind = "smtc"

    def __init__(self, on_action):
        from winrt.windows.foundation import Uri
        from winrt.windows.media import MediaPlaybackStatus, MediaPlaybackType
        from winrt.windows.media import SystemMediaTransportControlsButton as Button
        from winrt.windows.media.playback import MediaPlayer
        from winrt.windows.storage.streams import RandomAccessStreamReference
        self.Uri, self.Status, self.Type, self.Ref = Uri, MediaPlaybackStatus, MediaPlaybackType, RandomAccessStreamReference
        self.player = MediaPlayer()
        self.player.command_manager.is_enabled = False  # kendali dari ClixMax sendiri, bukan pemutar Windows
        smtc = self.smtc = self.player.system_media_transport_controls
        smtc.is_enabled = True
        for name in ("is_play_enabled", "is_pause_enabled", "is_next_enabled", "is_previous_enabled"):
            setattr(smtc, name, True)
        actions = {Button.PLAY: "play", Button.PAUSE: "pause", Button.STOP: "pause", Button.NEXT: "next",
                   Button.PREVIOUS: "prev"}
        self.token = smtc.add_button_pressed(lambda sender, args: actions.get(args.button) and
                                             on_action(actions[args.button]))
        smtc.playback_status = MediaPlaybackStatus.STOPPED

    def update(self, title, artist, art_url, playing, active):
        updater = self.smtc.display_updater
        if active:
            updater.type = self.Type.MUSIC
            updater.music_properties.title = title
            updater.music_properties.artist = artist
            if art_url:
                updater.thumbnail = self.Ref.create_from_uri(self.Uri(art_url))
        else:
            updater.clear_all()
        updater.update()
        self.smtc.playback_status = (self.Status.PLAYING if playing else
                                     self.Status.PAUSED if active else self.Status.STOPPED)

    def close(self):
        self.smtc.remove_button_pressed(self.token)
        self.smtc.is_enabled = False


class _Mpris:
    kind = "mpris"

    def __init__(self, on_action):
        import asyncio
        from dbus_next import BusType, Variant
        from dbus_next.aio import MessageBus
        from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method

        self.Variant = Variant
        state = self.state = {"status": "Stopped", "meta": {
            "mpris:trackid": Variant("o", "/org/mpris/MediaPlayer2/TrackList/NoTrack")}}

        class Root(ServiceInterface):
            def __init__(self):
                super().__init__("org.mpris.MediaPlayer2")

            @method()
            def Raise(self):
                on_action("show")

            @method()
            def Quit(self):
                on_action("quit")

            @dbus_property(access=PropertyAccess.READ)
            def CanQuit(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanRaise(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def HasTrackList(self) -> "b":
                return False

            @dbus_property(access=PropertyAccess.READ)
            def Identity(self) -> "s":
                return "ClixMax"

            @dbus_property(access=PropertyAccess.READ)
            def SupportedUriSchemes(self) -> "as":
                return []

            @dbus_property(access=PropertyAccess.READ)
            def SupportedMimeTypes(self) -> "as":
                return []

        class Player(ServiceInterface):
            def __init__(self):
                super().__init__("org.mpris.MediaPlayer2.Player")

            @method()
            def Next(self):
                on_action("next")

            @method()
            def Previous(self):
                on_action("prev")

            @method()
            def Pause(self):
                on_action("pause")

            @method()
            def Play(self):
                on_action("play")

            @method()
            def PlayPause(self):
                on_action("toggle")

            @method()
            def Stop(self):
                on_action("pause")

            @dbus_property(access=PropertyAccess.READ)
            def PlaybackStatus(self) -> "s":
                return state["status"]

            @dbus_property(access=PropertyAccess.READ)
            def Metadata(self) -> "a{sv}":
                return state["meta"]

            @dbus_property(access=PropertyAccess.READ)
            def Rate(self) -> "d":
                return 1.0

            @dbus_property(access=PropertyAccess.READ)
            def CanGoNext(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanGoPrevious(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanPlay(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanPause(self) -> "b":
                return True

            @dbus_property(access=PropertyAccess.READ)
            def CanSeek(self) -> "b":
                return False

            @dbus_property(access=PropertyAccess.READ)
            def CanControl(self) -> "b":
                return True

        self.root, self.player = Root(), Player()
        self.loop = asyncio.new_event_loop()
        ready, failure = threading.Event(), []

        def run():
            asyncio.set_event_loop(self.loop)

            async def connect():
                bus = await MessageBus(bus_type=BusType.SESSION).connect()
                bus.export("/org/mpris/MediaPlayer2", self.root)
                bus.export("/org/mpris/MediaPlayer2", self.player)
                await bus.request_name("org.mpris.MediaPlayer2.clixmax")
                return bus

            try:
                self.bus = self.loop.run_until_complete(connect())
            except Exception as exc:
                failure.append(exc)
                ready.set()
                return
            ready.set()
            self.loop.run_forever()

        threading.Thread(target=run, daemon=True).start()
        if not ready.wait(5) or failure:
            raise RuntimeError("D-Bus sesi tidak tersedia: %s" % (failure[0] if failure else "waktu habis"))

    def update(self, title, artist, art_url, playing, active):
        Variant = self.Variant
        meta = {"mpris:trackid": Variant("o", "/org/clixmax/track/now" if active else
                                         "/org/mpris/MediaPlayer2/TrackList/NoTrack")}
        if active:
            meta["xesam:title"] = Variant("s", title)
            meta["xesam:artist"] = Variant("as", [artist] if artist else [])
            if art_url:
                meta["mpris:artUrl"] = Variant("s", art_url)
        status = "Playing" if playing else ("Paused" if active else "Stopped")

        def apply():
            self.state.update(status=status, meta=meta)
            self.player.emit_properties_changed({"PlaybackStatus": status, "Metadata": meta})

        self.loop.call_soon_threadsafe(apply)

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)


class _MacNowPlaying:
    kind = "macos"

    def __init__(self, on_action):
        import MediaPlayer as MP
        self.MP = MP
        center = MP.MPRemoteCommandCenter.sharedCommandCenter()

        def handler(action):
            def handle(event):
                on_action(action)
                return 0  # MPRemoteCommandHandlerStatusSuccess
            return handle

        self.handlers = []
        for command, action in ((center.togglePlayPauseCommand(), "toggle"), (center.playCommand(), "play"),
                                (center.pauseCommand(), "pause"), (center.nextTrackCommand(), "next"),
                                (center.previousTrackCommand(), "prev")):
            command.setEnabled_(True)
            self.handlers.append(handler(action))
            command.addTargetWithHandler_(self.handlers[-1])
        self.info = MP.MPNowPlayingInfoCenter.defaultCenter()

    def update(self, title, artist, art_url, playing, active):
        MP = self.MP
        if active:
            self.info.setNowPlayingInfo_({MP.MPMediaItemPropertyTitle: title, MP.MPMediaItemPropertyArtist: artist,
                                          MP.MPNowPlayingInfoPropertyPlaybackRate: 1.0 if playing else 0.0})
        else:
            self.info.setNowPlayingInfo_(None)
        self.info.setPlaybackState_(MP.MPNowPlayingPlaybackStatePlaying if playing else
                                    MP.MPNowPlayingPlaybackStatePaused if active else
                                    MP.MPNowPlayingPlaybackStateStopped)

    def close(self):
        self.info.setNowPlayingInfo_(None)


class MediaSession:
    """Satu pintu untuk App: update() dipanggil saat lagu atau status putar berubah."""

    def __init__(self, on_action):
        self.impl, self.kind, self.last = None, "none", None
        builder = _Smtc if system.WINDOWS else _MacNowPlaying if system.MAC else _Mpris
        try:
            self.impl = builder(on_action)
            self.kind = self.impl.kind
        except Exception:
            log_error("Integrasi media OS tidak aktif:\n" + traceback.format_exc())
        if self.impl is None and system.watch_media_keys(on_action):
            self.kind = "hotkeys"

    def update(self, title, artist, art_url, playing, active):
        key = (title, artist, art_url, playing, active)
        if self.impl is None or key == self.last:
            return
        self.last = key
        try:
            self.impl.update(title, artist, art_url, playing, active)
        except Exception:
            log_error(traceback.format_exc())

    def close(self):
        if self.impl is not None:
            try:
                self.impl.close()
            except Exception:
                pass
