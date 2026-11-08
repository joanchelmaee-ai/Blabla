#!/usr/bin/env python3
"""Build an ONNX copy of Real-ESRGAN's compact real-world upscaler (realesr-general-x4v3) without PyTorch.

The .pth checkpoint is a zip of pickled tensors; we unpickle it with stand-ins for the torch classes,
read the raw float32 storages, and rebuild the SRVGGNetCompact graph (conv + PReLU x 32, pixel-shuffle x4,
plus a nearest-upsampled skip) with the `onnx` helper API.

    python3 scripts/build_sr_model.py   # models/realesr-general-x4v3.pth -> models/realesr-general-x4v3.onnx
Weights: https://github.com/xinntao/Real-ESRGAN (BSD-3-Clause).
"""
import os
import pickle
import zipfile

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "models", "realesr-general-x4v3.pth")
DST = os.path.join(ROOT, "models", "realesr-general-x4v3.onnx")
URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth"


def load_state_dict(path):
    zf = zipfile.ZipFile(path)
    prefix = zf.namelist()[0].split("/")[0]

    class Storage:
        def __init__(self, key, dtype):
            raw = zf.read(f"{prefix}/data/{key}")
            self.arr = np.frombuffer(raw, dtype=dtype)

    def rebuild_tensor(storage, offset, size, stride, *args):
        if not size:
            return storage.arr[offset:offset + 1].reshape(())
        itemsize = storage.arr.itemsize
        return np.lib.stride_tricks.as_strided(storage.arr[offset:], shape=tuple(size),
                                               strides=tuple(s * itemsize for s in stride)).copy()

    import collections

    # Weights-only loading (same idea as torch.load(weights_only=True)): the checkpoint may reference
    # ONLY these names, each mapped to our own harmless stand-in. Anything else is refused, so the file
    # cannot make the unpickler import or call arbitrary code.
    allowed = {
        ("torch._utils", "_rebuild_tensor_v2"): rebuild_tensor,
        ("torch", "FloatStorage"): np.float32,
        ("torch", "HalfStorage"): np.float16,
        ("torch", "DoubleStorage"): np.float64,
        ("collections", "OrderedDict"): collections.OrderedDict,
    }

    class Unpickler(pickle.Unpickler):
        def find_class(self, module, name):
            if (module, name) in allowed:
                return allowed[(module, name)]
            raise pickle.UnpicklingError(f"refusing to load {module}.{name} from checkpoint")

        def persistent_load(self, pid):
            # ('storage', storage_type, key, location, numel)
            _, dtype, key, _, _ = pid
            if not isinstance(dtype, type):
                dtype = np.float32
            return Storage(key, dtype)

    data = Unpickler(zf.open(f"{prefix}/data.pkl")).load()
    return data.get("params_ema", data.get("params", data))


def build(sd):
    keys = sorted({int(k.split(".")[1]) for k in sd}, key=int)
    nodes, inits = [], []
    x = "input"
    for idx in keys:
        w = sd[f"body.{idx}.weight"].astype(np.float32)
        name = f"body_{idx}"
        if w.ndim == 4:  # conv
            b = sd[f"body.{idx}.bias"].astype(np.float32)
            inits += [numpy_helper.from_array(w, name + "_w"), numpy_helper.from_array(b, name + "_b")]
            nodes.append(helper.make_node("Conv", [x, name + "_w", name + "_b"], [name], pads=[1, 1, 1, 1],
                                          kernel_shape=[3, 3]))
        else:  # PReLU, slope per channel
            inits.append(numpy_helper.from_array(w.reshape(-1, 1, 1), name + "_slope"))
            nodes.append(helper.make_node("PRelu", [x, name + "_slope"], [name]))
        x = name
    nodes.append(helper.make_node("DepthToSpace", [x], ["shuffled"], blocksize=4, mode="CRD"))
    inits.append(numpy_helper.from_array(np.array([1, 1, 4, 4], np.float32), "scales"))
    nodes.append(helper.make_node("Resize", ["input", "", "scales"], ["base"], mode="nearest"))
    nodes.append(helper.make_node("Add", ["shuffled", "base"], ["output"]))
    graph = helper.make_graph(nodes, "srvgg_compact_x4",
                              [helper.make_tensor_value_info("input", TensorProto.FLOAT, [1, 3, "h", "w"])],
                              [helper.make_tensor_value_info("output", TensorProto.FLOAT, [1, 3, "H", "W"])],
                              inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    model.ir_version = 8  # readable by older onnxruntime builds
    onnx.checker.check_model(model)
    return model


if __name__ == "__main__":
    if not os.path.exists(SRC):
        import urllib.request
        os.makedirs(os.path.dirname(SRC), exist_ok=True)
        urllib.request.urlretrieve(URL, SRC)
    sd = load_state_dict(SRC)
    onnx.save(build(sd), DST)
    print(f"{len(sd)} tensors -> {DST}")
