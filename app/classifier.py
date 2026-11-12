"""팀이 라벨링해서 학습시킨 키워드별 분류기 (tools/export_classifier.py 가 만든 파일을 읽음).

입력은 WD tagger 의 태그 확률, 출력은 키워드(시트 이름)별 확률입니다.
파일이 없으면 WD tagger 의 태그→키워드 매핑만 씁니다(서비스는 그대로 동작).
"""
from __future__ import annotations
import numpy as np

from . import config


class TeamClassifier:
    def __init__(self):
        self.models = {}
        self.index = {}
        self.info = {}
        self.error = ""

    def load(self):
        p = config.CLASSIFIER
        if not p.exists():
            self.error = f"{p.name} 없음 — WD 태그 매핑만 사용합니다."
            print("[AI] " + self.error, flush=True)
            return
        try:
            import joblib

            d = joblib.load(p)
            self.models, self.index, self.info = d["models"], d["index"], d.get("info", {})
            print(f"[AI] 팀 분류기 로드: 키워드 {len(self.models)}개 ({self.info.get('trained_at', '')})", flush=True)
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"
            print("[AI] 팀 분류기를 읽지 못했습니다:", self.error, flush=True)

    @property
    def ready(self) -> bool:
        return bool(self.models)

    def predict(self, tagprobs: dict) -> dict:
        if not self.models or not tagprobs:
            return {}
        x = np.zeros(len(self.index), dtype=np.float32)
        for t, p in tagprobs.items():
            j = self.index.get(t)
            if j is not None:
                x[j] = p
        x = x.reshape(1, -1)
        out = {}
        for kw, (clf, _auc, _n) in self.models.items():
            p = float(clf.predict_proba(x)[0, 1])
            if p >= config.TEAM_PROB:
                out[kw] = p
        return out


C = TeamClassifier()
