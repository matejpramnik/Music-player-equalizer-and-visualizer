import pygame as pg
import pygame_gui
import easygui
import os
from tinytag import TinyTag
from Pramník_app import State, App

class Panel():
    def __init__(self, rect: pg.Rect, manager: pygame_gui.UIManager):
        self.rect = rect
        self.surface = pg.Surface((self.rect.width, self.rect.height), pg.SRCALPHA)
        self.manager = manager
        self.panel = pygame_gui.elements.UIPanel(
            relative_rect=rect,
            manager=self.manager,
            starting_height=1,
            object_id=pygame_gui.core.ObjectID(class_id="@main_panels"))

    def handle_event(self, event, app):
        pass

    def open_directory(self) -> str:
        """
        Opens a file explorer and lets the user choose a folder. Returns an absolute path to it.
        """
        path = easygui.diropenbox("Choose a folder containing your audio", default=".")
        return path
    
    def scan_directory(self, path: str) -> list:
        """
        Scans a directory and returns a list of all files in it.

        :param path: Path to the directory.
        :type path: string 
        """
        retarr = []
        if path == None: return retarr
        with os.scandir(path) as ents:
            for e in ents:
                if e.is_dir() or e.is_symlink():
                    continue
                else:
                    retarr.append(e.path)
        return retarr
    
    def open_file(self) -> str:
        """
        Opens a file explorer and lets the user choose a file. Returns an absolute path to it.
        """
        path = easygui.fileopenbox("Choose an audio file to add to your queue",
                                   filetypes=[["*.wav", "*.mp3", "*.flac", "*.ogg", "*.aac", "*.3gp", "*.webm", "Audio files"]],
                                   multiple=True,
                                   default="*.wav")
        if path == None: return []
        return path
    
    # kvoli resize:
    def redraw(self, width: int, height: int) -> None:
        """
        Updates the Rect, Panel and Surface of a panel to specified dimensions.\n
        Rebuilds the UI elements

        :param width: New width, in pixels.
        :param height: New height, in pixels.
        :type width: integer
        :type height: integer
        """
        self.rect.update(self.rect.left, self.rect.top, width, height)
        self.surface = pg.Surface((self.rect.width, self.rect.height), pg.SRCALPHA)
        self.panel.kill()
        self.panel = pygame_gui.elements.UIPanel(
            relative_rect=self.rect,
            manager=self.manager,
            starting_height=1,
            object_id=pygame_gui.core.ObjectID(class_id="@main_panels"))


class MusicControlPanel(Panel):
    def __init__(self,
                 rect: pg.Rect,
                 manager,
                 freqs: dict,
                 queue: list,
                 volume: float,
                 theme: int,
                 shuffle: bool,
                 repeat_one: bool,
                 repeat_queue: bool):
        super().__init__(rect, manager)
        # config:
        self.queue = queue
        self.freqs = freqs
        self.theme = theme # 0=dark, 1=light
        self.shuffle = shuffle
        self.repeat_one = repeat_one
        self.repeat_queue = repeat_queue
        self.volume = volume

        self.currently_played_queue_index = 0
        self.last_volume = volume
        self.playing_SongItem = None
        
        self.supported_extensions = [".wav", ".mp3", ".mp2", ".flac", ".ogg", ".aac", ".m4a", ".3gp", ".aiff", ".wv"]
        self.build_ui()

    def redraw(self, width, height):
        super().redraw(width, height)
        self.build_ui()

    def build_ui(self) -> None:
        """
        Builds all of the UI elements.
        """
        
        self.play_stop_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#play_button")
        )

        self.next_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(40, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#next_button")
        )

        self.previous_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(-40, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#previous_button")
        )

        self.shuffle_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(80, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#shuffle_enabled_button" if self.shuffle else "#shuffle_disabled_button")
        )

        self.repeat_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(120, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                object_id="#repeat_one_button" if self.repeat_one else "#repeat_enabled_button" if self.repeat_queue else "#repeat_disabled_button")
        )
       
        self.volume_slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pg.Rect(-130, self.surface.get_height() - 60, 120, 20),
            manager=self.manager,
            container=self.panel,
            start_value=self.volume,
            value_range=(0, 1),
            click_increment=0.01,
            anchors={"centerx": "centerx"},
            object_id="#volume_slider"
        )

        self.volume_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(-210, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#volume_button")
        )

        self.song_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, self.play_stop_btn.rect.top - 150, -1, -1),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#huge_label")
        )

        self.file_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, self.song_name_label.rect.bottom, -1, -1),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#normal_label")
        )

        self.artist_album_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, self.file_name_label.rect.bottom, -1, -1),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#big_label")
        )

        self.file_progress = Slider(
            relative_rect=pg.Rect(0, self.artist_album_label.rect.bottom + 20, 320, 25),
            container=self.panel,
            manager=self.manager,
            # ak by value_range bola iba (0, 100), tak sa cas updatol raz za 3 sekundy (zaokruhlovanie)
            value_range=(0, 10000),
            click_increment=5,
            start_value=0,
            anchors={"centerx": "centerx"},
            object_id="#audio_file_progress_slider"
        )

        self.time_progress_label = TimeProgressUILabel(
            relative_rect=pg.Rect(self.file_progress.rect.left - 120, self.artist_album_label.rect.bottom + 20, 120, 25),
            container=self.panel,
            manager=self.manager
        )

        self.queue_panel = pygame_gui.elements.UIScrollingContainer(
            relative_rect=pg.Rect(65, 20, self.surface.get_width() - 70, self.surface.get_height() - 320),
            manager=self.manager,
            allow_scroll_y=True,
            allow_scroll_x=False,
            should_grow_automatically=True,
            container=self.panel,
            starting_height=1
        )
        if len(self.queue) > 0:
            self.set_queue(self.queue)

