"""Original, royalty-free background music synthesized in numpy, locked to the edit's tempo.

A clean, minimal house/neo-soul groove: warm electric-piano stabs, a soft pad, a bouncy sub bass, and light
drums. The kick can enter on a chosen beat (e.g. the first cut) so the drop lands with the edit. The pattern
is written so its last beat flows back into its first, which suits looping Reels/TikToks.
"""
import numpy as np

SR = 48000
NOTE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def hz(name):
    """'A3' -> 220.0"""
    n, octv = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((NOTE[n] + 12 * (octv + 1) - 69) / 12)


def _env(n, attack, tau):
    t = np.arange(n) / SR
    return np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / tau)


def _lowpass(x, cutoff):
    sp = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    sp *= 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(sp, len(x))


def epiano(freq, dur, vel=1.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * freq * t) + 0.32 * np.sin(2 * np.pi * 2 * freq * t + 0.3)
            + 0.08 * np.sin(2 * np.pi * 3 * freq * t) + 0.05 * np.sin(2 * np.pi * 7.02 * freq * t) * np.exp(-t / 0.05))
    trem = 1 + 0.06 * np.sin(2 * np.pi * 4.8 * t)
    return tone * trem * _env(n, 0.004, 0.55) * vel


def pad(freqs, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for det in (-0.12, 0.12):  # gentle chorus
            ff = f * 2 ** (det / 12)
            for h in range(1, 7):  # band-limited saw
                out += np.sin(2 * np.pi * ff * h * t + h) / h
    out = _lowpass(out, 1400)
    a = np.minimum(1, t / 0.25) * np.minimum(1, (dur - t) / 0.2).clip(0, 1)
    return out * a / (len(freqs) * 6)


def bass(freq, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(2 * np.pi * 2 * freq * t)
    return tone * _env(n, 0.003, 0.16)


def kick():
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 48 + 90 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.13) + 0.15 * np.exp(-t / 0.004)


def _noise(n, rng, lo, hi):
    x = rng.standard_normal(n)
    sp = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    sp[(f < lo) | (f > hi)] = 0
    return np.fft.irfft(sp, n)


def clap(rng):
    n = int(0.22 * SR)
    t = np.arange(n) / SR
    body = _noise(n, rng, 900, 6000)
    env = np.exp(-t / 0.06)
    for k in (0.0, 0.011, 0.022):  # three quick hand hits
        env = env + 0.6 * np.exp(-np.clip(t - k, 0, None) / 0.004) * (t >= k)
    return body / np.abs(body).max() * env * 0.55


def hat(rng, open_=False):
    n = int((0.22 if open_ else 0.045) * SR)
    t = np.arange(n) / SR
    x = _noise(n, rng, 7000, 16000)
    return x / np.abs(x).max() * np.exp(-t / (0.07 if open_ else 0.012))


def render(bpm, beats, chords, kick_from_beat=0, seed=3):
    """chords: one list of note names per bar (4 beats each). Returns stereo float32 of length beats*beat."""
    rng = np.random.default_rng(seed)
    beat = 60.0 / bpm
    total = int(beats * beat * SR)
    pad_len = total + int(2 * SR)
    L = np.zeros(pad_len)
    R = np.zeros(pad_len)
    side = np.ones(pad_len)  # sidechain gain from the kick

    def add(sig, at, gain=1.0, pan=0.0):
        a = int(at * SR)
        b = min(pad_len, a + len(sig))
        if a >= pad_len:
            return
        L[a:b] += sig[: b - a] * gain * (1 - pan) ** 0.5
        R[a:b] += sig[: b - a] * gain * (1 + pan) ** 0.5

    keys_bus = np.zeros(pad_len)
    pad_bus = np.zeros(pad_len)
    for i in range(beats):
        bar, pos = divmod(i, 4)
        notes = chords[bar % len(chords)]
        t0 = i * beat
        # drums
        if i >= kick_from_beat:
            add(kick(), t0, 0.95)
            a = int(t0 * SR)
            duck = 1 - 0.55 * np.exp(-np.arange(int(beat * SR)) / SR / 0.11)
            side[a:a + len(duck)] = np.minimum(side[a:a + len(duck)], duck[: max(0, min(len(duck), pad_len - a))])
            if pos in (1, 3):
                add(clap(rng), t0, 0.36, pan=0.05)
        add(hat(rng, open_=(pos == 3 and i >= kick_from_beat)), t0 + beat / 2, 0.16, pan=0.25)
        if i >= kick_from_beat:
            add(hat(rng), t0 + beat / 4 * 3, 0.06, pan=-0.2)
        # bass on the off-beat 8th (house bounce)
        root = hz(notes[0][:-1] + "1") if notes[0][-1].isdigit() else hz(notes[0] + "1")
        add(bass(root, beat / 2 * 0.95), t0 + beat / 2, 0.55)
        # e-piano stabs: on 1 of the bar, then on off-beats
        stabs = {0: [0.0], 1: [0.5], 2: [0.5], 3: [0.0, 0.5]}[pos]
        for s in stabs:
            for nme in notes:
                a = int((t0 + s * beat) * SR)
                sig = epiano(hz(nme), beat * 1.6, 0.9 if s == 0 else 0.7)
                keys_bus[a:a + len(sig)] += sig[: max(0, min(len(sig), pad_len - a))]
        if pos == 0:
            sig = pad([hz(n) for n in notes], 4 * beat + 0.3)
            a = int(t0 * SR)
            pad_bus[a:a + len(sig)] += sig[: max(0, min(len(sig), pad_len - a))]
    keys_bus *= side * 0.19
    pad_bus *= side * 0.5
    L += keys_bus * 0.95 + pad_bus
    R += keys_bus * 1.05 + pad_bus
    st = np.stack([L, R], 1)[:total]
    st = np.tanh(st * 1.3) / np.tanh(1.3)  # gentle glue
    return (st / (np.abs(st).max() + 1e-9) * 0.9).astype(np.float32)
