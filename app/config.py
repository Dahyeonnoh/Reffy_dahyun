import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _load_env():
    p = BASE / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
DATA = BASE / "data"
UPLOADS = DATA / "uploads"
TMP = DATA / "tmp"
for d in (UPLOADS, TMP, BASE / "models"):
    d.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv("DB_URL") or f"sqlite:///{(DATA / 'reffy.db').as_posix()}"
TAGGER = os.getenv("TAGGER", "auto").strip().lower()          # auto / off / mock(시험용 가짜 태그)
TAGGER_REPO = os.getenv("TAGGER_REPO", "SmilingWolf/wd-vit-tagger-v3").strip()
MODEL_DIR = Path(os.getenv("MODEL_DIR") or (BASE / "models"))
CLASSIFIER = Path(os.getenv("CLASSIFIER") or (BASE / "models" / "team_classifier.joblib"))
if not CLASSIFIER.is_absolute():
    CLASSIFIER = BASE / CLASSIFIER
WD_THRESHOLD = float(os.getenv("WD_THRESHOLD", "0.35"))        # WD 태그를 키워드 추천에 쓰는 최소 확률
TEAM_PROB = float(os.getenv("TEAM_PROB", "0.60"))               # 팀 분류기 최소 확률
TAG_THRESHOLD = float(os.getenv("TAG_THRESHOLD", "0.35"))       # 최종 태그 인정 확률 (PRD 8.2)
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "15"))
PAGE = 40