#################################################################################
# Burger menu
        self.burger_menu_btn = pygame_gui.elements.UIButton(
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#burger_menu_button"),
            relative_rect=pg.Rect(12, 12, 40, 40),
            text="",
            manager=self.manager,
            starting_height=11,
            container=self.panel
        )

        self.burger_menu_panel = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(0, 0, 380, 420),
            manager=self.manager,
            starting_height=10,
            object_id="#burger_menu_panel",
            container=self.panel
        )
        self.burger_menu_panel.hide()

        self.open_dir_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, 12, self.burger_menu_panel.rect.width - 80, 60),
            text="Open directory",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#open_dir_choice")
        )

        self.add_dir_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.open_dir_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Add directory to queue",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#add_dir_choice")
        )

        self.open_file_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.add_dir_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Add file to queue",
            manager=self.manager, 
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#open_file_choice")
        )

        self.toggle_eq_panel_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.open_file_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Equalizer",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#eq_choice")
        )

        self.change_vis_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.toggle_eq_panel_btn.rect.bottom, self.burger_menu_panel.rect.width - 75, 60),
            text="Change visualization",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#change_vis_choice")
        )

        self.switch_theme_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.change_vis_btn.rect.bottom, self.burger_menu_panel.rect.width - 75, 60),
            text="Switch theme",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#switch_theme_choice")
        )
