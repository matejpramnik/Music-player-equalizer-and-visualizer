import pygame as pg
import pygame_gui
import easygui
import os
from tinytag import TinyTag, Image
from io import BytesIO
from Pramník_app import State, App

class Panel():
    def __init__(self, rect: pg.Rect, manager: pygame_gui.UIManager):
        self.supported_extensions = [".wav", ".mp3", ".mp2", ".flac", ".ogg", ".aac", ".m4a", ".3gp", ".aiff", ".wv"]
        self.rect = rect
        self.surface = pg.Surface((self.rect.width, self.rect.height), pg.SRCALPHA)
        self.manager = manager
        self.panel = pygame_gui.elements.UIPanel(
            relative_rect=rect,
            manager=self.manager,
            starting_height=1,
            object_id=pygame_gui.core.ObjectID(class_id="@main_panels"))

    def build_ui(self) -> None:
        """
        Builds all of the UI elements.
        """
        pass

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
        Scans a directory and returns a list of all files in it. Will return the last image found in a directory.

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
                    _, ext = os.path.splitext(e)
                    if ext in self.supported_extensions:
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
    
    # resize "handler"
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
                 orig_queue: list,
                 volume: float,
                 theme: int,
                 shuffle: bool,
                 repeat_one: bool,
                 repeat_queue: bool):
        super().__init__(rect, manager)
        # config:
        self.queue = orig_queue
        self.freqs = freqs
        self.theme = theme # 0=dark, 1=light
        self.shuffle = shuffle
        self.repeat_one = repeat_one
        self.repeat_queue = repeat_queue
        self.volume = volume

        self.currently_played_queue_index = 0
        self.last_volume = volume
        self.playing_SongItem = None
        
        self.build_ui(orig_queue)

    def redraw(self, width, height, queue):
        super().redraw(width, height)
        self.build_ui(queue)

    def build_ui(self, queue: list) -> None:
        """
        Builds the GUI.

        :param queue: The queue to display
        :type queue: list
        """
        
        self.play_stop_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.surface.get_height() - 80, 60, 60),
            text="",
            manager=self.manager,
            container=self.panel.get_container(),
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#play_button")
        )

        self.next_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(55, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#next_button")
        )

        self.previous_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(-55, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#previous_button")
        )

        self.shuffle_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(160, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#shuffle_enabled_button" if self.shuffle else "#shuffle_disabled_button")
        )

        self.repeat_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(215, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                object_id="#repeat_one_button" if self.repeat_one else "#repeat_enabled_button" if self.repeat_queue else "#repeat_disabled_button")
        )
       
        self.volume_slider = Slider(
            relative_rect=pg.Rect(-180, self.surface.get_height() - 60, 85, 20),
            manager=self.manager,
            container=self.panel,
            start_value=self.volume,
            value_range=(0, 1),
            click_increment=0.01,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(object_id="#volume_slider",
                                               class_id="@sliders")
        )

        self.volume_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(-240, self.surface.get_height() - 70, 40, 40),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
                                               object_id="#volume_button")
        )

        self.song_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, self.play_stop_btn.rect.top - 125, -1, -1),
            text="",
            manager=self.manager,
            container=self.panel,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#huge_label")
        )

        self.artist_album_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, self.song_name_label.rect.bottom + 10, -1, -1),
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
            object_id=pygame_gui.core.ObjectID(object_id="#audio_file_progress_slider",
                                               class_id="@sliders")
        )

        self.time_progress_label = TimeUILabel(
            relative_rect=pg.Rect(-200, self.artist_album_label.rect.bottom + 20, 120, 25),
            container=self.panel,
            manager=self.manager,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(object_id="#normal_label")
        )

        self.full_time_label = TimeUILabel(
            relative_rect=pg.Rect(200, self.artist_album_label.rect.bottom + 20, 120, 25),
            container=self.panel,
            manager=self.manager,
            anchors={"centerx": "centerx"},
            object_id=pygame_gui.core.ObjectID(object_id="#normal_label")
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
        if len(queue) > 0:
            self.set_queue(queue)

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
            relative_rect=pg.Rect(0, 0, 390, 480),
            manager=self.manager,
            starting_height=10,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_panels",
                                               object_id="#burger_menu_panel"),
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
            text="Add files to queue",
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
            relative_rect=pg.Rect(70, self.toggle_eq_panel_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Change visualization",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#change_vis_choice")
        )

        self.switch_theme_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(70, self.change_vis_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Switch theme",
            manager=self.manager,
            container=self.burger_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#switch_theme_choice")
        )

    # window size menu
        self.window_size_menu_btn = pygame_gui.elements.UIButton(
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#window_size_menu_choice"),
            relative_rect=pg.Rect(70, self.switch_theme_btn.rect.bottom, self.burger_menu_panel.rect.width - 80, 60),
            text="Window size",
            manager=self.manager,
            container=self.burger_menu_panel
        )

        self.window_size_menu_panel = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(self.burger_menu_panel.rect.right, self.window_size_menu_btn.rect.top, 200, 190),
            manager=self.manager,
            starting_height=10,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_panels",
                                               object_id="#window_size_menu_panel"),
            container=self.panel
        )
        self.window_size_menu_panel.hide()

        self.small_window_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(10, 12, self.window_size_menu_panel.rect.width - 25, 50),
            text="Small",
            manager=self.manager,
            container=self.window_size_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#small_win_choice")
        )

        self.medium_window_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(10,
                                  self.small_window_btn.get_relative_rect().bottom + 5,
                                  self.window_size_menu_panel.rect.width - 25,
                                  50),
            text="Medium",
            manager=self.manager,
            container=self.window_size_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#med_win_choice")
        )

        self.large_window_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(10,
                                  self.medium_window_btn.get_relative_rect().bottom + 5,
                                  self.window_size_menu_panel.rect.width - 25,
                                  50),
            text="Large",
            manager=self.manager,
            container=self.window_size_menu_panel,
            object_id=pygame_gui.core.ObjectID(class_id="@menu_choice_buttons",
                                               object_id="#large_win_choice")
        )
