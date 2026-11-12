# REFFY — 레퍼런스 검색 서비스 (MVP)

이미지를 올리면 **WD tagger + 우리 팀이 라벨링해서 학습시킨 분류기**가 태그를 붙이고,
검색어·태그 필터로 레퍼런스를 찾는 서비스입니다. 화면은 와이어프레임(홈 피드 · 상세 필터 · 검색 결과 · 카드 상세 · 업로드)과
Design System 토큰을 따릅니다. 라벨링 앱(라이트테이블)과는 **별도 프로그램**이며 라벨링 앱은 수정하지 않습니다.

## 실행
```
cd reffy
python -m venv .venv && .venv\Scripts\activate        # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env                                 # (선택) 설정
python run.py                                          # http://127.0.0.1:8100
```
처음 켜면 WD tagger 모델(`SmilingWolf/wd-vit-tagger-v3`, 수백 MB)을 `models/` 로 내려받습니다(라벨링 앱 models 폴더의 것을 복사해 넣어도 됩니다:
`models/wd-vit-tagger-v3/model.onnx`, `selected_tags.csv`). 준비되는 동안에는 업로드 화면에서 직접 태그를 고를 수 있습니다.

## 팀 분류기 연결 (라벨링 → 서비스)
```
python tools/export_classifier.py ../labeling-app      # models/team_classifier.joblib 생성
python run.py                                          # 다음 실행부터 자동 적용
python -m tools.retag                                  # 이미 올라온 이미지를 새 분류기로 다시 태깅(사용자 수정은 유지)
```
라벨이 쌓여 분류기가 새로 학습되면 위 두 줄을 다시 실행하세요. 파일이 없으면 WD tagger → 기준표 매핑만 사용합니다.

## 이미지 한꺼번에 넣기
```
python -m tools.seed 이미지폴더 [작성자]
```

## 태깅 흐름 (PRD 8.2)
1. 업로드 → WD tagger 가 Safebooru 형식 태그 확률을 계산
2. ① 기준표(ia.json)의 Safebooru 태그 매핑 → 키워드 후보 ② 팀 분류기(확률 ≥ `TEAM_PROB` 0.60) → 키워드 후보
3. 같은 "하나만" 축은 확률이 가장 높은 하나만 남김
4. 사용자가 업로드 화면/상세 화면에서 태그를 지우거나 추가 → **최종 태그 = AI 태그(확률 ≥ `TAG_THRESHOLD`) + 사용자 추가 − 사용자 삭제**
   (AI 예측과 사용자 수정은 `image_tags` 에 따로 저장되어 나중에 합치는 규칙을 바꿀 수 있습니다)

## 검색
- 검색어는 공백으로 나눠 각각 태그에 연결합니다: 키워드 이름 > 묶음 이름 > 기준표 Safebooru 태그 > 판단 기준 설명, 그리고 작은 동의어 사전(`app/search.py` 의 `SYN`: "앉은"→앉기 등).
- 태그로 못 찾은 단어는 제목·WD 영어 태그와 비교합니다. 결과 위의 `#태그` 칩은 검색어에서 찾은 태그입니다.
- 필터: 같은 축은 OR, 축끼리는 AND. 정렬: 최근 / 인기(조회수) / 관련도.
- 태그 사전은 라벨링 기준표(`data/ia.json`, 일러스트용 223개)입니다. 기준표가 바뀌면 라벨링 앱의 `app/ia.json` 을 `data/ia.json` 으로 복사하세요.

## 이번 MVP에 없는 것 (와이어프레임에는 있음)
로그인·회원가입, 3D 포즈·색상 필터(탭은 비활성), 킵 스페이스·서랍, 알림·팔로우·하트·댓글, 사진 API 이미지.
작성자는 닉네임만 입력합니다(계정 없음). PRD §6 기준 F01~F07 범위입니다.