#################################################################################

        self.eq_panel = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(20, 0, self.surface.get_width() - 20, self.surface.get_height() - 250),
            manager=self.manager,
            container=self.panel,
            starting_height=5,
            object_id=pygame_gui.core.ObjectID(class_id="@main_panels",
                                               object_id="#eq_panel")
        )
        self.eq_panel.hide()

        self.eq_cross_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(40, 12, 40, 40),
            text="",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#cross_button")
        )

        y = 12
        for freq, gain in self.freqs.items():
            EqualizerSliderPanel(rect=pg.Rect(-30, y, 420, 50),
                                 manager=self.manager,
                                 container=self.eq_panel,
                                 frequency=freq,
                                 start_value=gain,
                                 anchors={"centerx": "centerx"},
                                 object_id="#eq_slider_panel")
            y += 50

    def set_queue(self, new_queue: list) -> bool:
        """
        Creates a new UIScrollingContainer and SongItem elements in it.\n
        Returns True if at least one element was added, else False.

        :param new_queue: A list of paths to audio files.
        :type new_queue: list
        """
        if len(new_queue) == 0: return False
        self.queue_panel.kill()
        
        self.queue_panel = pygame_gui.elements.UIScrollingContainer(
            relative_rect=pg.Rect(65, 20, self.surface.get_width() - 70, self.surface.get_height() - 320),
            manager=self.manager,
            allow_scroll_y=True,
            allow_scroll_x=False,
            should_grow_automatically=True,
            container=self.panel,
            starting_height=1
        )
        q = []
        y = -3
        for song in new_queue: 
            _, ext = os.path.splitext(song)
            if ext in self.supported_extensions and os.path.exists(song): # ak je unreachable, trva dlhsie kym to OS zisti
                tag = TinyTag.get(song)
                SongItem(rect=pg.Rect(0, y + 3, self.surface.get_width() - 90, 85),
                        manager=self.manager,
                        song_name=f"{tag.title}",
                        artist=f"{tag.artist}",
                        album=f"{tag.album}",
                        container=self.queue_panel,
                        object_id="#SongItem_panel",
                        file_path=song,
                        icon_path="icons/cd.png")
                y += 87
                q.append(song)
        self.queue = q.copy()
        return True

    def add_to_queue(self, new_queue: list) -> bool:
        """
        Adds SongItem elements to an existing UIScrollingContainer.\n
        Returns True if at least one element was added, else False.

        :param new_queue: A list of paths to audio files.
        :type new_queue: list
        """
        if len(new_queue) == 0: return False

        for song in new_queue:
            y = 87 * len(self.queue)
            _, ext = os.path.splitext(song)
            if ext in self.supported_extensions:
                tag = TinyTag.get(song)
                self.queue_panel.get_container().add_element(
                    SongItem(rect=pg.Rect(0, y, self.surface.get_width() - 90, 85),
                            manager=self.manager,
                            song_name=f"{tag.title}",
                            artist=f"{tag.artist}",
                            album=f"{tag.album}",
                            container=self.queue_panel,
                            object_id="#SongItem_panel",
                            file_path=song,
                            icon_path="icons/cd.png"))
                self.queue.append(song)
            y += 87
        self.queue_panel.update_containing_rect_position()
        return True

    def mark_played(self) -> None:
        """
        Changes specific elements based on the currently played audio file.\n
        Elements affected:
            - SongItem which is currently being played.
            - Labels displaying currently played audio file tags.
        """
        if self.playing_SongItem is not None:
            self.playing_SongItem.change_object_id(pygame_gui.core.ObjectID(object_id="#SongItem_panel"))
        for si in self.queue_panel.get_container().elements:
            if type(si) is SongItem and self.queue[self.currently_played_queue_index] == si.file_path:
                si.change_object_id(pygame_gui.core.ObjectID(object_id="#playing_SongItem_panel"))
                self.playing_SongItem = si
                self.song_name_label.set_text(si.song_name)
                self.file_name_label.set_text(os.path.basename(si.file_path))
                self.artist_album_label.set_text(f"{si.artist} {si.album}")
                break
    
    def update_ui(self, state: State, file_pos_s: float, file_length_s: float) -> None:
        """
        Updates UI elements based on audio file playback, expected to be called once per frame.\n
        Elements affected:
            - "Next" and "Previous" buttons.
            - "Volume"/"Mute" button.
            - File progress slider.
            - Currently played audio file tag labels.

        :param state: Application state.
        :param file_pos_s: Number of seconds the audio file has already been played for.
        :param file_length_s: File length, in seconds.
        :type state: State (Enum)
        :type file_pos_s: float
        :type file_length_s: float
        """
        if self.currently_played_queue_index == len(self.queue) - 1 and self.next_btn.visible:
            self.next_btn.hide()
        elif self.currently_played_queue_index < len(self.queue) - 1 and not self.next_btn.visible:
            self.next_btn.show()

        if self.currently_played_queue_index == 0 and self.previous_btn.visible:
            self.previous_btn.hide()
        elif self.currently_played_queue_index > 0 and not self.previous_btn.visible:
            self.previous_btn.show()

        if self.volume == 0.0 and "#mute_button" not in self.volume_btn.get_object_ids():
            self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                      object_id="#mute_button"))
        elif self.volume > 0.0 and "#mute_button" in self.volume_btn.get_object_ids():
            self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                      object_id="#volume_button"))
        # faktor 10000 kvoli zaokruhlovacej chybe, pozri self.file_progress
        if state.name == "PLAYING":
            wiper_val = (file_pos_s / file_length_s) * 10000
            if wiper_val >= 10000: wiper_val = 10000
            self.file_progress.wiper.set_current_value(wiper_val)
        if state.name == "PLAYING" or state.name == "PAUSED":
            pos = self.file_progress.wiper.get_current_value()
            self.time_progress_label.update_time_label(file_length_s, (file_length_s / 10000) * pos)

        if state.name == "PLAYING" and "#play_button" in self.play_stop_btn.get_object_ids():
            self.play_stop_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                       object_id="#pause_button"))
        elif not state.name == "PLAYING" and "#pause_button" in self.play_stop_btn.get_object_ids():
            self.play_stop_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                       object_id="#play_button"))
        
        # podla stavu skryjem tlacitka co by sa nemali stlacat:
        if not self.file_name_label.visible:
            self.next_btn.show()
            self.previous_btn.show()
            self.file_name_label.show()
            self.song_name_label.show()
            self.artist_album_label.show()

        if state.name == "DATA_LOADING":
            self.play_stop_btn.hide()
            self.file_progress.hide()
            self.time_progress_label.hide()
        elif (state.name == "PLAYING" or state.name == "PAUSED") and not self.play_stop_btn.visible:
            self.play_stop_btn.show()
            self.file_progress.show()
            self.time_progress_label.show()
        elif state.name == "INITIAL":
            self.play_stop_btn.hide()
            self.file_progress.hide()
            self.time_progress_label.hide()
            self.next_btn.hide()
            self.previous_btn.hide()
            self.file_name_label.hide()
            self.song_name_label.hide()
            self.artist_album_label.hide()

    def handle_event(self, event: pg.Event, app: App):
        """
        Handles events passed on by the main Event loop of the Application.\n
        Handles only the UI changes, calls the main App's methods for logic changes.

        :param event: An event for handling.
        :param app: An application that called this method.
        :type event: pygame.Event
        :type app: App
        """
        super().handle_event(event, app)
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.change_vis_btn:
                app.cycle_vis_type()

            elif event.ui_element == self.play_stop_btn:
                app.play_pause()
                
            elif event.ui_element == self.eq_cross_btn:
                self.eq_panel.hide()
                self.queue_panel.show()

            elif event.ui_element == self.volume_btn:
                if "#volume_button" in self.volume_btn.object_ids:
                    self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#mute_button"))
                    self.last_volume = self.volume
                    app.change_volume(0)
                elif "#mute_button" in self.volume_btn.object_ids and self.volume > 0.0:
                    self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#volume_button"))
                    self.volume = self.last_volume
                    app.change_volume(self.volume)

            elif event.ui_element == self.shuffle_btn:
                if "#shuffle_disabled_button" in self.shuffle_btn.object_ids:
                    self.shuffle_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#shuffle_enabled_button"))
                    app.change_queue_behaviour(shuffle=1)
                elif "#shuffle_enabled_button" in self.shuffle_btn.object_ids:
                    self.shuffle_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#shuffle_disabled_button"))
                    app.change_queue_behaviour(shuffle=0)
                    
            elif event.ui_element == self.repeat_btn:
                if "#repeat_disabled_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_enabled_button"))
                    app.change_queue_behaviour(repeat=2)
                elif "#repeat_enabled_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_one_button"))
                    app.change_queue_behaviour(repeat=1)
                elif "#repeat_one_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_disabled_button"))
                    app.change_queue_behaviour(repeat=0)

            elif event.ui_element == self.next_btn:
                if len(self.queue) > 1:
                    app.continue_in_queue(clicked_next=True)
                
            elif event.ui_element == self.previous_btn:
                if len(self.queue) > 1:
                    app.continue_in_queue(clicked_back=True)

            elif event.ui_element == self.burger_menu_btn:
                if self.burger_menu_panel.visible:
                    self.burger_menu_panel.hide()
                else:
                    self.burger_menu_panel.show()

            elif event.ui_element == self.open_dir_btn:
                # zasekne sa ui pri vacsich priecinkoch; pygame_gui nie je thread safe
                path = self.open_directory()
                files = self.scan_directory(path)
                status = self.set_queue(files)
                if status:
                    app.queue_changed(files)
                self.burger_menu_panel.hide()
                self.eq_panel.hide()

            elif event.ui_element == self.open_file_btn:
                path = self.open_file()
                status = self.add_to_queue(path)
                if status:
                    app.queue_changed(path, added=True)
                self.burger_menu_panel.hide()

            elif event.ui_element == self.add_dir_btn:
                # zasekne sa ui pri vacsich priecinkoch, lebo pygame_gui nie je thread safe
                path = self.open_directory()
                files = self.scan_directory(path)
                status = self.add_to_queue(files)
                if status:
                    app.queue_changed(files, added=True)
                self.burger_menu_panel.hide()
                self.eq_panel.hide()

            elif event.ui_element == self.toggle_eq_panel_btn:
                self.burger_menu_panel.hide()
                if self.eq_panel.visible == 1:
                    self.eq_panel.hide()
                    self.queue_panel.show()
                else:
                    self.queue_panel.hide()
                    self.eq_panel.show()

            elif event.ui_element == self.switch_theme_btn:
                self.theme = 1 - self.theme
                self.burger_menu_panel.hide()
                app.switch_theme()

            elif "#reset_single_button" in event.ui_element.object_ids:
                event.ui_element.parent_element.slider.set_current_value(0)
                freq = event.ui_element.parent_element.frequency
                app.change_eq(freq, 0)

            elif type(event.ui_element) is TransparentUIButton:
                path = event.ui_element.path
                self.currently_played_queue_index = self.queue.index(path)
                try:
                    self.mark_played()
                    app.change_song(path, clicked=True)
                except:
                    raise NameError

        elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
            if "#eq_slider" in event.ui_element.object_ids:
                freq = event.ui_element.parent_element.frequency
                value = event.value
                app.change_eq(freq, value)
                # toto neviem ci tu este treba:
                self.freqs[freq] = value

            elif "#volume_slider" in event.ui_element.object_ids:
                value = event.value
                self.volume = value
                app.change_volume(value)

            elif "#audio_file_progress_slider" in event.ui_element.object_ids:
                value = event.value / 100
                app.set_player_position(value)

        elif event.type == pg.MOUSEBUTTONDOWN:
            if not self.burger_menu_panel.rect.collidepoint(event.pos):
                self.burger_menu_panel.hide()


