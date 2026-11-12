"""라벨링 앱(라이트테이블)에서 팀이 학습시킨 분류기를 REFFY 가 쓰는 파일로 내보냅니다.

사용 (라벨링 앱이 쓰는 DB 에 접근할 수 있는 PC 에서):
    cd reffy
    python tools/export_classifier.py ../labeling-app
라벨링 앱의 .env(DB_URL) 설정을 그대로 사용하며, 앱의 학습 로직(app/learn.py)을 그대로 실행한 결과를
models/team_classifier.joblib 으로 저장합니다. 라벨링 앱 코드·DB 는 수정하지 않습니다(읽기만 합니다).
선행 조건: 라벨링 앱에서 WD tagger 가 이미지 태그를 한 번 이상 계산해 둔 상태(lb_tagvec) + 완료 라벨 충분.
"""
import os
import sys
import time
from pathlib import Path

if len(sys.argv) < 2:
    raise SystemExit("사용법: python tools/export_classifier.py 라벨링앱폴더")
src = Path(sys.argv[1]).resolve()
os.chdir(src)
sys.path.insert(0, str(src))
import joblib  # noqa: E402

from app import config, db  # noqa: E402
from app.learn import L  # noqa: E402
from app.tagger import T  # noqa: E402

out = Path(__file__).resolve().parent.parent / "models" / "team_classifier.joblib"
db.init_schema()
T._boot()                      # 모델 파일은 라벨링 앱 models 폴더의 것을 씁니다
if not T.ready:
    raise SystemExit(f"WD tagger 를 준비하지 못했어요: {T.message}")
L.train()
if not L.models:
    raise SystemExit(f"사용할 수 있는 분류기가 없어요 (AUC {config.LEARN_MIN_AUC} 이상, 양성 {config.LEARN_MIN_POS}장 이상인 키워드가 없음). 라벨이 더 쌓이면 다시 실행하세요. {L.error}")
out.parent.mkdir(exist_ok=True)
joblib.dump({"models": L.models, "index": L.index,
             "info": {"trained_at": time.strftime("%Y-%m-%d %H:%M"), "images": L.n_images, "keywords": len(L.models)}}, out)
print(f"저장: {out}  (키워드 {len(L.models)}개, 이미지 {L.n_images}장)")
for r in L.report[:15]:
    print(f"  {r['keyword']}: 양성 {r['pos']}장, AUC {r['auc']}, {'사용' if r['active'] else '미사용'}")
