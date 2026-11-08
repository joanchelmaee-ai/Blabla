#!/usr/bin/env python3
"""Render the editorial TikTok edit described in edit/edl.json.

Pipeline
  1. timeline   - resolve shot start times (dissolves overlap), write build/timeline.json
  2. type       - render the kinetic typography overlay (scripts/render_type.js -> build/type/*.png)
  3. audio      - synthesize the "silent-ready" sound bed (room tone + soft clinks/whooshes)
  4. video      - cut / speed-ramp (with real shutter blur) / zoom / transitions in numpy,
                  piped into ffmpeg which applies the shared grade (edit/grade.txt),
                  composites the typography, adds grain and encodes 1080x1920 H.264.

Usage:  python3 scripts/render.py <project> [--skip-type] [--no-type]
        e.g. python3 scripts/render.py bracelets   -> out/bracelets/final_1080x1920.mp4
"""
import argparse
import json
import math
import os
import subprocess
import sys
import wave
from collections import OrderedDict

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rel(p):
    return os.path.join(ROOT, p)


# --------------------------------------------------------------------------- probe
def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,r_frame_rate,color_transfer:stream_side_data=rotation",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    rot = 0
    for sd in s.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(sd["rotation"])
    w, h = s["width"], s["height"]
    if rot in (90, -90, 270, -270):
        w, h = h, w
    hdr = s.get("color_transfer") in ("smpte2084", "arib-std-b67")
    return {"w": w, "h": h, "fps": float(num) / float(den), "hdr": hdr}


# --------------------------------------------------------------------------- source reader
MAX_WORK = (1440, 2560)  # decode cap: plenty of headroom for push-ins on 4K originals