class VisPanel(Panel):
    def __init__(self, rect, manager):
        super().__init__(rect, manager)
        
    def handle_event(self, event, app):
        super().handle_event(event, app)


class SongItem(pygame_gui.elements.UIPanel):
    def __init__(self, rect, manager,
                 song_name: str,
                 artist: str,
                 album: str,
                 container: pygame_gui.core.UIContainer,
                 object_id: pygame_gui.core.ObjectID,
                 file_path: str,
                 icon_path: str | None = None):
        super().__init__(relative_rect=rect, manager=manager, container=container, object_id=object_id)
        self.file_path = file_path
        self.song_name = song_name if song_name != "None" else "--"
        self.artist = artist if artist != "None" else ""
        self.album = f"- {album}" if album != "None" else ""
        self.build_ui(rect, manager, file_path, icon_path)


    def build_ui(self, rect, manager, file_path, icon_path):
        """
        Builds all of the UI elements.
        """
        # obrazok (basic ikona)
        if icon_path:
            try:
                image_surface = pg.image.load(icon_path).convert_alpha()
                image_surface = pg.transform.smoothscale(image_surface, (48, 48))
            except:
                image_surface = None
        else:
            image_surface = None

        if image_surface:
            self.icon = pygame_gui.elements.UIImage(
                relative_rect=pg.Rect(5, 0, 48, 48),
                image_surface=image_surface,
                manager=manager,
                container=self,
                anchors={"centery": "centery"}
            )
        else:
            self.icon = None

        # tento button bude transparentny, takze vyrobim kliknutelny panel
        self.click_area = TransparentUIButton(
            relative_rect=pg.Rect(-1, -1, rect.width + 2, rect.height + 2),
            text="",
            manager=manager,
            container=self,
            starting_height=2,
            object_id="#transparent_button",
            path = file_path
        )

        self.options_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(rect.width - 40, 0, 40, 40),
            manager=manager,
            text="",
            container=self,
            starting_height=3,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#options_button")
        )

        text_x = 60
        self.song_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(text_x, 10, -1, 25),
            text=self.song_name,
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#big_label")
        )

        self.file_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(text_x, 32, -1, 22),
            text=os.path.basename(file_path),
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#normal_label")
        )

        self.artist_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(text_x, 56, -1, 22),
            text=self.artist,
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#normal_label")
        )

        self.album_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(self.artist_label.relative_rect.right + 4, 56, -1, 22),
            text=self.album,
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#normal_label")
        )


