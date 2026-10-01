"""Short image cue, stored locally at 48 kHz."""
from pathlib import Path
import wave
import numpy as np

CLICK = Path(__file__).resolve().parents[1]/'assets'/'sfx'/'image-click-dulce-seda.wav'

def motion_sound(path, animation, seconds=.48):
    rate=48000; seconds=max(.12,min(2,float(seconds))); frames=round(rate*seconds)
    stereo=np.zeros((frames,2),np.float64)
    if animation!='none':
        with wave.open(str(CLICK),'rb') as source:
            if (source.getframerate(),source.getnchannels(),source.getsampwidth())!=(rate,2,2):
                raise ValueError('El clic de imagen debe ser WAV estéreo PCM16 a 48 kHz')
            cue=np.frombuffer(source.readframes(source.getnframes()),'<i2').reshape(-1,2)/32768
        # The audition file was levelled for comparison. Six decibels of
        # headroom preserves the previous editor balance at each image's dB.
        count=min(frames,len(cue));stereo[:count]=cue[:count]*.5
    with wave.open(str(path),'wb') as out:
        out.setnchannels(2);out.setsampwidth(2);out.setframerate(rate)
        out.writeframes((stereo*32767).astype('<i2').tobytes())
    return frames/rate
