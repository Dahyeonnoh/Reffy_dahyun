"""폴더의 이미지를 한꺼번에 올리고 AI 태깅합니다.   python -m tools.seed 이미지폴더 [작성자]
(서비스를 켜지 않아도 됩니다. WD tagger 가 준비될 때까지 기다린 뒤 진행합니다.)"""
import json
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

from app import config, db
from app.classifier import C
from app.tagger import T
from app.tagmap import VOCAB, tag_image

FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}


def main():
    if len(sys.argv) < 2:
        raise SystemExit("사용법: python -m tools.seed 이미지폴더 [작성자]")
    folder, author = Path(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else "REFFY")
    db.init()
    T.start([v["aliases"] for v in VOCAB])
    C.load()
    for _ in range(600):
        if T.status in ("ready", "error", "off"):
            break
        time.sleep(1)
    if not T.ready:
        raise SystemExit(f"WD tagger 가 준비되지 않았어요: {T.message}")
    n = 0
    for f in sorted(folder.rglob("*")):
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
            continue
        try:
            im = Image.open(f)
            im.load()
            fmt = FORMATS.get(im.format)
            if not fmt:
                continue
            im = ImageOps.exif_transpose(im)
            res = tag_image(im)
        except Exception as e:  # noqa: BLE001
            print("건너뜀:", f.name, e)
            continue
        with db.engine.begin() as c:
            iid = c.execute(db.images.insert().values(title=f.stem[:120], author=author, file="pending", w=im.width, h=im.height, views=0,
                                                      wd_json=json.dumps(res["wd"], ensure_ascii=False))).inserted_primary_key[0]
            name = f"{iid}.{fmt}"
            c.execute(db.images.update().where(db.images.c.id == iid).values(file=name))
            for t in res["tags"]:
                c.execute(db.image_tags.insert().values(image_id=iid, ikey=t["ikey"], ai_prob=t["prob"], ai_src=t["src"], user_state=None))
        (config.UPLOADS / name).write_bytes(f.read_bytes())
        th = im.convert("RGB")
        th.thumbnail((520, 1400))
        th.save(config.UPLOADS / f"t_{iid}.jpg", "JPEG", quality=85)
        n += 1
        print(f"[{n}] {f.name}: 태그 {len(res['tags'])}개")
    print(f"완료: {n}장")


if __name__ == "__main__":
    main()
