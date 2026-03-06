import os
import random
import numpy as np
import ctypes
import json
import subprocess
import wave
from io import BytesIO
from enum import Enum
from pycaw.pycaw import AudioUtilities
from multiprocessing import Process, Queue, freeze_support
from pedalboard import Pedalboard, PeakFilter, Limiter, Gain
from scipy.signal import resample_poly
from audio_player import AudioPlayer


def load_frames_folder(path: str) -> list:
    """
    Loads .png files from a folder, changes their size and returns a folder of them sorted alphabetically.\n
    Used to load all frames for an animation.

    :param path: A path to the dictionary containing the .png files.
    :type path: string
    """
    frames = []
    files = os.listdir(path)
    files.sort(key=lambda f: int(f.split(".")[0]))
    for filename in files:
        if filename.endswith(".png"):
            img = pg.image.load(os.path.join(path, filename)).convert_alpha()
            img = pg.transform.smoothscale(img, (200, 200))
            frames.append(img)
    return frames

def calculate_vis_gain(freqs: dict, q: float, frequency: int) -> float:
    """
    Calculates the gain for a specific frequency, the middle frequency of an equalizer band and a Q value. Only affects frequencies in the -3 dB bandwidth.

    :param freqs: A dictionary of middle frequencies of an equalizer's peak filters with their gains.
    :param q: Q value.
    :param frequency: Frequency for which the value should be calculated.
    :type freqs: dictionary
    :type q: float
    :type frequency: integer
    """
    for center_freq, gain in freqs:
        if abs(gain) <= 1e-12: continue
        bw = center_freq / q
        if (center_freq - bw) <= frequency <= (center_freq + bw):
            # gain je v intervale <-120, 120>
            # 1 / 10 sluzi ako normalizovanie do intervalu <-12, 12>, tieto hodnoty moze vis_gain nadobudat
            #return gain / (10 * (1 + q2 * ((frequency / center_freq) - (center_freq / frequency))**2))
            return gain / (10 * (1 + q * q * ((frequency**2 - center_freq**2)**2 / (frequency**2 * center_freq**2))))
    return 0

def normalize_audio(samples: np.ndarray) -> np.ndarray:
    """
    Uses peak normalization to normalize audio data.

    :param samples: Data for normalization.
    :type samples: numpy array
    """
    target = 1.0
    s = samples

    sabs = np.abs(s)
    max_val = np.max(sabs)

    if max_val <= 1e-12:
        return samples

    scale = target / max_val
    return s * scale

def calculate_magnitudes(datas: np.ndarray) -> np.ndarray:
    """
    Transforms data from time domain into frequency domain. Returns calculated magnitudes of complex numbers in frquency domain.

    :param datas: A chunk of raw audio data.
    :type datas: numpy array
    """

    # hanning window function sa casto pouziva, ocisti data, mensie side lobes, cistejsi vysledok
    window = np.hanning(len(datas))
    data = datas * window

    # rfft uz vracia iba "polovicu" frekvencii (rate / 2)
    fft_complex = np.fft.rfft(data)
    magnitudes = np.abs(fft_complex)

    # toto tu technicky nemusi byt, lebo ja to aj tak skalujem pre velkost okna
    #   ale korektne by to malo byt este *2 lebo DFT je mirrored half-size
    # magnitudes *= 2.0 / np.sum(window)

    magnitudes[magnitudes < 0.05] = 0
    

    return magnitudes

