import threading
from pedalboard import Pedalboard
import sounddevice as sd
from time import monotonic

class AudioPlayer():
    def __init__(self, audio: list, board:Pedalboard | None=None, rate=44100, chunkSize=16384, volume=0.5):
        self.audio = audio
        self.rate = rate
        self.chunkSize = chunkSize
        self.board = board
        self.gain = volume
        
        self.position = 0
        self.last_callback_time = 0
        self.position_at_last_cb = 0

        self.playing = False
        self.lock = threading.Lock()
        # chunk/block-size ked je <16384->eq crackling; ked je >16384->eq ma dlhu odozvu
        self.t = threading.Thread(target=self._stream, args=(rate, chunkSize), daemon=True)
        self.t.start()

    def _callback(self, outdata, frames, time, status):
        """
        Protected method, must not be called explicitly.\n
        Callback for the audio player.
        """
        now = monotonic()

        if status:
            print(status)

        with self.lock:
            if not self.playing:
                outdata[:] = 0
                return
            
            self.last_callback_time = now
            self.position_at_last_cb = self.position
            
            chunk = self.audio[self.position:(self.position + frames)]
            self.position += frames
            gain = self.gain

        if self.board is not None:
            chunk = self.board(chunk, self.rate, self.chunkSize)

        if len(chunk) < frames:
            outdata[:len(chunk)] = chunk * gain
            outdata[len(chunk):] = 0
            raise sd.CallbackStop
        else:
            outdata[:] = chunk * gain

    def _stream(self, rate: int, blocksize: int) -> None:
        """
        Protected method, should not be called explicitly.\n
        Creates a sounddevice output stream.

        :param rate: Sampling rate of the audio.
        :param blocksize: The size of a block that is processed with each callback.
        :type rate: integer
        :type blocksize: integer
        """
        self.stream = sd.OutputStream(
            samplerate=rate,
            blocksize=blocksize,
            channels=2,
            latency="low",
            device=None,
            callback=self._callback)
        
    def play(self) -> None:
        """
        Starts playback.
        """
        with self.lock:
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
        with self.lock:
            self.playing = False
            self.stream.abort()
        time = self.get_position_s()
        self.seek(time)

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

        :param audio: Raw (normalized) audio data for the audio player.
        :type audio: numpy array 
        """
        with self.lock:
            self.audio = self.board(audio, self.rate)

    def set_volume(self, gain: float) -> None:
        """
        Set positive value for linear volume gain.

        :param gain: <0.0, 1.0>
        :type gain: float
        """
        with self.lock:
            self.gain = gain

    def terminate_player(self) -> None:
        """
        Terminates the output stream; cleanup.
        """
        self.stream.close()
        self.t.join()