#################################################################################

#################################################################################
# equalizer panel
        self.eq_panel = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(15, 0, self.surface.get_width() - 20, self.surface.get_height() - 230), #width 630
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

        self.flat_preset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, 115, 75, 40),
            text="Flat",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@text_buttons")
        )

        self.v_shape_preset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.flat_preset_btn.rect.bottom + 20, 75, 40),
            text="V-shape",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@text_buttons")
        )

        self.clarity_preset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.v_shape_preset_btn.rect.bottom + 20, 75, 40),
            text="Clarity",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@text_buttons")
        )

        self.bass_preset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.clarity_preset_btn.rect.bottom + 20, 75, 40),
            text="Bass",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@text_buttons")
        )

        self.vocal_preset_btn = pygame_gui.elements.UIButton(
            relative_rect=pg.Rect(0, self.bass_preset_btn.rect.bottom + 20, 75, 40),
            text="Vocals",
            manager=self.manager,
            container=self.eq_panel,
            starting_height=2,
            object_id=pygame_gui.core.ObjectID(class_id="@text_buttons")
        )

        self.eq_sliders = []
        # vert: 52px width na jeden
        y = 5
        for freq, gain in self.freqs.items():
            slider_panel = EqualizerSliderPanel(
                rect=pg.Rect(-30, y, 420, 50),
                manager=self.manager,
                container=self.eq_panel,
                frequency=freq,
                start_value=gain,
                anchors={"centerx": "centerx"},
                object_id="#eq_slider_panel")
            self.eq_sliders.append(slider_panel)
            y += 50
