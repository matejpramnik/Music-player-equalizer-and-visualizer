import threading
from pedalboard import Pedalboard
import sounddevice as sd
from time import monotonic, sleep

class AudioPlayer():
    def __init__(self, audio: list, board:Pedalboard | None=None, rate=44100, chunk_size=16384, volume=0.5):
        self.audio = audio
        self.rate = rate
        self.chunk_size = chunk_size
        self.board = board
        self.gain = pow(2, volume) - 1
        
        self.finished = False
        self.position = 0
        self.last_callback_time = 0
        self.position_at_last_cb = 0

        self.playing = False
        self.lock = threading.Lock()
        # chunk/block-size <16384 ->eq crackling; >16384 ->eq long latency
        self._stream(rate, chunk_size)

    def _callback(self, outdata, frames, time, status):
        """
        Protected method, must not be called explicitly.\n
        Callback for the audio player.
        """
        now = monotonic()

        # if status:
        #     print(status)

        with self.lock:
            self.finished = False
            if not self.playing:
                outdata[:] = 0
                return
            
            self.last_callback_time = now
            self.position_at_last_cb = self.position
            
            chunk = self.audio[self.position:(self.position + frames)]
            self.position += frames
            gain = self.gain

        if self.board is not None:
            chunk = self.board(chunk, self.rate, self.chunk_size)

        if len(chunk) < frames:
            outdata[:len(chunk)] = chunk * gain
            outdata[len(chunk):] = 0
            raise sd.CallbackStop
        else:
            outdata[:] = chunk * gain

    def _on_finished(self):
        """
        Protected method.\n
        Sets playing to False in case the restart_stream() method is called after the stream has ended.
        """
        with self.lock:
            self.finished = True
            self.playing = False
            self.position = 0

    def _stream(self, rate: int, blocksize: int, device=None) -> None:
        """
        Protected method.\n
        Creates a sounddevice output stream.

        :param rate: Sampling rate of the audio.
        :param blocksize: The size of a block that is processed with each callback.
        :param device: Output device, optional
        :type rate: integer
        :type blocksize: integer
        """
        try:
            with self.lock:
                self.stream = sd.OutputStream(
                    samplerate=rate,
                    blocksize=blocksize,
                    channels=2,
                    latency="low",
                    device=device, # None -> uses the default device (currently selected output device in Windows)
                    callback=self._callback,
                    finished_callback=self._on_finished)
        except:
            sleep(1)
            self._stream(rate, blocksize, device)
        
    def play(self) -> None:
        """
        Starts playback.
        """
        with self.lock:
            self.finished = False
            self.playing = True
            self.last_callback_time = 0
        if not self.stream.active:
            self.last_callback_time = 0
            self.position_at_last_cb = self.position
            self.stream.start()

    def pause(self) -> None:
        """
        Pauses playback. Uses sounddevice's abort method for an instant stop.
        """
        self.stream.abort()
        time = self.get_position_s()
        self.seek(time)
        with self.lock:
            self.playing = False
            self.finished = False

    def stop(self) -> None:
        """
        Stops playback and resets position. Use this before changing audio source.
        """
        with self.lock:
            self.playing = False
            self.position = 0
            self.last_callback_time = 0
            self.position_at_last_cb = self.position
        self.stream.abort()

    def seek(self, seconds: float) -> None:
        """
        Set audio player's postion, in seconds.

        :param seconds: Number of seconds since the start of the audio file to seek to.
        :type seconds: float
        """
        with self.lock:
            self.position = int(seconds * self.rate)

    def set_board(self, board: Pedalboard) -> None:
        """
        Set a Pedalboard filter board for the audio player.

        :param board: pedalboard.Pedalboard
        """
        with self.lock:
            self.board = board

    def get_position_s(self, paused=False) -> float:
        """
        Returns the current playback position of the audio file, in seconds.

        :param paused: Optional; set this to True if the playback is paused.
        :type paused: boolean
        """
        with self.lock:
            pos = self.position_at_last_cb
            t0 = self.last_callback_time
            playing = self.playing
            
        if paused:
            pos = self.position

        if not playing or t0 == 0:
            return pos / self.rate

        dt = monotonic() - t0
        return (pos / self.rate) + dt
    
    def get_song_length_s(self) -> float:
        """
        Returns the currently loaded song length, in seconds.
        """
        return len(self.audio) / self.rate

    def get_busy(self) -> bool:
        """
        Returns True if an audio file is currently being played
        """
        with self.lock:
            return self.playing
    
    def toggle_playback(self) -> None:
        """
        Toggles playback, instant.
        """
        if self.playing:
            self.pause()
        else:
            self.play()

    def set_audio(self, audio) -> None:
        """
        Sets an audio source.

        :param audio: Raw audio data for the audio player.
        :type audio: numpy array 
        """
        with self.lock:
            self.audio = audio

    def set_volume(self, gain: float) -> None:
        """
        Sets volume gain (logarithmically).

        :param gain: <0.0, 1.0>
        :type gain: float
        """
        volume = pow(2, gain) - 1
        with self.lock:
            self.gain = volume

    def terminate_player(self) -> None:
        """
        Terminates the output stream; cleanup.
        """
        self.stop()
        self.stream.close()

    def restart_player(self, play=False) -> None:
        """
        Restarts the audio player stream.
        Use in case of output device change.

        :param play: Should continue playing?
        :type play: bool
        """
        with self.lock:
            playing = self.playing
            pos = self.position
            self.playing = False
        self.stream.abort()

        self.terminate_player()
        sd.query_devices(sd.default.device, "output")
        self._stream(self.rate, self.chunk_size)

        if play or playing:
            self.seek(pos / self.rate)
            self.play()

    def get_finished(self) -> bool:
        """
        Returns True if the playback is finished.
        """
        with self.lock:
            return self.finished