class SourceReader:
    """Streams RGB frames forward from `start` seconds; random access within a sliding cache."""

    def __init__(self, path, start, info):
        self.info = info
        self.fps = info["fps"]
        w, h = info["w"], info["h"]
        scale = min(1.0, MAX_WORK[0] / w, MAX_WORK[1] / h)
        self.w, self.h = int(round(w * scale / 2) * 2), int(round(h * scale / 2) * 2)
        self.base = max(0.0, start - 0.05)
        vf = []
        if info["hdr"]:  # iPhone HLG/PQ originals -> SDR bt709
            vf.append("zscale=t=linear:npl=203,format=gbrpf32le,tonemap=hable:desat=0,"
                      "zscale=p=bt709:t=bt709:m=bt709:r=tv")
        if QUALITY["sr"]:
            vf.append("hqdn3d=0.8:0.8:2.5:2.5")
        vf.append(f"scale={self.w}:{self.h}:flags=lanczos:in_color_matrix=bt709:in_range=tv")
        vf.append("format=rgb24")
        cmd = ["ffmpeg", "-v", "error", "-ss", f"{self.base:.4f}", "-i", path,
               "-vf", ",".join(vf), "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.fsize = self.w * self.h * 3
        self.cache = OrderedDict()
        self.next_idx = 0
        self.last = None

    def _read_one(self):
        buf = self.proc.stdout.read(self.fsize)
        if len(buf) < self.fsize:
            return None
        return np.frombuffer(buf, np.uint8).reshape(self.h, self.w, 3)

    def frame_at_index(self, idx):
        while self.next_idx <= idx:
            f = self._read_one()
            if f is None:  # past end of clip: hold last frame
                f = self.last
                if f is None:
                    raise RuntimeError("source produced no frames")
            self.cache[self.next_idx] = f
            self.last = f
            self.next_idx += 1
            while len(self.cache) > 90:
                self.cache.popitem(last=False)
        if idx in self.cache:
            return self.cache[idx]
        return self.cache[next(iter(self.cache))]

    def index(self, t):
        return max(0, int(round((t - self.base) * self.fps)))

    def blended(self, t0, t1):
        """Mean of source frames whose timestamps fall in [t0, t1] (virtual shutter)."""
        i0, i1 = self.index(t0), self.index(t1)
        if i1 <= i0:
            return self.frame_at_index(i0)
        acc = np.zeros((self.h, self.w, 3), np.float32)
        for i in range(i0, i1 + 1):
            acc += self.frame_at_index(i)
        return (acc / (i1 - i0 + 1)).astype(np.uint8)

    def interpolated(self, t):
        """Frame at an exact time between two source frames, synthesized with optical flow
        (keeps slow motion smooth on 30 fps phone footage instead of stuttering repeats)."""
        x = (t - self.base) * self.fps
        a = int(np.floor(x))
        f = x - a
        if f < 0.08:
            return self.frame_at_index(max(0, a))
        if f > 0.92:
            return self.frame_at_index(a + 1)
        return flow_interp(self.frame_at_index(max(0, a)), self.frame_at_index(a + 1), f)

    def close(self):
        try:
            self.proc.stdout.close()
            self.proc.kill()
        except Exception:
            pass


# --------------------------------------------------------------------------- helpers
_DIS = None


def flow_interp(A, B, f):
    """Intermediate frame at fraction f between A and B (bidirectional DIS flow, Super-SloMo style blend)."""
    global _DIS
    if _DIS is None:
        _DIS = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    h, w = A.shape[:2]
    ga = cv2.cvtColor(A, cv2.COLOR_RGB2GRAY)
    gb = cv2.cvtColor(B, cv2.COLOR_RGB2GRAY)
    fab = _DIS.calc(ga, gb, None)
    fba = _DIS.calc(gb, ga, None)
    fta = -(1 - f) * f * fab + f * f * fba
    ftb = (1 - f) ** 2 * fab - f * (1 - f) * fba
    gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    wa = cv2.remap(A, gx + fta[..., 0], gy + fta[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    wb = cv2.remap(B, gx + ftb[..., 0], gy + ftb[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return cv2.addWeighted(wa, 1 - f, wb, f, 0)


def ease_inout(u):
    return u * u * (3 - 2 * u)


def lerp(a, b, u):
    return a + (b - a) * u


# --------------------------------------------------------------------------- AI upscaling
QUALITY = {"sr": True}          # set False by --draft for quick previews
_SR = None
SR_MODEL = os.path.join(ROOT, "models", "realesr-general-x4v3.onnx")


def sr_session():
    """Real-ESRGAN compact x4 (real-world degradations, incl. compression) via onnxruntime."""
    global _SR
    if _SR is None:
        if not os.path.exists(SR_MODEL):
            subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "build_sr_model.py")], check=True)
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = os.cpu_count() or 4
        _SR = ort.InferenceSession(SR_MODEL, so, providers=["CPUExecutionProvider"])
    return _SR


def ai_upscale(patch):
    x = patch.astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    y = sr_session().run(None, {"input": x})[0][0].transpose(1, 2, 0)
    return (np.clip(y, 0, 1) * 255 + 0.5).astype(np.uint8)


def warp_view(img, zoom, center, out_w, out_h, upscale, pre=None):
    """Sub-pixel crop (9:16) + resize in one affine warp, so slow zooms never jitter.
    When the crop has to be enlarged, the crop is cut out at source scale, upscaled 4x by the AI model,
    then resampled down to the output size, instead of a plain Lanczos stretch."""
    h, w = img.shape[:2]
    target = out_w / out_h
    if w / h > target:
        bh, bw = h, h * target
    else:
        bw, bh = w, w / target
    cw, ch = bw / zoom, bh / zoom
    cx = min(max(center[0] * w, cw / 2), w - cw / 2)
    cy = min(max(center[1] * h, ch / 2), h - ch / 2)
    x0, y0 = cx - cw / 2, cy - ch / 2
    s = out_w / cw
    m = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    if pre is not None:  # fold the alignment into the same single resample
        m = (np.vstack([m, [0, 0, 1]]) @ np.vstack([pre, [0, 0, 1]]))[:2].astype(np.float32)
    if QUALITY["sr"] and s > 1.05:
        pw, ph = int(round(out_w / s)) + 2, int(round(out_h / s)) + 2   # 1px margin each side
        mp = m.copy()
        mp[:, :] /= s
        mp[0, 2] += 1
        mp[1, 2] += 1
        patch = cv2.warpAffine(img, mp, (pw, ph), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT)
        big = ai_upscale(patch)
        k = big.shape[1] / pw  # = 4
        crop = big[int(round(k)):int(round(k * (ph - 1))), int(round(k)):int(round(k * (pw - 1)))]
        return cv2.resize(crop, (out_w, out_h), interpolation=cv2.INTER_AREA)
    interp = cv2.INTER_LANCZOS4 if s > 1 else cv2.INTER_AREA
    out = cv2.warpAffine(img, m, (out_w, out_h), flags=interp, borderMode=cv2.BORDER_REFLECT)
    if s > 1.15:  # draft mode: recover some crispness lost to plain upscaling
        amt = min(0.9, 0.35 * (s - 1.0))
        blur = cv2.GaussianBlur(out, (0, 0), 1.6)
        out = cv2.addWeighted(out, 1 + amt, blur, -amt, 0)
    return out


def motion_blur(img, length, dx):
    if length < 2:
        return img
    k = np.zeros((1, int(length)), np.float32)
    k[:] = 1.0 / int(length)
    blurred = cv2.filter2D(img, -1, k)
    m = np.array([[1, 0, dx], [0, 1, 0]], np.float32)
    return cv2.warpAffine(blurred, m, (img.shape[1], img.shape[0]), borderMode=cv2.BORDER_REFLECT)


# --------------------------------------------------------------------------- transitions
OVERLAP = ("dissolve", "pop", "blur")  # transitions where the two shots overlap in time


def punch(img, scale, focus, sigma):
    """Scale an output frame about `focus` (normalized) and soften it - used by the zoom-through."""
    h, w = img.shape[:2]
    if scale > 1.001:
        cx, cy = focus[0] * w, focus[1] * h
        m = np.array([[scale, 0, (1 - scale) * cx], [0, scale, (1 - scale) * cy]], np.float32)
        img = cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if sigma > 0.3:
        img = cv2.GaussianBlur(img, (0, 0), sigma)
    return img


# --------------------------------------------------------------------------- timeline
def build_timeline(edl):
    fps = edl["fps"]
    shots, t = [], 0
    for s in edl["shots"]:
        n = int(round(s["dur"] * fps))
        tr = s.get("trans_in", {})
        ov = tr.get("frames", 0) if tr.get("type") in OVERLAP else 0
        start = t - ov
        shots.append({"id": s["id"], "start_frame": start, "frames": n,
                      "start": start / fps, "dur": n / fps})
        t = start + n
    return {"fps": fps, "size": edl["size"], "total_frames": t, "duration": t / fps, "shots": shots}


def camera_for(spec, edl, tl):
    """A shot either moves on its own, or shares one continuous camera move with a group of shots
    (so a stop-motion sequence reads as a single slow push rather than restarting at every cut)."""
    by_id = {s["id"]: s for s in tl["shots"]}
    for cam in edl.get("cameras", []):
        if spec["id"] in cam["shots"]:
            g0 = by_id[cam["shots"][0]]["start_frame"]
            last = by_id[cam["shots"][-1]]
            g1 = last["start_frame"] + last["frames"] - 1
            return cam, g0, g1
    me = by_id[spec["id"]]
    return spec, me["start_frame"], me["start_frame"] + me["frames"] - 1


_ALIGN_CACHE = {}


def align_matrix(spec, cam, reader, edl, info):
    """Similarity transform mapping this shot's frames onto the camera group's reference frame,
    estimated from ORB features in the static upper part of the frame (props, wall)."""
    ref_t = cam.get("align_ref")
    if ref_t is None:
        return None
    key = (spec["src"], spec["in"], ref_t)
    if key in _ALIGN_CACHE:
        return _ALIGN_CACHE[key]
    ref_reader = SourceReader(rel(edl["sources"][spec["src"]]), ref_t, info)
    ref = cv2.cvtColor(ref_reader.frame_at_index(ref_reader.index(ref_t)), cv2.COLOR_RGB2GRAY)
    ref_reader.close()
    cur = cv2.cvtColor(reader.frame_at_index(reader.index(spec["in"])), cv2.COLOR_RGB2GRAY)
    h = ref.shape[0]
    mask = np.zeros_like(ref)
    mask[: int(h * cam.get("align_mask_top", 0.45)), :] = 255
    orb = cv2.ORB_create(3000)
    kr, dr = orb.detectAndCompute(ref, mask)
    kc, dc = orb.detectAndCompute(cur, mask)
    m = sorted(cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(dc, dr), key=lambda x: x.distance)[:400]
    A, _ = cv2.estimateAffinePartial2D(np.float32([kc[x.queryIdx].pt for x in m]),
                                       np.float32([kr[x.trainIdx].pt for x in m]),
                                       method=cv2.RANSAC, ransacReprojThreshold=2.0)
    _ALIGN_CACHE[key] = A
    return A


_WB_TARGET = {}


def _region_mean(img, region):
    h, w = img.shape[:2]
    x0, y0, x1, y1 = region
    return img[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].reshape(-1, 3).astype(np.float32).mean(0) + 1e-3


def wb_target(edl):
    """Reference colour of a static, neutral patch (e.g. plain wall) taken from one chosen frame."""
    cfg = edl["wb_lock"]
    key = (cfg["ref_src"], cfg["ref_t"])
    if key not in _WB_TARGET:
        path = rel(edl["sources"][cfg["ref_src"]])
        r = SourceReader(path, cfg["ref_t"], probe(path))
        _WB_TARGET[key] = _region_mean(r.frame_at_index(r.index(cfg["ref_t"])), cfg["region"])
        r.close()
    return _WB_TARGET[key]


def wb_gains(img, cfg, target):
    """Per-channel gains that hold the reference patch at the target colour (cancels auto white-balance
    and auto-exposure drift); brightness is corrected at `luma_strength` so real light changes survive."""
    m = _region_mean(img, cfg["region"])
    chroma = (target / target.mean()) / (m / m.mean())
    luma = (target.mean() / m.mean()) ** cfg.get("luma_strength", 0.5)
    return np.clip(chroma * luma, 0.7, 1.4).astype(np.float32)


def shot_frames(spec, reader, edl, tl, info=None):
    """Yield the output frames of one shot."""
    fps, (out_w, out_h) = edl["fps"], edl["size"]
    n = int(round(spec["dur"] * fps))
    me = next(s for s in tl["shots"] if s["id"] == spec["id"])
    cam, g0, g1 = camera_for(spec, edl, tl)
    z0, z1 = cam.get("zoom", [1, 1])
    center = cam.get("center", [0.5, 0.5])
    center_end = cam.get("center_end", center)
    zease = {"inout": ease_inout,
             "out": lambda u: 1 - (1 - u) ** 3,   # fast start, settles (pull-back reveals)
             "in": lambda u: u ** 3}.get(cam.get("ease"), lambda u: u)
    shutter = spec.get("shutter", 0.5)
    pre = align_matrix(spec, cam, reader, edl, info) if info else None
    wb = edl.get("wb_lock") if spec.get("wb_lock", True) else None
    target = wb_target(edl) if wb else None
    gains = None
    for k in range(n):
        if "out" in spec:  # speed ramp covering [in, out] in `dur`
            a = spec.get("ramp", 0.7)
            shape = spec.get("ramp_shape", "bell")
            if shape == "out":    # fast -> slow: decelerate after a cut
                f = lambda u: (1 + a) * u - a * u * u
            elif shape == "in":   # slow -> fast: accelerate into the next cut
                f = lambda u: (1 - a) * u + a * u * u
            else:                 # slow -> fast -> slow
                f = lambda u: u - a * math.sin(2 * math.pi * u) / (2 * math.pi)
            span = spec["out"] - spec["in"]
            ta = spec["in"] + span * f(k / n)
            tb = spec["in"] + span * f((k + 1) / n)
        else:
            sp = spec.get("speed", 1.0)
            ta = spec["in"] + k / fps * sp
            tb = ta + sp / fps
        if (tb - ta) < 0.9 / reader.fps:  # slower than the source frame rate: interpolate, don't repeat
            src = reader.interpolated(ta)
        else:
            src = reader.blended(ta, ta + shutter * (tb - ta))
        if wb:
            g = wb_gains(src, wb, target)
            gains = g if gains is None else 0.75 * gains + 0.25 * g  # smooth so the lock never pumps
            src = np.clip(src.astype(np.float32) * gains, 0, 255).astype(np.uint8)
        u = (me["start_frame"] + k - g0) / max(1, g1 - g0)
        e = zease(min(1.0, max(0.0, u)))
        c = (lerp(center[0], center_end[0], e), lerp(center[1], center_end[1], e))
        yield warp_view(src, lerp(z0, z1, e), c, out_w, out_h, True, pre)


def video_frames(edl, tl):
    fps = edl["fps"]
    infos = {k: probe(rel(v)) for k, v in edl["sources"].items()}
    pending = []  # outgoing frames held back for an overlapping transition into the next shot
    shots = edl["shots"]
    for si, spec in enumerate(shots):
        reader = SourceReader(rel(edl["sources"][spec["src"]]), spec["in"], infos[spec["src"]])
        frames = shot_frames(spec, reader, edl, tl, infos[spec["src"]])
        tin = spec.get("trans_in", {})
        nxt = shots[si + 1] if si + 1 < len(shots) else None
        ntr = (nxt or {}).get("trans_in", {})
        hold = ntr.get("frames", 0) if ntr.get("type") in OVERLAP else 0
        n = int(round(spec["dur"] * fps))
        fade_out = spec.get("fade_out", 0)
        tail = []
        n_pend = len(pending)
        for k, fr in enumerate(frames):
            # ---- incoming
            if tin.get("type") in OVERLAP and pending:
                a = ease_inout((k + 1) / (n_pend + 1))
                fr = cv2.addWeighted(pending.pop(0), 1 - a, fr, a, 0)
                if tin["type"] == "blur":  # soft-focus dissolve: defocus peaks mid-blend
                    fr = punch(fr, 1.0, (0.5, 0.5), 7 * math.sin(math.pi * a))
            elif tin.get("type") == "zoom" and k < tin["frames"]:
                p = 1 - k / tin["frames"]  # B arrives punched-in and settles
                fr = punch(fr, 1 + 0.32 * p * p, tin.get("focus_in", (0.5, 0.5)), 9 * p * p)
            elif tin.get("type") == "whip" and k < tin["frames"]:
                p = 1 - k / tin["frames"]
                fr = motion_blur(fr, 1 + 140 * p, 90 * p)
            # ---- outgoing
            if ntr.get("type") == "zoom" and k >= n - ntr["frames"]:
                p = (k - (n - ntr["frames"]) + 1) / ntr["frames"]  # A accelerates into the cut
                fr = punch(fr, 1 + 0.32 * p * p, ntr.get("focus_out", (0.5, 0.5)), 9 * p * p)
            elif ntr.get("type") == "whip" and k >= n - ntr["frames"]:
                p = (k - (n - ntr["frames"]) + 1) / ntr["frames"]
                fr = motion_blur(fr, 1 + 140 * p, -90 * p)
            if fade_out and k >= n - fade_out:
                a = ease_inout((k - (n - fade_out) + 1) / fade_out)
                paper = np.full_like(fr, (246, 243, 238))
                fr = cv2.addWeighted(fr, 1 - a, paper, a, 0)
            if hold and k >= n - hold:
                tail.append(fr)
                continue
            yield fr
        reader.close()
        pending = tail


# --------------------------------------------------------------------------- audio
SR = 48000


def synth_audio(edl, tl, path):
    total = tl["duration"]
    if edl.get("music"):
        import music
        m = edl["music"]
        beat = 60.0 / m["bpm"]
        beats = int(np.ceil(total / beat))
        mix = music.render(m["bpm"], beats, m["chords"], m.get("kick_from_beat", 0))
        n_total = int(total * SR)
        mix = mix[:n_total]
        fade = int(0.03 * SR)
        mix[-fade:] *= np.linspace(1, 0, fade)[:, None]
        pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        return
    n = int(total * SR) + SR // 2
    rng = np.random.default_rng(7)
    mix = np.zeros((n, 2), np.float32)

    # soft room tone (pink-ish noise, low-passed) so the clip never sounds dead
    white = rng.standard_normal(n).astype(np.float32)
    spec = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n, 1 / SR)
    shape = 1 / np.sqrt(np.maximum(freqs, 20)) * (1 / (1 + (freqs / 2500) ** 2))
    room = np.fft.irfft(spec * shape, n).astype(np.float32)
    room *= 10 ** (-50 / 20) / (np.sqrt(np.mean(room ** 2)) + 1e-9)
    mix += room[:, None]

    starts = {s["id"]: s["start"] for s in tl["shots"]}

    def clink(gain):
        d = int(0.6 * SR)
        t = np.arange(d) / SR
        out = np.zeros(d, np.float32)
        f0 = rng.uniform(2300, 2800)
        for ratio, amp, tau in [(1, 1, .22), (1.51, .55, .16), (2.33, .35, .1), (3.2, .2, .07)]:
            out += amp * np.sin(2 * np.pi * f0 * ratio * t + rng.uniform(0, 6)) * np.exp(-t / tau)
        out *= np.minimum(1, t / 0.002)
        tap = np.zeros(d, np.float32)  # a second, softer touch 28 ms later
        lag = int(0.028 * SR)
        tap[lag:] = out[:-lag] * 0.45
        out = out + tap
        return out / np.max(np.abs(out)) * 10 ** (-20 / 20) * gain

    def click(gain):
        """Soft plastic 'plug-in' click: a short band-passed transient over a tiny low thump."""
        d = int(0.12 * SR)
        t = np.arange(d) / SR
        noise = rng.standard_normal(d).astype(np.float32)
        sp = np.fft.rfft(noise)
        fr = np.fft.rfftfreq(d, 1 / SR)
        sp *= np.exp(-((np.log(np.maximum(fr, 1)) - np.log(3200)) ** 2) / 0.35)
        snap = np.fft.irfft(sp, d).astype(np.float32) * np.exp(-t / 0.006)
        thump = np.sin(2 * np.pi * 180 * t) * np.exp(-t / 0.018) * 0.5
        out = snap / (np.max(np.abs(snap)) + 1e-9) + thump
        return out / np.max(np.abs(out)) * 10 ** (-13 / 20) * gain

    def whoosh(gain):
        d = int(0.45 * SR)
        noise = rng.standard_normal(d).astype(np.float32)
        sp = np.fft.rfft(noise)
        fr = np.fft.rfftfreq(d, 1 / SR)
        sp *= np.exp(-((np.log(np.maximum(fr, 1)) - np.log(1800)) ** 2) / 1.2)
        out = np.fft.irfft(sp, d).astype(np.float32)
        env = np.sin(np.pi * np.linspace(0, 1, d)) ** 2
        env = env * np.linspace(0.6, 1.0, d)
        out *= env
        return out / np.max(np.abs(out)) * 10 ** (-23 / 20) * gain

    for i, fx in enumerate(edl.get("sfx", [])):
        at = starts[fx["at"]] + fx.get("offset", 0)
        sig = {"clink": clink, "whoosh": whoosh, "click": click}[fx["type"]](fx.get("gain", 1))
        a = max(0, int(at * SR))
        b = min(n, a + len(sig))
        pan = 0.5 + 0.12 * math.sin(i * 1.7)
        mix[a:b, 0] += sig[: b - a] * (1 - pan) * 1.4
        mix[a:b, 1] += sig[: b - a] * pan * 1.4

    fade = int(0.08 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)[:, None]
    end = int(total * SR)
    mix[end - fade:end] *= np.linspace(1, 0, fade)[:, None]
    mix = mix[:end]
    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project", help="name of the edit: reads edit/<project>.json + type/<project>.html")
    ap.add_argument("--out", help="default: out/<project>/final_1080x1920.mp4")
    ap.add_argument("--skip-type", action="store_true", help="reuse the rendered type frames")
    ap.add_argument("--no-type", action="store_true", help="render without typography")
    ap.add_argument("--draft", action="store_true", help="fast preview: plain Lanczos instead of AI upscaling")
    args = ap.parse_args()
    args.out = args.out or f"out/{args.project}/final_1080x1920.mp4"
    QUALITY["sr"] = not args.draft
    BUILD = os.path.join(ROOT, "build", args.project)

    edl = json.load(open(rel(f"edit/{args.project}.json")))
    if edl.get("typography") is False:  # an edit can opt out of on-screen text entirely
        args.no_type = True
    os.makedirs(BUILD, exist_ok=True)
    os.makedirs(os.path.dirname(rel(args.out)), exist_ok=True)
    tl = build_timeline(edl)
    json.dump(tl, open(os.path.join(BUILD, "timeline.json"), "w"), indent=2)
    print(f"timeline: {tl['total_frames']} frames = {tl['duration']:.2f}s", file=sys.stderr)

    if not args.no_type and not args.skip_type:
        subprocess.run(["node", rel("scripts/render_type.js"), rel(f"type/{args.project}.html"), BUILD],
                       check=True, cwd=ROOT)

    wav = os.path.join(BUILD, "audio.wav")
    synth_audio(edl, tl, wav)

    grade = open(rel(edl.get("grade", "edit/grade.txt"))).read().strip()
    w, h = edl["size"]
    fps = edl["fps"]
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-"]
    if args.no_type:
        fc = f"[0:v]format=gbrp,{grade}[c];"
        amap = "1:a"
    else:
        cmd += ["-framerate", str(fps), "-i", os.path.join(BUILD, "type", "%05d.png")]
        fc = f"[0:v]format=gbrp,{grade}[g];[1:v]format=rgba[t];[g][t]overlay=0:0:format=gbrp:shortest=1[c];"
        amap = "2:a"
    fc += ("[c]scale=out_color_matrix=bt709:out_range=tv,format=yuv444p,"
           "noise=c0s=2:c0f=t,format=yuv420p[v]")
    cmd += ["-i", wav, "-filter_complex", fc, "-map", "[v]", "-map", amap,
            "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-profile:v", "high",
            "-x264-params", "aq-mode=3:aq-strength=0.9:deblock=-1,-1",
            "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-color_range", "tv",
            *(["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"] if edl.get("music") else []),
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
            "-movflags", "+faststart", "-shortest", rel(args.out)]
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    for fr in video_frames(edl, tl):
        enc.stdin.write(np.ascontiguousarray(fr).tobytes())
        count += 1
    enc.stdin.close()
    enc.wait()
    print(f"wrote {count} frames -> {args.out}", file=sys.stderr)
    if count != tl["total_frames"]:
        print(f"WARNING: expected {tl['total_frames']} frames", file=sys.stderr)


if __name__ == "__main__":
    main()