#################################################################################

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
        y = 0
        for song in new_queue:
            if os.path.exists(song): # ak je unreachable, trva dlhsie kym to OS zisti
                tag = TinyTag.get(song, image=True)
                image: Image | None = tag.images.any
                SongItem(rect=pg.Rect(0, y, self.surface.get_width() - 90, 85),
                    manager=self.manager,
                    song_name=f"{tag.title}",
                    artist=f"{tag.artist}",
                    album=f"{tag.album}",
                    container=self.queue_panel.get_container(),
                    object_id="#SongItem_panel",
                    file_path=song,
                    image=image)
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
        y = 87 * len(self.queue)
        for song in new_queue:
            if song not in self.queue:
                tag = TinyTag.get(song, image=True)
                image: Image | None = tag.images.any
                SongItem(rect=pg.Rect(0, y, self.surface.get_width() - 90, 85),
                        manager=self.manager,
                        song_name=f"{tag.title}",
                        artist=f"{tag.artist}",
                        album=f"{tag.album}",
                        container=self.queue_panel.get_container(),
                        object_id="#SongItem_panel",
                        file_path=song,
                        image=image)
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

        # next/previous button hide/show
        #   big mess
        index = self.currently_played_queue_index
        rep_queue = self.repeat_queue
        rep_one = self.repeat_one
        q_len = len(self.queue)
        state_name = state.name
        if index == q_len - 1 and self.next_btn.visible and not rep_queue and not rep_one:
            self.next_btn.hide()
        elif (index < q_len - 1 or rep_queue or rep_one) and not self.next_btn.visible and q_len != 1:
            self.next_btn.show()
        if index == 0 and self.previous_btn.visible and not rep_queue and not rep_one:
            self.previous_btn.hide()
        elif (index > 0 or rep_queue or rep_one) and not self.previous_btn.visible and q_len != 1:
            self.previous_btn.show()

        # speaker/mute
        if self.volume == 0.0 and "#volume_button" in self.volume_btn.get_object_ids():
            self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                      object_id="#mute_button"))
        elif self.volume > 0.0 and "#mute_button" in self.volume_btn.get_object_ids():
            self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                      object_id="#volume_button"))
        
        # file progress
        # factor 10000 because of rounding error, see self.file_progress
        if state_name == "PLAYING":
            wiper_val = (file_pos_s / file_length_s) * 10000
            if wiper_val >= 10000: wiper_val = 10000
            self.file_progress.set_current_value(wiper_val)
        if state_name == "PLAYING" or state_name == "PAUSED":
            pos = self.file_progress.get_current_value()
            self.time_progress_label.update_time((file_length_s / 10000) * pos)
            self.full_time_label.update_time(file_length_s)

        if state_name == "PLAYING" and "#play_button" in self.play_stop_btn.get_object_ids():
            self.play_stop_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                       object_id="#pause_button"))
        elif not state_name == "PLAYING" and "#pause_button" in self.play_stop_btn.get_object_ids():
            self.play_stop_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                       object_id="#play_button"))
        
        # hiding buttons that would do nothing; based on the app state
        if not self.song_name_label.visible:
            self.next_btn.show()
            self.previous_btn.show()
            self.song_name_label.show()
            self.artist_album_label.show()

        if state_name == "DATA_LOADING":
            self.play_stop_btn.hide()
            self.file_progress.hide()
            self.time_progress_label.hide()
            self.full_time_label.hide()
        elif (state_name == "PLAYING" or state_name == "PAUSED") and not self.play_stop_btn.visible:
            self.play_stop_btn.show()
            self.file_progress.show()
            self.time_progress_label.show()
            self.full_time_label.show()
        elif state_name == "INITIAL":
            self.play_stop_btn.hide()
            self.file_progress.hide()
            self.time_progress_label.hide()
            self.full_time_label.hide()
            self.next_btn.hide()
            self.previous_btn.hide()
            self.song_name_label.hide()
            self.artist_album_label.hide()
            if self.playing_SongItem is not None:
                self.playing_SongItem.change_object_id(pygame_gui.core.ObjectID(object_id="#SongItem_panel"))
                self.playing_SongItem = None

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
                    app.change_volume(0.0)
                    self.last_volume = self.volume
                    self.volume = 0.0
                    self.volume_slider.set_current_value(0.0)
                    self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#mute_button"))
                elif "#mute_button" in self.volume_btn.object_ids and self.last_volume > 0.0:
                    self.volume = self.last_volume
                    app.change_volume(self.volume)
                    self.volume_slider.set_current_value(self.volume)
                    self.volume_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#volume_button"))
                    
            elif event.ui_element == self.shuffle_btn:
                if "#shuffle_disabled_button" in self.shuffle_btn.object_ids:
                    self.shuffle_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#shuffle_enabled_button"))
                    app.change_queue_behaviour(shuffle=1)
                    self.shuffle = True
                elif "#shuffle_enabled_button" in self.shuffle_btn.object_ids:
                    self.shuffle_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#shuffle_disabled_button"))
                    app.change_queue_behaviour(shuffle=0)
                    self.shuffle = False
                    
            elif event.ui_element == self.repeat_btn:
                if "#repeat_disabled_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_enabled_button"))
                    app.change_queue_behaviour(repeat=2)
                    self.repeat_queue = True
                    self.repeat_one = False
                elif "#repeat_enabled_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_one_button"))
                    app.change_queue_behaviour(repeat=1)
                    self.repeat_queue = False
                    self.repeat_one = True
                elif "#repeat_one_button" in self.repeat_btn.object_ids:
                    self.repeat_btn.change_object_id(pygame_gui.core.ObjectID(class_id="@control_buttons",
                                                                            object_id="#repeat_disabled_button"))
                    app.change_queue_behaviour(repeat=0)
                    self.repeat_queue = False
                    self.repeat_one = False

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
            
            elif event.ui_element == self.window_size_menu_btn:
                if self.window_size_menu_panel.visible:
                    self.window_size_menu_panel.hide()
                else:
                    self.window_size_menu_panel.show()

            elif event.ui_element == self.open_dir_btn:
                # blocks ui, laggy when the directory is large; pygame_gui is not thread-safe
                path = self.open_directory()
                files = self.scan_directory(path)
                status = self.set_queue(files)
                if status:
                    app.queue_changed(files)
                self.burger_menu_panel.hide()
                self.eq_panel.hide()

            elif event.ui_element == self.open_file_btn:
                # blocks ui, laggy when many files are chosen; pygame_gui is not thread-safe
                path = self.open_file()
                status = self.add_to_queue(path)
                if status:
                    app.queue_changed(path, added=True)
                self.burger_menu_panel.hide()

            elif event.ui_element == self.add_dir_btn:
                # blocks ui, laggy when the directory is large; pygame_gui is not thread-safe
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

            elif event.ui_element == self.small_window_btn:
                app.change_window_size(1300, 790)
            
            elif event.ui_element == self.medium_window_btn:
                app.change_window_size(1600, 960)

            elif event.ui_element == self.large_window_btn:
                app.change_window_size(1920, 1020)

            elif event.ui_element == self.flat_preset_btn:
                # flat preset; every slider to 0 dB
                for eq_slider_panel in self.eq_sliders:
                    eq_slider_panel.slider.set_current_value(0)
                    app.change_eq(eq_slider_panel.frequency, 0)

            elif event.ui_element == self.v_shape_preset_btn:
                # standard V-shape eq preset; boosts bass and treble, ideal for rock and pop music
                gains = [80, 60, 40, 15, 5, 5, 15, 40, 60, 80]
                for i in range(10):
                    self.eq_sliders[i].slider.set_current_value(gains[i])
                    app.change_eq(self.eq_sliders[i].frequency, gains[i])
                    self.freqs[self.eq_sliders[i].frequency] = gains[i]

            elif event.ui_element == self.clarity_preset_btn:
                # creates an audible difference between highs and lows at the expense of vocals
                gains = [40, 30, 10, -20, -20, 0, 15, 20, 10, 10]
                for i in range(10):
                    self.eq_sliders[i].slider.set_current_value(gains[i])
                    app.change_eq(self.eq_sliders[i].frequency, gains[i])
                    self.freqs[self.eq_sliders[i].frequency] = gains[i]

            elif event.ui_element == self.bass_preset_btn:
                # boosts low frequencies; simulates a low-pass filter; balances it with a slight mid-high frequency boost
                gains = [80, 65, 30, 20, 0, -5, 5, 15, 10, 0]
                for i in range(10):
                    self.eq_sliders[i].slider.set_current_value(gains[i])
                    app.change_eq(self.eq_sliders[i].frequency, gains[i])
                    self.freqs[self.eq_sliders[i].frequency] = gains[i]

            elif event.ui_element == self.vocal_preset_btn:
                # boosts frequencies where vocals typically exist
                gains = [0, 0, 0, 20, 60, 70, 70, 60, 20, 0]
                for i in range(10):
                    self.eq_sliders[i].slider.set_current_value(gains[i])
                    app.change_eq(self.eq_sliders[i].frequency, gains[i])
                    self.freqs[self.eq_sliders[i].frequency] = gains[i]

            elif "#reset_single_button" in event.ui_element.object_ids:
                event.ui_element.parent_element.slider.set_current_value(0)
                freq = event.ui_element.parent_element.frequency
                app.change_eq(freq, 0)

            elif type(event.ui_element) is TransparentUIButton:
                path = event.ui_element.path
                self.currently_played_queue_index = self.queue.index(path)
                self.mark_played()
                app.change_song(path, clicked=True)

        elif event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED:
            if "#eq_slider" in event.ui_element.object_ids:
                # get EqualizerSliderPanel frequency
                freq = event.ui_element.parent_element.parent_element.frequency
                value = event.value
                # call Slider method set_current_value()
                event.ui_element.parent_element.set_current_value(value)
                app.change_eq(freq, value)
                self.freqs[freq] = value

            elif "#volume_slider" in event.ui_element.object_ids:
                value = event.value
                self.volume = value
                self.last_volume = value
                self.volume_slider.set_current_value(value)
                app.change_volume(value)

            elif "#audio_file_progress_slider" in event.ui_element.object_ids:
                value = event.value / 100
                event.ui_element.parent_element._set_line_length()
                app.set_player_position(value)

        elif event.type == pg.MOUSEBUTTONDOWN:
            window_panel_opened = self.window_size_menu_panel.visible
            burger_menu_opened = self.burger_menu_panel.visible

            if not window_panel_opened:
                if burger_menu_opened and not self.burger_menu_panel.rect.collidepoint(event.pos):
                    self.burger_menu_panel.hide()
            else:
                if not self.burger_menu_panel.rect.collidepoint(event.pos) and not self.window_size_menu_panel.rect.collidepoint(event.pos):
                    self.burger_menu_panel.hide()
                    self.window_size_menu_panel.hide()

    def handle_scrolling(self, event: pg.Event) -> None:
        """
        Handles the queue panel scrolling. Gets rid of the UIScrollingContainer's deceleration after scrolling.

        :param event: Pygame Event
        """
        # scroll position (pixels)
        current_y = -self.queue_panel.scrollable_container.relative_rect.y
        max_scroll = self.queue_panel.scrolling_height - self.queue_panel._view_container.rect.height

        new_y = max(0, min(current_y - event.y * 30, max_scroll))
        self.queue_panel.scrollable_container.set_relative_position(
            (self.queue_panel.scrollable_container.relative_rect.x, -new_y)
        )

        # scrollbar sync
        if self.queue_panel.scrolling_height > 0:
            self.queue_panel.vert_scroll_bar.set_scroll_from_start_percentage(
                new_y / self.queue_panel.scrolling_height
            )
            # stop the momentum
            self.queue_panel.vert_scroll_bar.rebuild()