def any_audio_to_wav(path: str) -> bytes:
    """
    Using FFmpeg, transcodes a file in a supported format to 16-bit PCM WAVE file with a sampling frequency of 44100 Hz.\n
    Returns raw bytes of a WAVE file

    :param path: Path to the audio file.
    :type path: string
    """

    cmd = [
        "ffmpeg",
        "-i", path,
        "-f", "wav",
        "-acodec", "pcm_s16le",  # 16-bit PCM
        "-ar", "44100",
        "-loglevel", "error",
        "pipe:1"
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
    except FileNotFoundError:
        print("FFmpeg is required in order to use this app!\nExiting now...")
        pg.quit()
        exit("FFmpeg not present on this system")

    return result.stdout

def get_vis_data(curr_audio_file: str, retval: Queue) -> None:
    """
    Calculates the data needed for visualizing and playing audio.
    Normalizes (using peak normalization) the data for playback.
    Returns via the "retval" parameter.

    :param curr_audio_file: Path to the audio file.
    :param retval: Out parameter; this is where the return value is placed.
    :type curr_audio_file: string
    :type retval: multiprocessing.Queue
    """

    # otvori subor, ziska data, spolu s metadatmi ich da do zoznamu, prvy element
    # return - nic, tato funkcia je volana v druhom vlakne
    # taktiez zrobi resampling na 44,1 kHz

    if not curr_audio_file.endswith(".wav"):
        wave_bytes = any_audio_to_wav(curr_audio_file)
        wave_audio_file = BytesIO(wave_bytes)
    else:
        wave_audio_file = curr_audio_file
        temp = wave.open(wave_audio_file, "rb")
        if temp.getframerate() != 44100:
            wave_bytes = any_audio_to_wav(curr_audio_file)
            wave_audio_file = BytesIO(wave_bytes)
        temp.close()
        
    # tu uz su urcite wave subory so sampling rate 44100Hz
    with wave.open(wave_audio_file, "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        chunk = 512 # vacsi chunk = viac vyslednych frekvencnych rozsahov (chunk/2 freq rozsahov)
        #frame_size = sampwidth * channels
        
        freq = (16, 22050)
        # netreba odignorovat header, to wave robi automaticky
        #wf.readframes(int(44 / frame_size))
        ret_data = []
        sound_data = []

        if sampwidth == 1:
            dtype_ = np.uint8
        elif sampwidth == 2:
            dtype_ = np.int16 # najbeznejsie pouzivany bitrate
        elif sampwidth == 3:
            raise NotImplementedError("24-bit PCM is not supported")
        elif sampwidth == 4:
            dtype_ = np.int32
        else:
            raise ValueError("Unsupported sample width")

        while True:
            datas = wf.readframes(chunk)    # kazdu analyzu robim z chunku o velkosti chunk
            if not datas:
                break

            # pre vizualizaciu nechavam povodnu implementaciu
            data = np.frombuffer(datas, dtype=dtype_)
            cdata = data
            if channels == 2:      # stereo -> mono
                cdata = cdata.reshape(-1, channels)
                cdata = np.mean(cdata, axis=1, dtype=np.float32)
            calculated = calculate_magnitudes(cdata)

            # pre sounddevice to musim z prekladanych kanalov dostat na (data, channels) + dat a float32
            data = data.astype(np.float32, copy=False)
            data = data.reshape(-1, channels)
            sound_data.append(data)

            # if log_scale:
            #     #TODO:
            #     # logaritmicka os x
            #     #  nejak sa to scaluje, ale neviem ako
            #     freqs = np.fft.rfftfreq(chunk//2, 1/rate)[:-1]
            #     log = np.logspace(np.log10(freq[0]),
            #                     np.log10(freq[1]),
            #                     chunk // 4 + 1)
            #     band_idx = np.digitize(freqs, log) - 1

            #     log_mag = np.zeros(chunk // 4)
            #     counts = np.zeros(chunk // 4)

            #     for k, b in enumerate(band_idx):
            #         if 0 <= b < chunk // 4:
            #             log_mag[b] += calculated[k]
            #             counts[b] += 1

            #     nonzero = counts > 0
            #     log_mag[nonzero] /= counts[nonzero]

            #     ret_data.append(log_mag)

            # if log_volume:
            #     # logaritmicka hlasitost
            #     calculated = 1000 * np.log10(calculated + 1e-12)
            #     #calculated = np.clip(calculated, 0, rate//2)
            #     ret_data.append(calculated)

            ret_data.append(calculated)

    # prevzorkovanie na 44,1 kHz
    sound_data = np.concatenate(sound_data, axis=0)
    if rate != 44100:
            sound_data = np.stack([resample_poly(ch, 44100, rate) for ch in sound_data.T], axis=1)
        
    sound_data = normalize_audio(sound_data)

    retval.put((rate, chunk, freq, ret_data, sound_data))



class State(Enum):
    """
    Enum for app state
    """
    PLAYING = 1
    DATA_LOADING = 2
    INITIAL = 3
    PAUSED = 4



class App:
    def __init__(self):
        # tento import musi byt az tu kvoli ImportError (circular import)
        from classes import MusicControlPanel, VisPanel

        self.output_device = AudioUtilities.GetSpeakers()

        # zapamatany config
        try:
            with open("config.json", "r") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = None

        self.screen_width = config_data["width"] if config_data != None else 1360
        self.screen_height = config_data["height"] if config_data != None else 800

        # nie vzdy je cesta ku suborom pristupna
        self.queue = config_data["queue"] if config_data != None else ["04 - Beat It.flac"]
        self.original_queue = config_data["original_queue"] if config_data != None else self.queue.copy()

        freqs_gain_values = config_data["freqs_gain_values"] if config_data != None else [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        self.freqs = {25: freqs_gain_values[0], 50: freqs_gain_values[1],
                    110: freqs_gain_values[2], 230: freqs_gain_values[3],
                    490: freqs_gain_values[4], 1020: freqs_gain_values[5],
                    2150: freqs_gain_values[6], 4530: freqs_gain_values[7],
                    9500: freqs_gain_values[8], 20000: freqs_gain_values[9]}
        self.theme = config_data["theme"] if config_data != None else 1 # 0=dark, 1=light
        self.shuffle = config_data["shuffle"] if config_data != None else False
        self.repeat_one = config_data["repeat_one"] if config_data != None else False
        self.repeat_queue = config_data["repeat_queue"] if config_data != None else False
        self.volume = config_data["volume"] if config_data != None else 0.5
        self.vis_type = config_data["vis_type"] if config_data != None else 1

        self.currently_played_queue_index = 0
        self.vis_start = 650

        # pygame inicializacia
        pg.init()
        self.display = pg.display.init()
        pg.display.set_caption("Music player")
        icon = pg.image.load("icons/darkChartBig.png")
        pg.display.set_icon(icon)
        self.clock = pg.time.Clock()
        self.font = pg.font.Font("font/TCM_____.TTF", 12)

        self.curr_audio_file = self.queue[0]
        self.player = AudioPlayer([], volume=self.volume)
        keys = list(self.freqs.keys())
        self.eq_q_factor = 3
        self.equalizer_board = Pedalboard([
            PeakFilter(cutoff_frequency_hz=keys[0], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[1], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[2], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[3], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[4], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[5], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[6], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[7], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[8], q=self.eq_q_factor, gain_db=0),
            PeakFilter(cutoff_frequency_hz=keys[9], q=self.eq_q_factor, gain_db=0),
            Gain(gain_db=-6.0),
            Limiter(threshold_db=-0.1)
        ])
        self.player.set_board(self.equalizer_board)

        # pygame window/display veci
        self.display = pg.display.set_mode((self.screen_width, self.screen_height))
        controls_rect = pg.Rect(0, 0, self.vis_start, self.screen_height)
        drawing_rect = pg.Rect(self.vis_start, 0, self.screen_width - self.vis_start, self.screen_height)

        # pygame_gui veci:
        # 1 manager, obrazovka rozdelena na 2 panely, 1 na controls, 1 na vizualizaciu
        #  + tema a font
        theme = "theme.json" if self.theme == 0 else "light_theme.json"
        self.manager = pygame_gui.UIManager((self.screen_width, self.screen_height), enable_live_theme_updates=True)
        self.manager.add_font_paths(
            font_name="tw_cen_mt",
            regular_path="font/TCM_____.TTF"
        )
        self.manager.get_theme().get_font_dictionary().preload_font(
            font_name="tw_cen_mt",
            font_size=18,
            bold=False,
            italic=False,
            antialiased=True
        )
        self.manager.get_theme().load_theme(theme)

        self.control_panel = MusicControlPanel(
            controls_rect,
            self.manager,
            self.freqs,
            self.original_queue,
            self.volume,
            self.theme,
            self.shuffle,
            self.repeat_one,
            self.repeat_queue
        )
        self.vis_panel = VisPanel(drawing_rect, self.manager)

        # loading animacia
        icon_path = "icons/loadingDark" if self.theme == 1 else "icons/loadingLight"
        self.loading_frames = load_frames_folder(icon_path)

        # typ vizualizacie
        self.vis_num = 3
        self.log_scale = False
        self.log_volume = False
        self.fps = 44100 / 512

        self.running = True
        self.state = State.INITIAL
        
        self.__run()
    

    def __visualize(self, rate: int, chunk: int, freq_interval: tuple, working_data: list) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "basic"-type visualization, draws it onto a vis_panel surface.
        """
        # Vykreslenie vizualizacie pre 1 chunk (1 riadok base vizualizacie)

        counter = 0
        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk
        factor = self.vis_panel.rect.width / 261
        #freq_bin_color = (252, 252, 252) if self.theme == 0 else (24, 52, 78)

        q = self.eq_q_factor
        freqs = self.freqs.items()
        for j,v in enumerate(working_data):
            vis_gain = 0
            f = j * fps
            if f < f_min or f > f_max:
                counter += 1
                continue

            # zohladnenie ekvalizera:
            vis_gain = calculate_vis_gain(freqs, q, f)
            vis_gain_multiplier = 10 ** (vis_gain / 20)

            color = np.clip((255-j, 1+j, 0), 0, 255)
            x = j * factor + 5
            y = self.screen_height - (v * vis_gain_multiplier)
            y = self.screen_height if y >= self.screen_height else 0 if y <= 0 else y
            x, y = int(round(x)), int(round(y))

            pg.draw.line(self.vis_panel.surface, color, (x, self.screen_height - 15), (x, y - 15), width = 2)
            counter += 1


    def __visualize_3d(self, rate: int, chunk: int, freq_interval: tuple, data: list, position: int, vis_num: int, scale_value: float)-> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "3D"-type visualization, draws it onto a vis_panel surface.
        """

        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk
        factor = self.vis_panel.rect.width / 261
        level_offset = self.vis_panel.rect.width / 150

        q = self.eq_q_factor
        freqs = self.freqs.items()

        for iter in range(vis_num, 0, -1):
            working_data = data[position + iter] if (0 <= (position + iter) < len(data)) else data[position - vis_num]
            working_data = working_data * scale_value

            r = max(0, 255 - iter * 5)
            g = 20
            b = min(255, 100 + iter * 3)
            a = min(255, 255 // iter + 40)
            color = (r, g, b, a)

            current_iter_y = self.screen_height - (35 * iter)

            for j,v in enumerate(working_data):
                
                vis_gain = 0
                f = j * fps
                if f < f_min or f > f_max:
                    continue

                # zohladnenie ekvalizera:
                vis_gain = calculate_vis_gain(freqs, q, f)
                vis_gain_multiplier = 10 ** (vis_gain / 20)

                x = j * factor + level_offset * (iter - 1) + 5
                y = current_iter_y - (v * vis_gain_multiplier)
                y = current_iter_y if y >= current_iter_y else 0 if y <= 0 else y
                x, y = int(round(x)), int(round(y))

                # zmena sirky vyrazne spomaluje vykreslovanie
                pg.draw.line(self.vis_panel.surface, color, (x, current_iter_y), (x, y), width = 1)


    def __visualize_circle(self, rate: int, chunk: int, freq_interval: tuple, working_data: list, pos: int) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "circle" type visualization, draws it onto a vis_panel surface.
        """
        # Vykreslenie vizualizacie pre 1 chunk

        counter = 0
        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk

        q = self.eq_q_factor
        freqs = self.freqs.items()

        x_start = self.vis_panel.surface.get_width() // 2
        y_start = self.vis_panel.surface.get_height() // 2

        lines_num = 258
        angles_rad = np.linspace(0, 2*np.pi, lines_num, endpoint=False)
        sin_table = np.sin(angles_rad)
        cos_table = np.cos(angles_rad)

        for j,v in enumerate(working_data):
            
            vis_gain = 0
            f = j * fps
            if f < f_min or f > f_max:
                counter += 1
                continue

            # zohladnenie ekvalizera:
            vis_gain = calculate_vis_gain(freqs, q, f)
            vis_gain_multiplier = 10 ** (vis_gain / 20)

            color = np.clip((1 + j, 0, 255 - j), 0, 255)
            
            line_length = (v * vis_gain_multiplier)
            line_length = 0 if line_length < 0 else line_length
            index = (counter + (pos // 4)) % len(sin_table)

            x_s = x_start + 35 * sin_table[index]
            y_s = y_start + 35 * cos_table[index]
            x = line_length * sin_table[index]
            y = line_length * cos_table[index]
            e_x, e_y = int(round(x_s + x)), int(round(y_s + y))
            
            pg.draw.aaline(self.vis_panel.surface, color, (x_s, y_s), (e_x, e_y), width = 3)
            counter += 1


    def __run(self) -> None:
        """
        Private method, should not be called explicitly.\n
        Contains the main pygame and event loop. This should be run only once by the class' __init__ method
        """
        #         (rate, chunk, freq, wholeFileData, sound_data)
        # self.vis_data = (int, int, (int, int), list, np.ndarray)
        self.vis_data = tuple
        self.worker_process = None
        self.initial_data_loaded = True

        # aby boli queues synchronizovane medzi App a MusicControlPanel
        #  // nevolat // pred tym ako sa v control_panel vytvori queue GUI
        self.control_panel.queue = self.queue.copy()

        # loading animacia pomocne premenne
        current_frame = 0
        accum_time = 0
        frame_delay = 25

        while self.running:

            # skontrolovat device change
            device = AudioUtilities.GetSpeakers()
            if device.id != self.output_device.id:
                self.output_device = device
                playing = self.player.get_busy()
                self.player.restart_player(playing)
            
            # synchronizacia:
            self.control_panel.currently_played_queue_index = self.currently_played_queue_index
            # vsetky eventy pygame a panelov + update UI
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    self.running = False
                    pg.quit()
                    # zapamatanie konfiguracie uzivatela
                    save_config = {
                        "width": self.screen_width,
                        "height": self.screen_height,
                        "queue": self.queue,
                        "original_queue": self.original_queue,
                        "freqs_gain_values": list(self.freqs.values()),
                        "theme": self.theme,
                        "shuffle": self.shuffle,
                        "repeat_one": self.repeat_one,
                        "repeat_queue": self.repeat_queue,
                        "volume": self.volume,
                        "vis_type": self.vis_type
                    }
                    with open("config.json", "w") as f:
                        json.dump(save_config, f)

                    quit()
                self.manager.process_events(event)
                self.control_panel.handle_event(event, self)
                #self.vis_panel.handle_event(event, self)

            # "vymazanie" predoslej iteracie vizualizacie (refresh) + clock tick:
            self.vis_panel.surface.fill((232, 241, 242) if self.theme == 1 else (10,12,16))
            self.manager.update(1 / self.fps)
            self.manager.draw_ui(self.display)
            dt = self.clock.tick(self.fps)
            self.control_panel.update_ui(self.state, self.player.get_position_s(), self.player.get_song_length_s())

            if self.state == State.DATA_LOADING and not self.thread_retval.empty():
                self.vis_data = self.thread_retval.get()
                self.processed_vis_data_max_val = max([np.max(chunk) for chunk in self.vis_data[3]])
                self.player.set_audio(self.vis_data[4])
                self.worker_process.join()
                if not self.initial_data_loaded:
                    self.state = State.PLAYING
                    self.player.play()



            elif self.state == State.INITIAL:
                do_nothing = True



            elif self.state == State.DATA_LOADING:
                
                accum_time += dt
                if accum_time >= frame_delay:
                    accum_time = 0
                    current_frame = (current_frame + 1) % len(self.loading_frames)

                frame_surface = self.loading_frames[current_frame]
                frame_rect = frame_surface.get_rect()
                frame_rect.center = (self.vis_panel.rect.width // 2, self.vis_panel.rect.height // 2)
                self.vis_panel.surface.blit(frame_surface, frame_rect)



            elif self.state == State.PLAYING or self.state == State.PAUSED:
                rate, chunk, freq_interval, processed_vis_data, _ = self.vis_data

                fps = rate / chunk
                if self.state == State.PAUSED: curr = self.player.get_position_s(True)
                else: curr = self.player.get_position_s()

                # davam offset -30, aby bolo syncnute
                i = int(curr * fps - 30)
                if i > len(processed_vis_data) - 1:
                    # cely audio subor sa uz prehral/vizualizoval
                    self.continue_in_queue()
                    i = len(processed_vis_data) - 1
                    continue
                elif i < 0:
                    i = 0

                ############################################################################################
                #vizualizacie:

                working_data = processed_vis_data[i]
                if self.processed_vis_data_max_val > 0.0:
                    scale_value = self.screen_height / self.processed_vis_data_max_val
                    working_data = working_data * scale_value * 1.5

                # basic
                if self.vis_type == 1:
                    self.__visualize(rate, chunk, freq_interval, working_data)

                # 3D-ish
                elif self.vis_type == 2:
                    # Pocet vizualizovanych "riadkov"; nad 15 to zacina sekat s eq, ale je to in sync aj tak
                    vis_num = 12
                    self.__visualize_3d(rate, chunk, freq_interval, processed_vis_data, i, vis_num, scale_value)

                # kruhova
                elif self.vis_type == 3:
                    self.__visualize_circle(rate, chunk, freq_interval, working_data, i)

                ############################################################################################



            # nakreslenie, zaobrazenie (musi to byt v tomto poradi):
            self.display.blit(self.vis_panel.surface, self.vis_panel.rect.topleft)
            self.display.blit(self.control_panel.surface, self.control_panel.rect.topleft)
            
            pg.display.flip()
            
    

    def __set_song(self, path: str, bypass_loading=False) -> None:
        """
        Private method, should not be called explicitly.\n
        Sets a new audio file for processing and playback
        """
        # tuto metodu vola iba change_song
        self.curr_audio_file = path
        if not bypass_loading:
            self.thread_retval = Queue()
            if self.worker_process is not None and self.worker_process.is_alive():
                # get_vis_data iba cita zo suboru + pouziva ffmpeg, nehrozi data loss/corruption
                self.worker_process.terminate()
                self.worker_process.join()
            self.worker_process = Process(target=get_vis_data,
                             args=(self.curr_audio_file,
                                   self.thread_retval))
            self.worker_process.start()
        else:
            self.player.seek(0)
            self.player.play()

    def change_song(self, path: str, bypass_loading=False, clicked=False) -> None:
        """
        Changes the currently playing audio file.\nAllows for bypassing loading of the file.

        :param path: The path to the audio file.
        :param bypass_loading: Optional; Load the file data for playback and visualization?
        :param clicked: Optional; Has the user clicked a SongItem class panel?
        :type path: string
        :type bypass_loading: boolean
        :type clicked: boolean
        """
        # tuto metodu volaju aj classes
        self.player.stop()
        self.currently_played_queue_index = self.queue.index(path)
        if not bypass_loading:
            self.state = State.DATA_LOADING
        if clicked:
            self.initial_data_loaded = False
        self.__set_song(path, bypass_loading)

    def change_eq(self, frequency: int, value: float) -> None:
        """
        Changes the gain of one equalizer band.

        :param frequency: The middle frequency of the band.
        :param value: The gain of the filter.
        :type frequency: integer
        :type value: float
        """
        for filter in self.equalizer_board:
            if type(filter) is PeakFilter and filter.cutoff_frequency_hz == frequency:
                # value moze byt v intervale <-120, 120> - vyssia presnost
                filter.gain_db = value / 10
                self.freqs[frequency] = value
                break

    def change_volume(self, value: float) -> None:
        """
        Sets volume of playback.

        :param value: Value of new volume <0, 1>
        :type value: float
        """
        self.volume = value
        self.player.set_volume(value)

    def cycle_vis_type(self) -> None:
        """
        Cycles between visualization types.
        """
        self.vis_type = self.vis_type % self.vis_num + 1

    def continue_in_queue(self, clicked_back=False, clicked_next=False) -> None:
        """
        Finds the next audio file to play and plays it.

        :param clicked_back: Optional; Has the user clicked "previous song"?
        :param clicked_next: Optional; Has the user clicked "next song"?
        :type clicked_back: boolean
        :type clicked_next: boolean
        """

        self.player.stop()

        # uzivatel klikol:
        if clicked_back:
            next_index = self.currently_played_queue_index - 1
        elif clicked_next:
            next_index = self.currently_played_queue_index + 1

        # uzivatel neklikol (skoncil sa subor):
        else:
            if self.repeat_one: # funguje
                next_index = self.currently_played_queue_index
                self.change_song(self.curr_audio_file, bypass_loading=True)
                return
            elif self.repeat_queue:
                next_index = (self.currently_played_queue_index + 1) % len(self.queue)
            else:
                if self.currently_played_queue_index == len(self.queue) - 1:
                    self.state = State.INITIAL
                    return
                else:
                    next_index = self.currently_played_queue_index + 1
        if next_index < 0:
            next_index = len(self.queue) + next_index

        self.curr_audio_file = self.queue[next_index]
        self.currently_played_queue_index = self.queue.index(self.curr_audio_file)

        #synchronizacia logiky a GUI:
        self.control_panel.currently_played_queue_index = self.currently_played_queue_index
        self.control_panel.mark_played()
        self.change_song(self.curr_audio_file)

    def play_pause(self) -> None:
        """
        Toggle playback.
        """
        self.player.toggle_playback()
        if self.player.get_busy():
            self.state = State.PLAYING
        else:
            self.state = State.PAUSED

    def queue_changed(self, new_queue: list, added: bool=False) -> None:
        """
        Notify the application that the list of audio files in queue has been changed.
        
        :param new_queue: List of new queue files.
        :param added: Is it adding to the current queue?
        :type new_queue: Python list
        :type added: boolean
        """
        if added:
            self.original_queue += new_queue.copy()
            if self.shuffle:
                newq = new_queue.copy()
                random.shuffle(newq)
                self.queue += newq.copy()
            else:
                self.queue += new_queue.copy()
        else:
            self.player.stop()
            self.queue = new_queue.copy()
            self.original_queue = new_queue.copy()
            if self.shuffle:
                random.shuffle(self.queue)
            self.state = State.INITIAL
            self.initial_data_loaded = True

    def set_player_position(self, position: int) -> None:
        """
        Sets the audio player current position in the file based on percentage.

        :param position: Position in percentage <0, 100>
        :type position: integer
        """
        length = self.player.get_song_length_s()
        self.player.pause()
        self.player.seek((length / 100) * position)
        if self.state == State.PLAYING:
            self.player.play()

    def change_queue_behaviour(self, shuffle: int | None = None, repeat: int | None = None) -> None:
        """
        Change repeat and shuffle behaviour.

        :param shuffle: 0 -> shuffle DISABLED\n
                        1 -> shuffle ENABLED

        :param repeat:  0 -> repeat DISABLED\n
                        1 -> repeat one ENABLED\n
                        2 -> repeat queue ENABLED
        """
        if shuffle != None:
            if shuffle == 1:
                self.shuffle = True 
                self.original_queue = self.queue.copy()
                random.shuffle(self.queue)
            elif shuffle == 0:
                self.shuffle = False
                self.queue = self.original_queue.copy()
            self.control_panel.queue = self.queue.copy()
            #self.control_panel.set_queue(self.queue.copy())
            if not self.initial_data_loaded:
                self.currently_played_queue_index = self.queue.index(self.curr_audio_file)
                self.control_panel.currently_played_queue_index = self.currently_played_queue_index
            self.control_panel.mark_played()
        if repeat != None:
            if repeat == 0:
                self.repeat_one = False
                self.repeat_queue = False
            if repeat == 1:
                self.repeat_one = True
                self.repeat_queue = False
            if repeat == 2:
                self.repeat_one = False
                self.repeat_queue = True

    def switch_theme(self) -> None:
        """
        Changes theme of the application (light / dark).
        Rebuilds the UI.
        """
        self.theme = 1 - self.theme
        theme_path = "theme.json" if self.theme == 0 else "light_theme.json"
        self.manager.get_theme().load_theme(theme_path)
        self.manager.rebuild_all_from_changed_theme_data()
        icon_path = "icons/loadingDark" if self.theme == 1 else "icons/loadingLight"
        self.loading_frames = load_frames_folder(icon_path)

    def change_window_size(self, width: int, height: int) -> None:
        """
        Changes Pygame window size.

        :param width: New width
        :param height: New height
        :type width: integer
        :type height: integer
        """
        self.screen_width = width
        self.screen_height = height
        self.display = pg.display.set_mode((width, height))

        self.manager.set_window_resolution((self.screen_width, self.screen_height))
        self.control_panel.redraw(self.vis_start, self.screen_height)
        self.vis_panel.redraw(self.screen_width - self.vis_start, self.screen_height)
        self.control_panel.mark_played()



if __name__ == "__main__":
    freeze_support()
    # pygame import tu, kvoli multiprocessingu a Windows spawn() metode
    import pygame as pg
    import pygame_gui

    # aby sa okno automaticky neskalovalo
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    App()
    