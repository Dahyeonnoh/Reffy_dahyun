"""모든 이미지를 최신 분류기로 다시 태깅합니다. 사용자가 고친 태그(추가/삭제)는 그대로 유지돼요.
   python -m tools.retag"""
import json
import time

from PIL import Image, ImageOps
from sqlalchemy import text

from app import config, db
from app.classifier import C
from app.tagger import T
from app.tagmap import VOCAB, tag_image


def main():
    db.init()
    T.start([v["aliases"] for v in VOCAB])
    C.load()
    for _ in range(600):
        if T.status in ("ready", "error", "off"):
            break
        time.sleep(1)
    if not T.ready:
        raise SystemExit(f"WD tagger 가 준비되지 않았어요: {T.message}")
    imgs = db.rows("SELECT id, file FROM images")
    for n, r in enumerate(imgs, 1):
        p = config.UPLOADS / r["file"]
        if not p.exists():
            continue
        res = tag_image(ImageOps.exif_transpose(Image.open(p)))
        with db.engine.begin() as c:
            c.execute(text("UPDATE image_tags SET ai_prob = NULL, ai_src = NULL WHERE image_id = :i"), {"i": r["id"]})
            for t in res["tags"]:
                k = c.execute(text("UPDATE image_tags SET ai_prob = :p, ai_src = :s WHERE image_id = :i AND ikey = :k"), {"p": t["prob"], "s": t["src"], "i": r["id"], "k": t["ikey"]}).rowcount
                if not k:
                    c.execute(db.image_tags.insert().values(image_id=r["id"], ikey=t["ikey"], ai_prob=t["prob"], ai_src=t["src"], user_state=None))
            c.execute(text("DELETE FROM image_tags WHERE image_id = :i AND ai_prob IS NULL AND (user_state IS NULL OR user_state = 'del')"), {"i": r["id"]})
            c.execute(text("UPDATE images SET wd_json = :w WHERE id = :i"), {"w": json.dumps(res["wd"], ensure_ascii=False), "i": r["id"]})
        print(f"[{n}/{len(imgs)}] 이미지 {r['id']}: 태그 {len(res['tags'])}개")


if __name__ == "__main__":
    main()