class VisPanel(Panel):
    def __init__(self, rect, manager):
        super().__init__(rect, manager)


class SongItem(pygame_gui.elements.UIPanel):
    def __init__(self, rect, manager,
                 song_name: str,
                 artist: str,
                 album: str,
                 object_id: pygame_gui.core.ObjectID,
                 file_path: str,
                 container: pygame_gui.core.UIContainer | None=None,
                 image: Image | None = None):
        super().__init__(relative_rect=rect, manager=manager, container=container, object_id=object_id)
        self.file_path = file_path
        self.song_name = os.path.basename(file_path) if song_name == "None" else song_name
        self.artist = artist if artist != "None" else ""
        self.album = f"- {album}" if album != "None" else ""
        song_name_y = 32 if song_name == "None" else 19
        self.build_ui(rect, manager, file_path, image, song_name_y)


    def build_ui(self, rect, manager, file_path, image, song_name_y):
        """
        Builds all of the UI elements.
        """
        # album cover (if exists)
        if image is not None:
            image_data: bytes = image.data
            image_surface = pg.image.load(BytesIO(image_data))
            image_surface = pg.transform.smoothscale(image_surface, (64, 64))
        else:
            image_surface = pg.image.load("icons/cd.png")
            image_surface = pg.transform.smoothscale(image_surface, (64, 64))

        self.icon = pygame_gui.elements.UIImage(
            relative_rect=pg.Rect(16, 0, 64, 64),
            image_surface=image_surface,
            manager=manager,
            container=self,
            anchors={"centery": "centery"}
        )

        # transparent button the size of the entire panel; effectively a clickable panel
        self.click_area = TransparentUIButton(
            relative_rect=pg.Rect(-1, -1, rect.width + 2, rect.height + 2),
            text="",
            manager=manager,
            container=self,
            starting_height=2,
            object_id="#transparent_button",
            path = file_path
        )

        # self.options_btn = pygame_gui.elements.UIButton(
        #     relative_rect=pg.Rect(rect.width - 45, 0, 40, 40),
        #     manager=manager,
        #     text="",
        #     container=self,
        #     starting_height=3,
        #     anchors={"centery": "centery"},
        #     object_id=pygame_gui.core.ObjectID(class_id="@control_buttons",
        #                                        object_id="#options_button")
        # )

        text_x = 96
        self.song_name_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(text_x, song_name_y, -1, 25),
            text=self.song_name,
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#big_label")
        )

        self.artist_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(text_x, 45, -1, 22),
            text=self.artist,
            manager=manager,
            container=self,
            object_id=pygame_gui.core.ObjectID(class_id="@SongItem_labels",
                                               object_id="#normal_label")
        )

        self.album_label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(self.artist_label.relative_rect.right + 4, 45, -1, 22),
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

        self.slider = Slider(
            relative_rect=pg.Rect(80, -2, rect.width - 110, 24),
            value_range=(-120, 120),
            start_value=start_value,
            container=self,
            parent_element=self,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(object_id="#eq_slider",
                                               class_id="@sliders"),
            manager=manager,
            click_increment=5
        )

        freq = str(self.frequency) if self.frequency < 1000 else str(round(self.frequency / 1000, 1)) + "k"
        self.label = pygame_gui.elements.UILabel(
            relative_rect=pg.Rect(0, 0, 72, 25),
            manager=manager,
            container=self,
            anchors={"centery": "centery"},
            object_id=pygame_gui.core.ObjectID(object_id="#eq_label"),
            text=freq + " Hz"
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
                relative_rect=pg.Rect(x, 20, 32, 19),
                manager=manager,
                container=self,
                object_id=pygame_gui.core.ObjectID(object_id="#gain_label"),
                anchors={"centery": "centery"},
                text=("-" + str(abs(gains[i]))) if gains[i] < 0 else ("+" + str(gains[i])) if gains[i] > 0 else "  " + str(gains[i])
            )
            x += self.slider.rect.width / 6.6