class TransparentUIButton(pygame_gui.elements.UIButton):
    def __init__(self, relative_rect, text, manager, container, starting_height, object_id, path):
        super().__init__(relative_rect=relative_rect,
                         text=text,
                         manager=manager,
                         container=container,
                         starting_height=starting_height,
                         object_id=object_id)
        self.path = path
        

class EqualizerSliderPanel(pygame_gui.elements.UIPanel):
    def __init__(self, rect, manager,
                 container: pygame_gui.core.UIContainer,
                 object_id: pygame_gui.core.ObjectID,
                 start_value: int,
                 anchors,
                 frequency: int):
        super().__init__(relative_rect=rect, manager=manager, container=container, object_id=object_id, anchors=anchors)
        self.frequency = frequency
        self.build_ui(rect, manager, start_value)
        self.current_value = self.slider.get_current_value()

    def build_ui(self, rect, manager, start_value):
        """
        Builds all of the UI elements.
        """
        self.slider = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pg.Rect(80, 0, rect.width - 110, 20),
            value_range=(-120, 120),
            start_value=start_value,
            container=self,
            parent_element=self,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(object_id="#eq_slider"),
            manager=manager,
            click_increment=5
        )

        self.label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, 0, 70, 25),
            manager=manager,
            container=self,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(object_id="#eq_label"),
            text=str(self.frequency) + "Hz"
        )

        self.reset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(rect.width - 30, 0, 30, 30),
            manager=manager,
            container=self,
            parent_element=self,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(object_id="#reset_single_button"),
            text=""
        )

        x = self.slider.get_relative_rect().left - 6
        gains = [-12, -8, -4, 0, 4, 8, 12]
        for i in range(7):
            pygame_gui.elements.UILabel(
                relative_rect=pg.Rect(x, rect.height - 15, 32, 20),
                manager=manager,
                container=self,
                object_id=pygame_gui.core.ObjectID(object_id="#gain_label"),
                text=("-" + str(abs(gains[i]))) if gains[i] < 0 else ("+" + str(gains[i])) if gains[i] > 0 else "  " + str(gains[i])
            )
            x += self.slider.rect.width / 6.6