## 환경 변수 (`.env`)
`DB_URL`(비우면 SQLite `data/reffy.db`, MySQL 은 `mysql+pymysql://...`), `TAGGER`(auto/off/mock), `CLASSIFIER`, `WD_THRESHOLD`, `TEAM_PROB`, `TAG_THRESHOLD`, `PORT`.
`TAGGER=mock` 은 모델 없이 화면을 시험하는 가짜 태그입니다. 실제 서비스에는 쓰지 마세요. 값 뒤에 `# 주석`을 붙이지 마세요.

## 폴더
`app/` 서버(main·tagger·classifier·tagmap·search·db) · `static/` 화면 · `tools/` 분류기 내보내기·재태깅·시드 · `data/` 기준표·DB·업로드 · `models/` 모델 파일

## 계정·킵 스페이스·서랍·알림 (Figma 와이어프레임 반영)
- 화면 주소: `#/` 홈, `#/login`, `#/signup`, `#/keep`(킵 스페이스), `#/drawer`(서랍: 레퍼런스 북 · 최근 본 · 반응한), `#/post/번호`(게시물 상세).
- 둘러보기와 검색은 로그인 없이 되고, 업로드·하트·댓글·팔로우·킵·북·알림은 로그인이 필요합니다.
- 비밀번호는 PBKDF2 로 해시해 저장하고, 세션은 HttpOnly 쿠키를 씁니다. 기존 DB 는 서버를 켤 때 새 테이블과 열이 자동으로 추가되며 데이터는 그대로입니다.
- 로그인 이전에 올라간 이미지는 주인이 없어서, 로그인한 누구나 태그를 고치거나 삭제할 수 있습니다.
- 아직 안 된 것: SNS 로그인(Google·카카오·네이버·X), 비밀번호 찾기, 약관 전문, 프로필·팔로워 화면, 3D 포즈·색상 필터, 북 커버 이미지 직접 업로드(처음 담은 3장이 커버가 됩니다).

## 디자인 (가이드 적용본)
Figma "Web (가이드 적용본)" 기준: GNB 88px(검색 320,22 950×44 · 액션 1340,28), 필터 300px(p24, 항목 pitch 36), 피드 pt29/px24·필터와 20 간격·카드 간격 14, 상세 패널 389px, 알림 팝오버 400px, 로그인 Split 720|720, 업로드 680|680.
아이콘은 `static/icons.js`(Figma Icons 컴포넌트의 SVG 경로 그대로), 폰트는 Pretendard 타입 스케일 변수(`--t-*`, app.css 하단)입니다.

## 컬러 팔레트 검색
- 이미지를 올리면 대표색 최대 5개를 뽑아 DB(`images.colors`)에 저장합니다. 기존 이미지는 서버 시작 때 자동으로 채워요.
- 필터 패널 '색상 필터' 탭에서 색을 고르거나(최대 5개) 직접 입력 → '필터 적용하기'. 상세 화면의 팔레트 버튼에서 그 이미지의 색을 눌러도 같은 색으로 찾아요.
- `GET /api/images?color=#hex,#hex` — 그 색 계열(빨강·파랑 등은 색상 ±30°)이 이미지 면적의 30% 이상이면 노출, 점유율이 큰 순. 검정·회색·흰색은 밝기 구간으로 판단. 이미지 위 팔레트 아이콘 → 대표색 5개를 현재 팔레트로 불러오기(`GET /api/images/{id}/colors`).

## 마이페이지
- `#/me` 내 프로필, `#/u/아이디` 다른 사람 프로필, `#/me/edit` 프로필 편집. 아바타 메뉴 → 마이페이지.
- 프로필: 사진·닉네임·소개(100자)·외부 링크(최대 5개, http(s)만), 게시물/팔로워/팔로잉 수, 게시물·북 탭(북 탭은 본인만). 팔로워/팔로잉 숫자를 누르면 목록 모달.
- API: `GET /api/users/{uid}`, `/posts`, `/books`, `/follows?kind=followers|following`, `PUT /api/me/profile`, `POST|DELETE /api/me/avatar`, `POST /api/books/{id}/cover`.
