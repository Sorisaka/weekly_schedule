# weekly_schedule

週次予定表PDFを生成するCLIツールです。A3縦1ページの週次表（分単位）に加えて、日別7ページを追加生成できます。

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 日本語フォント

日本語の文字化けを避けるため、TrueTypeフォントを指定してください。例として Noto Sans CJK JP を利用できます。

```
fonts/NotoSansCJKjp-Regular.otf
```

`config.yaml` の `font.path` にフォントファイルを設定すると、PDFに埋め込みされます。

## 実行例

```bash
python timetable_pdf.py `
  --week-start 2026-01-05 `
  --config config.yaml `
  --classes classes.yaml `
  --special special_days.yaml `
  --work work_shifts.txt `
  --events events_2026.txt `
  --daily on `
  --out out/2026-W02.pdf
```

サンプル入力は `samples/` に用意しています。

```bash
python timetable_pdf.py `
  --week-start 2026-01-05 `
  --config samples/config.yaml `
  --classes samples/classes.yaml `
  --special samples/special_days.yaml `
  --work samples/work_shifts.txt `
  --events samples/events_2026.txt `
  --daily on `
  --out out/2026-W02.pdf
```

## 入力ファイルフォーマット

### config.yaml

```yaml
page_title: "Weekly Schedule"
font:
  name: "NotoSansCJK"
  path: "fonts/NotoSansCJKjp-Regular.otf"

# 時限表（period -> [start,end]）
time_table:
  1: ["09:00", "10:30"]
  2: ["10:40", "12:10"]

# 習慣パターン
routines:
  free_override_mode: false
  work_type_thresholds:
    night_end: "05:00"
    morning_start: "09:00"
  pattern_nonwork:
    sleep: ["00:00", "06:30"]
    breakfast: ["07:00", "07:30"]
  pattern_work_night:
    sleep: ["04:30", "11:00"]
  pattern_work_morning:
    sleep: ["23:30", "06:00"]
    breakfast: ["06:30", "07:00"]

colors:
  sleep: "#DDEEFF"
  meal: "#FFF2CC"
  walk: "#E6FFDA"
  class: "#D8E8FF"
  work: "#FFE0CC"
  move: "#E8E8E8"
  free: "#E8D8FF"
```

### classes.yaml

曜日ごとに period番号 → {title, location(optional)} を指定します。

```yaml
mon:
  1:
    title: "経済学"
    location: "A101"
  2:
    title: "統計学"
wed:
  3:
    title: "ゼミ"
```

### special_days.yaml

```yaml
canceled:
  - date: 2026-01-08
    period: 2
    note: "休講"
  - date: 2026-01-09
    # period省略で当日の授業を全休講
ondemand:
  - date: 2026-01-10
    period: 1
    note: "オンデマンド"
```

### work_shifts.txt

年月ヘッダは `YYYYMM` 形式。日付は `D,HH[-HH]` または `D,HH:MM-HH:MM`。

```text
202601
1,19-23
3,23-04
5,19-04
```

### events_YYYY.txt

年ヘッダは `YYYY` 形式。カテゴリ省略時は `free`。

```text
2026
01/10,13:00-15:30,ミーティング,free
01/12,18-19,歯医者
```

## 機能メモ

- 時刻は `HH:MM` または `HH` を受け付けます（`HH` は `:00` 扱い）。
- 予定が1分でも重複すると赤枠で衝突表示します（自動調整なし）。
- 日跨ぎ予定は当日と翌日に自動分割して描画します。
- 60分/30分/10分の罫線で視認性を確保しています（0:00〜24:00の時間軸）。

## よくあるエラー

- フォントが見つからない
  - `config.yaml` の `font.path` に TTF/OTF のパスを指定してください。
  - 指定パスが存在しない場合は `フォントファイルが見つかりません` が表示されます。
- 日本語が文字化けする
  - 日本語対応フォント（例: Noto Sans CJK JP）を用意し、`font.path` に指定してください。