class Slider(pygame_gui.elements.UIPanel):
    def __init__(self,
                 relative_rect: pg.Rect,
                 container: pygame_gui.core.UIContainer,
                 object_id: pygame_gui.core.ObjectID,
                 manager: pygame_gui.UIManager,
                 anchors,
                 starting_height: int = 1,
                 value_range: tuple = (0, 1),
                 start_value: float | int = 0,
                 click_increment: int = 1,
                 parent_element: None | pygame_gui.core.UIElement = None):
        super().__init__(relative_rect=relative_rect,
                         starting_height=starting_height,
                         manager=manager,
                         container=container,
                         object_id=object_id,
                         anchors=anchors,
                         parent_element=parent_element)
        self.build_ui(relative_rect, manager, value_range, start_value, click_increment, object_id)
        self.max_value = value_range[1]
        self.set_current_value(start_value)

    def set_current_value(self, new_value: float | int, warn: bool=True) -> None:
        """
        Set the current value of the slider.

        :param new_value: Value to set the slider to
        :param warn: set to 'False' to suppress the default warning, instead the value will be clamped.
        """
        self.wiper.set_current_value(new_value, warn)
        self._set_line_length()

    def _set_line_length(self) -> None:
        """
        Sets only the progress line length.
        """
        width = self.get_relative_rect().width * self.get_current_value_percentage()
        self.line_progress.set_dimensions((width, 4))

    def get_current_value(self) -> float | int:
        """
        Get the current slider value.
        """
        return self.wiper.get_current_value()
    
    def get_current_value_percentage(self) -> float:
        """
        Get the current slider value in percentage. <0, 1>
        """
        return self.wiper.current_percentage

    def build_ui(self, rect, manager, value_range, start_value, click_increment, object_id):
        """
        Builds all of the UI elements.
        """
        
        self.line = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(2, 0, rect.width - 2, 4),
            manager=manager,
            container=self,
            starting_height=0,
            object_id="#slider_line",
            anchors={"centery": "centery"}
        )

        self.line_progress = pygame_gui.elements.UIPanel(
            relative_rect=pg.Rect(2, 0, 0, 4),
            manager=manager,
            container=self,
            starting_height=1,
            anchors={"left": "left",
                     "centery": "centery"},
            object_id="#slider_line_progress"
        )

        self.wiper = pygame_gui.elements.UIHorizontalSlider(
            relative_rect=pg.Rect(0, 0, rect.width + 2, rect.height),
            start_value=start_value,
            value_range=value_range,
            container=self,
            parent_element=self,
            manager=manager,
            click_increment=click_increment,
            object_id=object_id,
        )


class TimeUILabel(pygame_gui.elements.UILabel):
    def __init__(self, relative_rect, manager, container, anchors={}, object_id=pygame_gui.core.ObjectID()):
        super().__init__(relative_rect=relative_rect,
                         manager=manager,
                         container=container,
                         anchors=anchors,
                         text="",
                         object_id=object_id)

    def update_time(self, time_s: float):
        """
        Updates the displayed time.

        :param time_s: Time to be displayed, in seconds.
        :type time_s: float
        """
        self.time_s = time_s
        self.minutes = int(round(time_s) / 60)
        self.seconds = round(time_s) % 60

        text = f"{self.minutes}:{self.seconds:02d}"
        self.set_text(text)