class Slider(pygame_gui.elements.UIPanel):
    def __init__(self,
                 relative_rect: pg.Rect,
                 container: pygame_gui.core.UIContainer,
                 object_id: pygame_gui.core.ObjectID,
                 manager,
                 anchors,
                 starting_height: int = 1,
                 value_range: tuple = (0, 1),
                 start_value: float | int = 0,
                 click_increment: int = 1):
        super().__init__(relative_rect=relative_rect,
                         starting_height=starting_height,
                         manager=manager,
                         container=container,
                         object_id=object_id,
                         anchors=anchors)
        self.build_ui(relative_rect, manager, value_range, start_value, click_increment)
        self.current_value = self.wiper.get_current_value()

    def build_ui(self, rect, manager, value_range, start_value, click_increment):
        """
        Builds all of the UI elements.
        """
        self.wiper = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pg.Rect(0, 0, rect.width, rect.height),
            start_value=start_value,
            value_range=value_range,
            container=self,
            parent_element=self,
            manager=manager,
            click_increment=click_increment,
            object_id="#slider_wiper",
        )

        self.line = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(2, rect.height // 2 - 1, rect.width - 2, 4),
            manager=manager,
            container=self,
            object_id="#slider_line"
        )


class TimeProgressUILabel(pygame_gui.elements.UIPanel):
    def __init__(self, relative_rect, manager, container, anchors={}, starting_height=1):
        super().__init__(relative_rect=relative_rect,
                         manager=manager,
                         container=container,
                         starting_height=starting_height,
                         anchors=anchors,
                         object_id=pygame_gui.core.ObjectID(class_id="@main_panels"))
        self.build_ui(relative_rect, manager)

    def build_ui(self, relative_rect, manager):
        """
        Builds all of the UI elements.
        """
        
        self.time_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, 0, relative_rect.width, relative_rect.height),
            text="",
            manager=manager,
            container=self,
            object_id="#eq_label"
        )

    def update_time_label(self, full_time_s: float, playing_time_s: float):
        """
        Updates the displayed time.

        :param full_time_s: Full time, in seconds.
        :param playing_time_s: Time the songs has been playing for, in seconds.
        :type full_time_s: float
        :type playing_time_s: float
        """
        self.full_time_s = full_time_s
        self.full_minutes = int(full_time_s / 60)
        self.full_seconds = round(full_time_s % 60)

        self.playing_time_s = playing_time_s
        self.playing_minutes = int(self.playing_time_s / 60)
        self.playing_seconds = round(self.playing_time_s % 60)

        text = f"{self.playing_minutes}:{self.playing_seconds:02d} / {self.full_minutes}:{self.full_seconds:02d}"
        self.time_label.set_text(text)
