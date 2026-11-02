"""Bounded PCM WAV decoding; preserves uploaded bytes outside this module."""
from array import array
from dataclasses import dataclass
import io
import math
import struct
import sys
import wave

MAX_BYTES = 12 * 1024 * 1024
MAX_SECONDS = 60


@dataclass(frozen=True)
class Audio:
    sample_rate: int
    channels: int
    frames: int
    duration: float
    pcm16: bytes  # mono, 16000 Hz, little endian


def decode_wav(payload):
    if not isinstance(payload, bytes) or not 44 <= len(payload) <= MAX_BYTES:
        raise ValueError("WAV须为44字节～12 MiB")
    if payload[:4] != b"RIFF" or payload[8:12] != b"WAVE":
        raise ValueError("仅支持RIFF PCM WAV，不能直接上传WebM/MP3")
    if struct.unpack_from("<I", payload, 4)[0] + 8 != len(payload):
        raise ValueError("WAV长度不一致或文件截断")
    try:
        with wave.open(io.BytesIO(payload), "rb") as source:
            channels, rate, width, frames = (source.getnchannels(), source.getframerate(),
                                            source.getsampwidth(), source.getnframes())
            if source.getcomptype() != "NONE" or width != 2 or channels not in (1, 2):
                raise ValueError("仅支持16-bit PCM单声道/双声道WAV")
            if not 8000 <= rate <= 48000 or frames == 0 or frames / rate > MAX_SECONDS:
                raise ValueError("采样率须为8～48 kHz，音频时长须为0～60秒")
            pcm = source.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError("无法解析PCM WAV") from exc
    if len(pcm) != frames * channels * 2:
        raise ValueError("WAV音频帧截断")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    mono = [sum(samples[i:i+channels]) / channels for i in range(0, len(samples), channels)]
    count = max(1, int(math.floor(frames * 16000 / rate)))
    result = array("h")
    for i in range(count):
        position = i * rate / 16000
        left = min(int(position), frames-1)
        right = min(left+1, frames-1)
        sample = mono[left] + (mono[right]-mono[left]) * (position-left)
        result.append(max(-32768, min(32767, round(sample))))
    if sys.byteorder != "little":
        result.byteswap()
    return Audio(rate, channels, frames, frames/rate, result.tobytes())
