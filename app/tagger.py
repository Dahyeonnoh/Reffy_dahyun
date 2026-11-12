"""WD tagger (ONNX): 이미지 -> Danbooru/Safebooru 형식 태그 확률. 라벨링 앱과 같은 모델·전처리를 씁니다.

- 처음 켤 때 models/<저장소 이름>/ 으로 model.onnx, selected_tags.csv 를 내려받습니다(수백 MB).
  오프라인이면 그 폴더에 직접 넣어 두면 됩니다.
- TAGGER=mock 은 모델 없이 화면·검색을 시험하기 위한 가짜 태그입니다(실제 서비스에는 쓰지 마세요).
"""
from __future__ import annotations
import csv
import hashlib
import os
import threading
import urllib.request

import numpy as np

from . import config


class Tagger:
    def __init__(self):
        self.status = "off"          # off / loading / ready / error
        self.message = ""
        self.session = None
        self.names: list = []
        self.general = None
        self.counts: list = []
        self.size = 448
        self.mock = False
        self.model_id = config.TAGGER_REPO.split("/")[-1]
        self.lock = threading.Lock()

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def start(self, vocab_aliases=()):
        if config.TAGGER == "off":
            self.message = "TAGGER=off"
            return
        if config.TAGGER == "mock":
            self.mock, self.status = True, "ready"
            self._aliases = sorted({t for a in vocab_aliases for t in a.split()})
            self.message = "시험용 가짜 태그(mock)"
            print("[AI] TAGGER=mock : 가짜 태그로 동작합니다(시험 전용).", flush=True)
            return
        threading.Thread(target=self._boot, daemon=True).start()

    def _fetch(self, name: str, folder):
        dst = folder / name
        if dst.exists():
            return dst
        folder.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{config.TAGGER_REPO}/resolve/main/{name}"
        print(f"[AI] {name} 내려받는 중... ({url})", flush=True)
        tmp = dst.with_suffix(dst.suffix + ".part")
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(tmp, dst)
        return dst

    def _boot(self):
        self.status = "loading"
        try:
            import onnxruntime as ort

            folder = config.MODEL_DIR / self.model_id
            onnx_path = self._fetch("model.onnx", folder)
            tags_path = self._fetch("selected_tags.csv", folder)
            with open(tags_path, newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.names = [r["name"] for r in rows]
            self.general = np.array([r["category"] == "0" for r in rows])
            self.counts = [int(r.get("count") or 0) for r in rows]
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = max(1, (os.cpu_count() or 2) // 2)
            self.session = ort.InferenceSession(str(onnx_path), sess_options=opts, providers=["CPUExecutionProvider"])
            self.size = int(self.session.get_inputs()[0].shape[1])
            self.status = "ready"
            print(f"[AI] WD tagger 준비 완료 ({self.model_id}, {len(self.names)}개 태그)", flush=True)
        except Exception as e:  # noqa: BLE001
            self.status, self.message = "error", f"{type(e).__name__}: {e}"
            print("[AI] WD tagger 를 쓸 수 없습니다:", self.message, flush=True)

    def _prepare(self, im):
        from PIL import Image

        im = im.convert("RGBA")
        canvas = Image.new("RGBA", im.size, (255, 255, 255, 255))
        canvas.alpha_composite(im)
        im = canvas.convert("RGB")
        w, h = im.size
        side = max(w, h)
        sq = Image.new("RGB", (side, side), (255, 255, 255))
        sq.paste(im, ((side - w) // 2, (side - h) // 2))
        if side != self.size:
            sq = sq.resize((self.size, self.size), Image.BICUBIC)
        arr = np.asarray(sq, dtype=np.float32)[:, :, ::-1]   # RGB -> BGR
        return np.expand_dims(arr, 0)

    def predict(self, im) -> dict:
        """{태그: 확률}  (0.02 이상만)"""
        if self.mock:
            seed = int(hashlib.md5(im.tobytes()[:4096] + str(im.size).encode()).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            pool = self._aliases or ["solo", "1girl"]
            pick = rng.choice(len(pool), size=min(len(pool), 14), replace=False)
            return {pool[i]: float(rng.uniform(0.4, 0.95)) for i in pick}
        with self.lock:
            inp = self.session.get_inputs()[0].name
            out = self.session.run(None, {inp: self._prepare(im)})[0][0]
        idx = np.where(out >= 0.02)[0]
        return {self.names[i]: float(out[i]) for i in idx}


T = Tagger()
