import os
import numpy as np
import subprocess
import wave
from io import BytesIO
from multiprocessing import Process, Queue, freeze_support
from scipy.signal import resample_poly
from enum import Enum


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
    Legacy version for one frequency\n
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
            return gain / (10 * (1 + (q*q) * ((frequency / center_freq) - (center_freq / frequency))**2))
            #return gain / (10 * (1 + q * q * ((frequency**2 - center_freq**2)**2 / (frequency**2 * center_freq**2))))
    return 0

def compute_gains(frequencies: np.ndarray, center_freqs: np.ndarray, gains: np.ndarray, active: np.ndarray, q: float) -> np.ndarray:
    """
    Calculates the gain for all frequencies, the middle frequency of an equalizer band and a Q value. Additive.

    :param frequencies: Frequency for which the value should be calculated.
    :param center_freqs: An array of middle frequencies of an equalizer's peak filters with their gains.
    :param gains: Gains of the filters (in decibels)
    :param active: Which frequencies are affected by the eq.
    :param q: Q factor.
    
    :type frequencies: NDArray
    :type center_freqs: NDArray
    :type gains: NDArray
    :type active: NDArray
    :type q: float
    """
    q_sq = q * q
    r = frequencies[:, None] / center_freqs[None, :]  # shape (257, 10)
    detuning = r - (1.0 / (r + 1e-12))
    # gains are in range <-120, 120>
    band_gains = gains / (10.0 * (1.0 + q_sq * (detuning ** 2)))
    band_gains[:, ~active] = 0.0
    return band_gains.sum(axis=1)  # shape (257,) in dB; range <-12, 12>

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

    if max_val <= 1e-12: return samples

    scale = target / max_val
    return s * scale

def calculate_magnitudes(datas: np.ndarray) -> np.ndarray:
    """
    Transforms data from time domain into frequency domain. Returns calculated magnitudes of complex numbers in frquency domain.

    :param datas: A chunk of raw audio data.
    :type datas: numpy array
    """

    # hanning window function, smaller side lobes
    window = np.hanning(len(datas))
    data = datas * window

    # rfft returns (len(datas) / 2 + 1) values (257 if len(datas) is 512)
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
    Resamples the file (if needed) to 44100Hz 16bit PCM.
    Normalizes (using peak normalization) the data for playback.
    Returns via the "retval" parameter.

    :param curr_audio_file: Path to the audio file.
    :param retval: Out parameter; this is where the return value is placed.
    :type curr_audio_file: string
    :type retval: multiprocessing.Queue
    """

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
        
    # here, the file is 44100Hz 16bit
    with wave.open(wave_audio_file, "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        sampwidth = wf.getsampwidth()
        chunk = 512
        freq = (16, 22050)
        ret_data = []
        ret_data_divided = [[] for _ in range(channels)]
        sound_data = []

        # legacy
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
            datas = wf.readframes(chunk)    # read "chunk" amount of frames
            if not datas:
                break

            # visualization data
            data = np.frombuffer(datas, dtype=dtype_)
            cdata = data
            if channels > 1:      # stereo -> mono
                data_together = cdata.reshape(-1, channels)
                data_together = np.mean(data_together, axis=1, dtype=np.float32)
            calculated = calculate_magnitudes(data_together)
            ret_data.append(calculated)

            # divided data for each channel
            for i in range(channels):
                length = len(cdata)
                one_channel_data = cdata[i:length:channels]
                one_channel_data_calculated = calculate_magnitudes(one_channel_data)
                ret_data_divided[i].append(one_channel_data_calculated)

            # playback data
            #   sounddevice needs shape (data, channels) + dtype float32
            data = data.astype(np.float32, copy=False)
            data = data.reshape(-1, channels)
            sound_data.append(data)

    sound_data = np.concatenate(sound_data, axis=0)
    # legacy, should not happen
    if rate != 44100:
        sound_data = np.stack([resample_poly(ch, 44100, rate) for ch in sound_data.T], axis=1)
        
    sound_data = normalize_audio(sound_data)

    retval.put((rate, chunk, freq, ret_data, sound_data, ret_data_divided))



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
        # circular import prevention
        from classes import MusicControlPanel, VisPanel

        self.output_device = AudioUtilities.GetSpeakers()

        # remembered config state
        try:
            with open("config.json", "r") as f:
                config_data = json.load(f)
        except FileNotFoundError:
            config_data = None

        self.screen_width = config_data["width"] if config_data != None else 1360
        self.screen_height = config_data["height"] if config_data != None else 800

        # the route may not exist (SAN/NAS, network drive)
        self.queue = config_data["queue"] if config_data != None else []
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

        # pygame init
        pg.init()
        self.display = pg.display.init()
        pg.display.set_caption("Music player")
        icon = pg.image.load("icons/darkChartBig.png")
        pg.display.set_icon(icon)
        self.clock = pg.time.Clock()
        self.font = pg.font.Font("font/Inter-VariableFont_opsz,wght.ttf", 12)

        # audio player and eq
        self.curr_audio_file = ""
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

        # eq gain lookup (for visualizations)
        center_freqs = np.array(list(self.freqs.keys()), dtype=np.float32)
        gains = np.array(list(self.freqs.values()), dtype=np.float32)
        active = np.abs(gains) > 1e-12
        frequencies = np.linspace(0, 22050, 257)
        self.vis_gains = compute_gains(frequencies, center_freqs, gains, active, self.eq_q_factor)

        # pygame window/display things; splits the display into 2 parts
        self.display = pg.display.set_mode((self.screen_width, self.screen_height))
        controls_rect = pg.Rect(0, 0, self.vis_start, self.screen_height)
        drawing_rect = pg.Rect(self.vis_start, 0, self.screen_width - self.vis_start, self.screen_height)

        # pygame_gui:
        # 1 manager, panels for display split; theme + font
        theme = "theme.json" if self.theme == 0 else "light_theme.json"
        self.manager = pygame_gui.UIManager((self.screen_width, self.screen_height), enable_live_theme_updates=True)
        self.manager.add_font_paths(
            font_name="Inter",
            regular_path="font/Inter-VariableFont_opsz,wght.ttf"
        )
        self.manager.get_theme().get_font_dictionary().preload_font(
            font_name="Inter",
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

        # loading animation
        icon_path = "icons/loadingDark" if self.theme == 1 else "icons/loadingLight"
        self.loading_frames = load_frames_folder(icon_path)

        # visualization types
        self.vis_num = 6
        self.fps = 44100 / 512

        self.running = True
        self.state = State.INITIAL
        
        self.__run()
    

    def __visualize(self, rate: int, chunk_size: int, freq_interval: tuple, working_data: list) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "basic"-type visualization, draws it onto a vis_panel surface.
        """
        # 1 visualization row (basic visualization, just 1 frequency domain)

        counter = 0
        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk_size
        factor = self.vis_panel.rect.width / 261
        #freq_bin_color = (252, 252, 252) if self.theme == 0 else (24, 52, 78)

        for j,v in enumerate(working_data):
            vis_gain = 0
            f = j * fps

            if f < f_min or f > f_max:
                counter += 1
                continue

            # eq taken into account:
            vis_gain = self.vis_gains[j]
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
        level_offset = self.vis_panel.rect.width / 90

        for iter in range(vis_num, 0, -1):
            working_data = data[position + iter] if (0 <= (position + iter) < len(data)) else data[position - vis_num]
            working_data = working_data * scale_value * 1.5

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

                # eq taken into account:
                vis_gain = self.vis_gains[j]
                vis_gain_multiplier = 10 ** (vis_gain / 20)

                x = j * factor + level_offset * (iter - 1) + 5
                y = current_iter_y - (v * vis_gain_multiplier)
                y = current_iter_y if y >= current_iter_y else 0 if y <= 0 else y
                x, y = int(round(x)), int(round(y))

                # DO NOT change the width; massively impacts performace
                pg.draw.line(self.vis_panel.surface, color, (x, current_iter_y), (x, y), width = 1)


    def __visualize_circle(self, rate: int, chunk: int, freq_interval: tuple, working_data: list, pos: int) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "circle" type visualization, draws it onto a vis_panel surface.
        """

        counter = 0
        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk

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

            # eq taken into account:
            vis_gain = self.vis_gains[j]
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


    def __visualize_circle_peaks(self, rate: int, chunk: int, freq_interval: tuple, working_data: list, pos: int) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "circle" type visualization, draws it onto a vis_panel surface.
        """

        counter = 0
        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk

        lines_num = 258
        angles_rad = np.linspace(0, 2*np.pi, lines_num, endpoint=False)
        sin_table = np.sin(angles_rad)
        cos_table = np.cos(angles_rad)

        x_start = self.vis_panel.surface.get_width() // 2
        y_start = self.vis_panel.surface.get_height() // 2
        prev_x, prev_y = x_start, y_start
        last_x, last_y = 0, 0

        for j,v in enumerate(working_data):
            
            vis_gain = 0
            f = j * fps
            if f < f_min or f > f_max:
                counter += 1
                continue

            # eq taken into account:
            vis_gain = self.vis_gains[j]
            vis_gain_multiplier = 10 ** (vis_gain / 20)

            color = np.clip((1 + j, 255 - j, 30), 0, 255)
            
            line_length = (v * vis_gain_multiplier)
            line_length = 0 if line_length < 0 else line_length
            index = (counter + (pos // 4)) % len(sin_table)

            x_s = x_start + 35 * sin_table[index]
            y_s = y_start + 35 * cos_table[index]
            x = line_length * sin_table[index]
            y = line_length * cos_table[index]
            e_x, e_y = int(round(x_s + x)), int(round(y_s + y))
            if j == 1:
                prev_x, prev_y = e_x, e_y
                last_x, last_y = e_x, e_y
            if j == 256:
                e_x, e_y = last_x, last_y
            
            pg.draw.line(self.vis_panel.surface, color, (prev_x, prev_y), (e_x, e_y), width = 3)
            prev_x, prev_y = e_x, e_y
            counter += 1


    def __visualize_circle_stereo(self, rate: int, chunk: int, freq_interval: tuple, working_data_left: list, working_data_right: list, pos: int) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "circle" type visualization, draws it onto a vis_panel surface.
        """

        def draw_one_channel(channel_data: list, mid_x, mid_y):
            counter = 0
            f_min = freq_interval[0]
            f_max = freq_interval[1]
            fps = rate / chunk

            lines_num = 258
            angles_rad = np.linspace(0, 2*np.pi, lines_num, endpoint=False)
            sin_table = np.sin(angles_rad)
            cos_table = np.cos(angles_rad)

            x_start = mid_x
            y_start = mid_y
            prev_x, prev_y = x_start, y_start
            last_x, last_y = 0, 0

            for j,v in enumerate(channel_data):
                
                vis_gain = 0
                f = j * fps
                if f < f_min or f > f_max:
                    counter += 1
                    continue

                # eq taken into account:
                vis_gain = self.vis_gains[j]
                vis_gain_multiplier = 10 ** (vis_gain / 20)

                color = np.clip((30, 255 - j, 1 + j), 0, 255)
                
                line_length = (v * vis_gain_multiplier)
                line_length = 0 if line_length < 0 else line_length
                index = (counter + (pos // 4)) % len(sin_table)

                x_s = x_start + 35 * sin_table[index]
                y_s = y_start + 35 * cos_table[index]
                x = line_length * sin_table[index]
                y = line_length * cos_table[index]
                e_x, e_y = int(round(x_s + x)), int(round(y_s + y))
                if j == 1:
                    prev_x, prev_y = e_x, e_y
                    last_x, last_y = e_x, e_y
                if j == 256:
                    e_x, e_y = last_x, last_y
                
                pg.draw.line(self.vis_panel.surface, color, (prev_x, prev_y), (e_x, e_y), width = 3)
                prev_x, prev_y = e_x, e_y
                counter += 1
        
        draw_one_channel(working_data_left, self.vis_panel.surface.get_width() // 4, self.vis_panel.surface.get_height() // 2)
        draw_one_channel(working_data_right, self.vis_panel.surface.get_width() // 4 * 3, self.vis_panel.surface.get_height() // 2)


    def __visualize_circle_3d(self, rate: int, chunk: int, freq_interval: tuple, data: list, position: int, scale_value: float) -> None:
        """
        Private method, should not be called explicitly.\n
        Creates one frame of "3D circle" type visualization, draws it onto a vis_panel surface.
        """

        f_min = freq_interval[0]
        f_max = freq_interval[1]
        fps = rate / chunk

        x_start = self.vis_panel.surface.get_width() // 2
        y_start = self.vis_panel.surface.get_height() // 2

        lines_num = 258
        angles_rad = np.linspace(0, 2*np.pi, lines_num, endpoint=False)
        sin_table = np.sin(angles_rad)
        cos_table = np.cos(angles_rad)

        for iter in range(11, 0, -1):
            working_data = data[position - 4*iter] if position > 4*iter else data[0]
            working_data = working_data * scale_value * 1.5
            counter = 0

            r = 30
            g = max(0, 170 - iter * 5)
            b = min(255, 200 + iter * 3)
            a = min(255, 255 // iter + 30)
            color = (r, g, b, a)

            for j,v in enumerate(working_data):
                
                vis_gain = 0
                f = j * fps
                if f < f_min or f > f_max:
                    counter += 1
                    continue

                # eq taken into account:
                vis_gain = self.vis_gains[j]
                vis_gain_multiplier = 10 ** (vis_gain / 20)
                
                line_length = (v * vis_gain_multiplier)
                line_length = 0 if line_length < 0 else line_length
                index = (counter + (position // 4)) % len(sin_table)

                x_s = x_start + (30 + 22*iter) * sin_table[index]
                y_s = y_start + (30 + 22*iter) * cos_table[index]
                x = line_length * sin_table[index]
                y = line_length * cos_table[index]
                e_x, e_y = int(round(x_s + x)), int(round(y_s + y))
                
                pg.draw.aaline(self.vis_panel.surface, color, (x_s, y_s), (e_x, e_y), width = 2)
                counter += 1


    def __run(self) -> None:
        """
        Private method, should not be called explicitly.\n
        Contains the main pygame and event loop. This should be run only once by the class' __init__ method
        """
        #         (rate, chunk, freq, wholeFileData, sound_data, wholeFileDataDivided)
        # self.vis_data = (int, int, (int, int), list, np.ndarray, list)
        self.vis_data = tuple
        self.worker_process = None
        self.initial_data_loaded = True

        # App and MusicControlPanel queues sync
        #  DO NOT call before control_panel queue GUI is first created
        self.control_panel.queue = self.queue.copy()

        # loading animation variables
        current_frame = 0
        accum_time = 0
        frame_delay = 25

        while self.running:

            # check for device change
            device = AudioUtilities.GetSpeakers()
            if device.id != self.output_device.id:
                self.output_device = device
                playing = self.player.get_busy()
                self.player.restart_player(playing)
            
            # sync
            self.control_panel.currently_played_queue_index = self.currently_played_queue_index
            # event handling + UI update
            self.manager.update(1 / self.fps)
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    self.running = False
                    self.player.terminate_player()
                    pg.quit()
                    # remembers the config
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

                elif event.type == pygame_gui.UI_BUTTON_PRESSED or \
                    event.type == pygame_gui.UI_HORIZONTAL_SLIDER_MOVED or \
                    event.type == pg.MOUSEBUTTONDOWN:
                    self.control_panel.handle_event(event, self)
                if event.type == pg.MOUSEWHEEL:
                    if self.control_panel.queue_panel.hover_point(*pg.mouse.get_pos()):
                        self.control_panel.handle_scrolling(event)
                        continue # disables the weird deceleration
                    
                self.manager.process_events(event)

            # erases the previous iteration of vis + clock tick
            self.vis_panel.surface.fill((232, 241, 242) if self.theme == 1 else (10,12,16))
            self.manager.draw_ui(self.display)
            dt = self.clock.tick(self.fps)
            self.control_panel.update_ui(self.state, self.player.get_position_s(), self.player.get_song_length_s())

            if self.state == State.DATA_LOADING and not self.process_retval.empty():
                # data is loaded, worker process has finished
                self.vis_data = self.process_retval.get()
                # maximum value in any channel
                self.processed_vis_data_max_val = max(np.max(chunk) for outer in self.vis_data[5] for chunk in outer)
                self.player.set_audio(self.vis_data[4])
                self.worker_process.join()
                if not self.initial_data_loaded:
                    self.state = State.PLAYING
                    self.player.play()


            elif self.state == State.INITIAL:
                do_nothing = True


            elif self.state == State.DATA_LOADING:
                # data is being loaded, draw the loading animation
                
                accum_time += dt
                if accum_time >= frame_delay:
                    accum_time = 0
                    current_frame = (current_frame + 1) % len(self.loading_frames)

                frame_surface = self.loading_frames[current_frame]
                frame_rect = frame_surface.get_rect()
                frame_rect.center = (self.vis_panel.rect.width // 2, self.vis_panel.rect.height // 2)
                self.vis_panel.surface.blit(frame_surface, frame_rect)


            elif self.state == State.PLAYING or self.state == State.PAUSED:
                # is either playing, or is paused; draw the visualization
                rate, chunk, freq_interval, processed_vis_data, _, processed_vis_data_divided = self.vis_data

                fps = rate / chunk
                if self.state == State.PAUSED: curr = self.player.get_position_s(True)
                else: curr = self.player.get_position_s()

                # offset -30; sync reasons
                i = int(curr * fps - 30)
                if i > len(processed_vis_data) - 1 or self.player.get_finished():
                    # the entire file has finished playback
                    self.continue_in_queue()
                    i = len(processed_vis_data) - 1
                    continue
                elif i < 0:
                    i = 0

                ############################################################################################
                #visualizations:

                working_data = processed_vis_data[i]
                working_data_divided = [channel[i] for channel in processed_vis_data_divided]
                if self.processed_vis_data_max_val > 0.0:
                    scale_value = self.screen_height / self.processed_vis_data_max_val
                    working_data = working_data * scale_value * 1.5
                    working_data_divided = [channel * (scale_value / 2) for channel in working_data_divided]

                # basic
                if self.vis_type == 1:
                    self.__visualize(rate, chunk, freq_interval, working_data)

                # 3D-ish
                elif self.vis_type == 2:
                    # the number of visualized rows; starts to lag when above 15
                    vis_num = 12
                    self.__visualize_3d(rate, chunk, freq_interval, processed_vis_data, i, vis_num, scale_value)

                # circle
                elif self.vis_type == 3:
                    self.__visualize_circle(rate, chunk, freq_interval, working_data, i)

                # circle 3D
                elif self.vis_type == 4:
                    self.__visualize_circle_3d(rate, chunk, freq_interval, processed_vis_data, i, scale_value)

                # circle peaks
                elif self.vis_type == 5:
                    self.__visualize_circle_peaks(rate, chunk, freq_interval, working_data, i)

                # circle stereo
                elif self.vis_type == 6:
                    self.__visualize_circle_stereo(rate, chunk, freq_interval, working_data_divided[0], working_data_divided[1], i)

                ############################################################################################


            # blit and flip (order of operations must be preserved)
            self.display.blit(self.vis_panel.surface, self.vis_panel.rect.topleft)
            self.display.blit(self.control_panel.surface, self.control_panel.rect.topleft)
            pg.display.flip()
            
    

    def __set_song(self, path: str, bypass_loading=False) -> None:
        """
        Private method, should not be called explicitly.\n
        Sets a new audio file for processing and playback
        """
        # this method is called only by change_song()
        self.curr_audio_file = path
        if not bypass_loading:
            self.process_retval = Queue()
            if self.worker_process is not None and self.worker_process.is_alive():
                # get_vis_data only reads the files (+ffmpeg); data corruption won't happen; can terminate
                self.worker_process.terminate()
                self.worker_process.join()
            self.worker_process = Process(target=get_vis_data,
                             args=(self.curr_audio_file,
                                   self.process_retval))
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
                # value can be in <-120, 120> - higher resolution
                filter.gain_db = value / 10
                self.freqs[frequency] = value

                # vis_gain lookup
                center_freqs = np.array(list(self.freqs.keys()), dtype=np.float32)
                gains = np.array(list(self.freqs.values()), dtype=np.float32)
                active = np.abs(gains) > 1e-12
                frequencies = np.linspace(0, 22050, 257)
                self.vis_gains = compute_gains(frequencies, center_freqs, gains, active, self.eq_q_factor)
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

        # the user has clicked (messy)
        if clicked_back or clicked_next:
            if self.repeat_one:
                next_index = self.currently_played_queue_index
                self.change_song(self.curr_audio_file, bypass_loading=True)
                return
            if clicked_back:
                next_index = self.currently_played_queue_index - 1
            elif clicked_next:
                next_index = self.currently_played_queue_index + 1

            if next_index >= len(self.queue) - 1:
                next_index = next_index % len(self.queue)

        # the user has not clicked (file has ended)
        else:
            if self.repeat_one:
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

        # logic and GUI sync
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
        self.control_panel.queue = self.queue.copy()

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

        self.manager.clear_and_reset()
        self.manager.set_window_resolution((self.screen_width, self.screen_height))
        self.control_panel.redraw(self.vis_start, self.screen_height, self.original_queue.copy())
        self.vis_panel.redraw(self.screen_width - self.vis_start, self.screen_height)
        # queue sync
        self.control_panel.queue = self.queue.copy()
        self.control_panel.mark_played()



if __name__ == "__main__":
    #freeze_support()
    # imports here to prevent importing at every process spawn
    import pygame as pg
    import pygame_gui
    import random
    import ctypes
    import json
    from pycaw.pycaw import AudioUtilities
    from pedalboard import Pedalboard, PeakFilter, Limiter, Gain
    from audio_player import AudioPlayer

    # the window should not scale automatically (pygame thing)
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
    App()
    