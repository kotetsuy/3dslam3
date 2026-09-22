# 3dslam3 — 複数写真から簡易3DGSを生成

## モデル選定状況

- **SigLIP 2: 採用**（物体／部屋・風景の分類）。独立CLIとして実装済みで、写真GUIからは自動実行しません。
- **FreeSplatter-O: 不採用**。ヘッドホン4枚を背景あり・背景除去後の両方で試したが、ユーザーの閲覧評価で品質に満足できなかったため。CPUで約50秒の推論も10秒目標に未達。これは今回の写真・前処理・実行条件に対する判断です。再現用スクリプトと結果は保持します。
- **DA3-BASE → 点群 → 簡易3DGS: 当面の基本方式として採用**。ヘッドホンと渋谷駅の両方でユーザーの閲覧評価が良好でした。
- **写真に合わせた最適化: 任意の追加処理**。色・透明度・大きさの最適化を実装・検証済みですが、現在は簡易変換で十分との判断からGUIの通常生成には入れていません。


## 現在の使い方

更新日: 2026-09-21。対象マシンはAMD Ryzen AI MAX+ 395 / Radeon 8060Sです。現在の基本処理は次のとおりです。

```text
写真2〜8枚（まずは4枚）
  → DA3-BASEで深度・カメラ姿勢を推定
  → RGB点群へ変換
  → 球状Gaussianへ簡易変換
  → 標準3DGS属性のPLYを保存・WebGL2ビューアで表示
```

DA3-BASE自身が3DGSを直接生成するわけではありません。GUIでは背景を含むシーン全体を生成します。ヘッドホンで試した背景除去マスクによる物体だけの抽出はCLIの追加処理です。メッシュ化はしていません。

### 起動・停止

このPCでは必要なモデル・実行環境をセットアップ済みです。プロジェクトディレクトリで実行します。

```bash
./start_all.sh
# ROCm初期化・モデル読込・ウォームアップ完了後に起動完了を表示
# ブラウザ: http://127.0.0.1:8080/

./stop_all.sh
```

起動中はDA3モデルをGPUに保持し、写真生成時にも同じモデルを再利用します。新規セットはGPU（ROCm / float32）が既定で、CPUも選択できます。ROCm常駐を省略する起動は `./start_all.sh --cpu`。ログは `run/server.log` です。初回のダウンロードと環境構築、設定変更、停止対象の扱いは後述の各節を参照してください。`start_all.sh` 自体はインストールやモデル取得を行いません。

### 写真GUIとビューア

1. セット名を入力し、写真をクリック選択またはドラッグ＆ドロップする。
2. 「このセットを保存」を押す。
3. 実行環境を選び「3Dを作成」を押す。
4. 完了後に「3Dを見る」を開く。PLYのダウンロードも可能。

JPEG・PNG・WebP・HEIC/HEIF・MPO、2〜8枚、合計64MB以内、1枚3000万画素以下に対応します。HEIC/HEIF・MPOは向きを補正し、JPEGに変換して取り込みます。MPOは代表画像のみを使用します。新規セットは最大20件、生成は同時に1件です。既存のヘッドホン・渋谷駅の結果も同じ一覧から閲覧できます。

各カードには全写真を並べて表示します。写真をクリックすると、保存されたフルサイズ画像を別タブで開きます。既存のヘッドホン・渋谷駅も同じ写真付きカードに揃え、生成時に保存された入力画像（`input_*.png`）を表示します。既存結果は閲覧専用です。写真リンクとカード表示はユーザーによる動作確認済みです。

room3dgsから写真選択GUIとWebGL2ビューアをコピーし、DA3処理へ接続しました。元のroom3dgsは変更していません。ビューアのドラッグ回転は、固定距離の点ではなく**モデルの座標範囲の中心**を軸にします。右ドラッグで平行移動、Ctrl+ホイールで前後移動、数字キーで撮影視点へ戻れます。

### 処理時間の見方

| 条件 | 実測 | 計測範囲 |
|---|---:|---|
| 渋谷駅4枚・常駐ROCm FP32 | **約1.91〜1.92秒** | 写真読込・DA3推論・点群化・簡易3DGS保存。アップロード・起動・表示は除外 |
| 同条件のDA3ネットワーク部分 | 約0.356秒 | 上記に含まれる推論のみ |
| 渋谷駅4枚・CPU単発 | 約6.31秒 | Python起動・import・モデル読込・点群/簡易3DGS保存を含む |
| 渋谷駅8枚・CPU単発 | 約10.49秒 | 同上 |
| 渋谷駅4枚・ROCm単発 | 約6.34〜6.82秒 | 同上。FP16/FP32別試行、先行試験後のキャッシュあり |
| ヘッドホン4枚・CPUの初期測定 | 約3.54秒 | DA3内部計測3.38秒＋簡易変換0.16秒。起動・import・背景除去等を除外 |

**常駐化後の約1.9秒と、起動を含む約6秒は計測範囲が異なります。** サーバー起動時のDA3モデル初期化とウォームアップは今回約4秒で、Python起動と一部importは別です。写真アップロードからiPhoneで表示するまでの全体時間は未計測です。各実測の条件・詳細は後半に残しています。

### 使用デバイス

| 処理 | 現在の実装 |
|---|---|
| SigLIP 2分類（独立CLI） | CPU。GUIには未接続 |
| DA3深度・カメラ推定 | 通常起動では常駐ROCm GPU。CPU経路も保持 |
| 点群化・簡易3DGS変換・保存 | CPU |
| 任意の写真最適化 | ROCm GPU |
| ブラウザ表示 | WebGL2。GPU使用の有無はブラウザ環境に依存 |

### iPhone・テザリングからの接続

`./start_all.sh` は既定で `0.0.0.0` に待ち受け、外部接続が有効です。iPhoneから使う場合は、PCをiPhoneのテザリング等の同じネットワークに接続して起動します。PC内限定にする場合は `./start_all.sh --host 127.0.0.1` を使用してください。

```bash
./stop_all.sh
./start_all.sh
```

PCで画面上部の「PCの接続URL」を確認し、iPhoneのSafariでそのURLを開いて写真を選択します。表示例は `http://192.168.0.9:8080/` ですが、このIPは固定値ではありません。画面は接続中のインターフェースのIPv4を取得し、**15秒ごと・フォーカス復帰時**に更新します。ポートを変えた場合も実際のポートを表示します。`0.0.0.0` やiPhone自身の `localhost` をSafariに入力するのではなく、表示されたPCのIPを使ってください。

PC内限定で起動した場合は、その状態も併記します。URL表示機能だけでは外部接続を有効にしません。接続できない場合はPCの接続先・IP・待受設定・ファイアウォールの8080番への到達性を確認してください。MPO対応後、iPhone実機から1152×1536の写真4枚をアップロードできたことをユーザーが確認しました。テザリング経由の接続は別途未確認です。写真GUIが対応するJPEG・PNG・WebP・HEIC/HEIF・MPOを選んでください。

### 保存先と主なファイル

| 保存先・ファイル | 用途 |
|---|---|
| `DA3/checkpoints/`, `DA3/source/` | 固定revisionのDA3重み・公式ソース |
| `DA3/.venv/`, `DA3/.venv-rocm/` | CPU環境とROCm追加依存環境 |
| `DA3/uploads/<ID>/` | GUIの写真・サムネイル・メタデータ・生成結果 |
| `DA3/trash/` | GUIで一覧から削除したセットの退避先 |
| `DA3/outputs/` | ヘッドホン・渋谷駅などCLI試験結果 |
| `viewer/` | コピーしたGUI・WebGL2ビューア・ライセンス表示 |
| `start_all.sh`, `stop_all.sh`, `server_control.py` | サーバーの起動・停止・準備完了確認 |
| `viewer_server.py`, `photo_sets.py`, `da3_runtime.py` | HTTP API・写真セット管理・常駐ROCmモデル |
| `infer_da3.py`, `points_to_3dgs.py` | 深度/点群推論と簡易3DGS変換 |
| `optimize_3dgs.py` | 任意の写真最適化 |
| `reports/` | 検証レポート |
| `run/` | 起動管理ファイル・サーバーログ |

ダウンロード物・生成物・写真・環境・キャッシュは `.gitignore` の `.venv/`、`.cache/`、`/DA3/`、`/FreeSplatter-O/`、`/run/` 等で除外します。取得スクリプト・実行スクリプト・検証コード・ライセンス表示は管理対象です。ライセンスの詳細と固定revisionはモデル別の節に記載しています。

## SigLIP 2分類（独立CLI）

CLIPの実装・比較試験後、採用する重みのライセンスがモデルカードに明示されているSigLIP 2へ切り替えました。比較用CLIPの記録は保持しています。

`google/siglip2-base-patch16-224` を使い、写真を `object`（物体中心）、`room`（室内空間）、`outdoor`（屋外風景）に分類します。既定モデルはSigLIP 2です。追加学習は行っていません。

### SigLIP 2のセットアップ・ダウンロード

```bash
uv venv .venv
uv pip install --python .venv/bin/python torch --index-url https://download.pytorch.org/whl/cpu
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python download_model.py
```

`download_model.py` はHugging Faceからモデルを取得します。初回はネットワークと約1.6GBの空き容量が必要です。既に取得したファイルは再利用します。`requirements.lock` は実測環境のパッケージ一覧です。

モデルID・revision・既定保存先は `model_config.py` で一元管理し、推論とダウンロードで同じrevisionを使用します。

- モデル: `google/siglip2-base-patch16-224`
- revision: `75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2`
- 保存先: プロジェクト直下の `.cache/huggingface/`（実行時の作業ディレクトリに依存しません）
- 取得ファイル: `model.safetensors`、`config.json`、`preprocessor_config.json`、`special_tokens_map.json`、`tokenizer.json`、`tokenizer.model`、`tokenizer_config.json`、配布元の `README.md`（モデルカード）

ダウンロードしたファイル・Hubキャッシュ・ロックファイルはすべて `.cache/` 以下に入り、`.gitignore` で除外します。仮想環境 `.venv/` も除外しています。

```bash
# ネットワークを使わず、必要な取得ファイルの存在を確認
.venv/bin/python download_model.py --local-files-only
```

`--cache-dir` で保存先を変更できます。その場合は推論にも同じ `--cache-dir` を指定してください。独自の保存先をリポジトリ内に設ける場合は、そのディレクトリも `.gitignore` に追加してください。

### 分類の実行

```bash
.venv/bin/python clip_classifier.py /path/to/photos --limit 4 --local-files-only
# モデルを保持して3回計測し、JSONを保存
.venv/bin/python clip_classifier.py /path/to/photos --limit 4 --repeat 3 --local-files-only --output reports/result.json
```

写真はローカルで処理します。複数ファイルの直接指定も可能です。ディレクトリは直下のみ名前順で読み込み、`--limit` を省略すると全画像を処理します。EXIF回転補正とRGB変換を行い、無効なファイルや壊れた画像はエラーにします。

既定はCPU・4スレッド・float32。`ClipClassifier` を一度生成し `classify(paths)` を繰り返すとモデルを常駐できます。`--device cuda` は対応PyTorchが必要で、GPUは未検証です。`--model` では比較用のCLIPを選択できますが、既定の取得スクリプトはSigLIP 2のみ取得します。

### 判定方式と旧ルーティング

各クラス3種類の英文プロンプトから正規化した平均特徴を作り、画像との類似度に学習済みスケールを適用してsoftmaxを取ります。SigLIPのテキストはモデルの最大長にpaddingします。これは本アプリの相対分類スコアで、SigLIP本来のsigmoidスコアや校正済みの正解確率ではありません。共通logit_biasはsoftmaxで相殺されるため省略しています。

写真セットの全画像が物体／シーンのどちらかに十分な差で一致した場合のみ推奨モデルを返します。シーンのスコアはroom + outdoor。既定は最大スコア0.60以上、物体とシーンの差0.15以上。混在・低信頼度は `uncertain` です。しきい値は未校正です。

- 物体 → `FreeSplatter-O`
- シーン → `Depth Anything 3`
- 保留 → 推奨モデルなし

これは比較試験時の `clip_classifier.py` の `recommended_model` 出力です。**物体 → FreeSplatter-Oという旧対応はコードに残っていますが、現在の採用方針ではありません。** 再構成モデル自体は起動せず、GUIもこのルーティングを使いません。現行GUIは物体・シーンともDA3 → 簡易3DGSを使用します。

### SigLIP 2のライセンス

採用したSigLIP 2の重みは、Googleの[固定revisionのモデルカード](https://huggingface.co/google/siglip2-base-patch16-224/blob/75de2d55ec2d0b4efc50b3e9ad70dba96a7b2fa2/README.md)に **Apache-2.0** と明示されています。取得スクリプトは、その表示を含むモデルカードも保存します。

[Apache License 2.0原文](https://www.apache.org/licenses/LICENSE-2.0)に従い、商用利用・改変・再配布が可能です。主な事項は以下です。

- 再配布時はApache License 2.0の全文を受領者に渡す必要があります。READMEのリンクだけで代用しないでください。
- 変更したファイルには変更した旨を明示し、関連する著作権・特許・商標・帰属表示を保持します。
- 配布物にNOTICEが含まれる場合、該当する帰属表示も保持します。
- ライセンスは無保証であり、商標の利用許諾を与えるものではありません。
- 本モデルの利用によって自作アプリのソース公開が要求されることはありません。

この節は採用モデルの条件を説明するものです。PyTorch、Transformers等の依存ライブラリには各自のライセンスが適用されます。本プロジェクト独自コードのライセンスをこの節で新たに指定するものではありません。

### 分類の検証結果（2026-09-21）

AMD Ryzen AI MAX+ 395、CPU 4スレッド、float32、Python 3.14.3、torch 2.14.0+cpu、transformers 4.57.6。同じモデルを保持し各セットを3回処理しました。

| 入力（各4枚） | SigLIP 2の結果 | 常駐2〜3回目 |
|---|---|---|
| ヘッドホン | object | 0.456〜0.460秒 |
| 渋谷駅 | room / scene | 0.455〜0.456秒 |
| 猫のいる部屋 | uncertain | 0.475〜0.476秒 |
| 卓上の玩具 | object | 0.441〜0.442秒 |
| ヘッドホン2枚＋駅2枚 | uncertain | 1回のみ、JSON参照 |

時間には画像読み込み・前処理・推論・判定を含み、Python起動・ライブラリimport・モデル初期化・ダウンロード・JSON書き込みは含みません。キャッシュからのモデル初期化は0.653秒でした。

猫のいる部屋は、壁際の小物を近くから撮影した1枚が物体判定となり、残り3枚と不一致で保留です。通常4セット中3セットは期待ルート、1セットは保留。混在セットの保留も確認しています。以前のCLIPとルート判定は同じで、所要時間は約2.6〜3.1倍でした。少数サンプルのため一般精度は保証しません。この分類試験では屋外専用セット・GPUでの分類速度・分類と再構成を接続した品質は未検証です。

```bash
.venv/bin/python -m unittest discover -s tests -p test_classifier.py -v
HF_HUB_OFFLINE=1 .venv/bin/python evaluate_clip.py
```

単体テスト7件は成功。実画像の評価スクリプトは、このマシンの既存データパスに依存します。部屋が期待するsceneルートにならない既知の評価未達に対して、終了コード1を返します。

生データ: [SigLIP 2](reports/siglip2_evaluation.json)、[従来CLIP](reports/evaluation.json)、[CLIP回帰確認](reports/clip_regression.json)。

## FreeSplatter-Oの取得と試験記録（不採用）

FreeSplatter-Oは、物体の複数写真から3D Gaussian Splattingとカメラパラメータを推定するモデルです。物体検知器ではありません。SigLIP 2で物体中心と判定した写真の、後段の再構成候補として試験しましたが、品質評価により不採用としました。以下は再現用の記録です。

```bash
# SigLIP 2と同じダウンロード用仮想環境を利用
.venv/bin/python download_freesplatter.py
# ネットワークを使わず取得済みファイルとソースrevisionを確認
.venv/bin/python download_freesplatter.py --local-files-only
```

Gitと、上記セットアップで導入するhuggingface-hubが必要です。スクリプトは作業ディレクトリによらず、プロジェクト直下の `FreeSplatter-O/` に保存します。このフォルダ全体を `.gitignore` に登録しています。ダウンロードスクリプト自身は管理対象です。

```text
FreeSplatter-O/
├── source/                         # 公式Gitリポジトリ（設定・コード・ライセンス）
│   ├── LICENSE.txt
│   ├── README.md
│   ├── configs/freesplatter-object.yaml
│   └── ...
└── checkpoints/
    ├── freesplatter-object.safetensors  # 約1.23GB、306Mパラメータ
    ├── README.md                       # 重み配布元のモデルカード
    └── .cache/                         # Hugging Faceの取得メタデータ
```

取得元は以下の固定バージョンです。

- [公式ソース](https://github.com/TencentARC/FreeSplatter): `70ef1ff0a8b618d80aab6eaad3cc580536da2ece`
- [公式重み](https://huggingface.co/TencentARC/FreeSplatter): `728fad7e13bad72d7a47407be523fdb571832e08`
- 取得する重みは標準の `freesplatter-object.safetensors` のみ。2DGS版とシーン用は取得しません。

再実行時には取得済みファイルを再利用します。ソースのrevisionが異なる場合や追跡ファイルに変更がある場合は停止し、変更を上書きしません。オフライン確認はファイルの存在とソースrevision等を確認するもので、重み全体のハッシュ再検証ではありません。

### FreeSplatterのライセンス

公式READMEは**コードとモデルの両方に、Apache 2.0を基にTencent独自の追加条件を設けたライセンス**が適用されると説明しています。Hugging Faceの `apache-2.0` タグだけで標準Apache-2.0と同一と判断しないでください。

[固定バージョンのLICENSE.txt](https://github.com/TencentARC/FreeSplatter/blob/70ef1ff0a8b618d80aab6eaad3cc580536da2ece/LICENSE.txt)には、対象が推論コード・パラメータ・重みであることと、EU域内での使用を意図しない旨が記載されています。利用・配布時にはこの原文を確認し、ライセンスの同梱、関連表示の保持、変更したファイルの明示等の条件に従ってください。原文は `FreeSplatter-O/source/LICENSE.txt` にも保存されます。

また[公式README](https://github.com/TencentARC/FreeSplatter/blob/70ef1ff0a8b618d80aab6eaad3cc580536da2ece/README.md)は、デモで利用するHunyuan3D-1とBRIAAI RMBG-2.0に別の非商用ライセンスがあると説明しています。今回のスクリプトはこれらの追加モデルを取得しません。

### 現在の準備範囲

ソース・物体用重みの取得後、下記のCPU専用経路でGaussian生成まで実行しました。公式推奨環境はCUDA中心で、Radeon 8060SでのGPU推論は未検証です。

公式 `app.py` は追加モデルのダウンロードを行い、重みの参照先も `./ckpts/FreeSplatter` です。下記の専用スクリプトは今回の `checkpoints/` を直接読み込みます。SigLIP 2用のCPU仮想環境に公式CUDA依存をそのまま追加しないでください。

### FreeSplatter-OのCPU推論（2026-09-21）

```bash
.venv/bin/python infer_freesplatter.py /path/to/object/photos --limit 4
# 既定のheadphones出力に対する診断用点群投影図
.venv/bin/python preview_freesplatter.py
```

`infer_freesplatter.py` は公式Transformerを読み込み、xformers AttentionをPyTorch SDPAに置き換えます。公式ソース自体は変更せず、全重みをstrict=Trueで照合します。Attentionの置換は小さなテンソルで明示的なscaled dot-product計算と一致することを確認しました。公式xformers実行とのモデル全体の数値比較は未実施です。

入力は名前順のヘッドホン写真4枚。背景除去なし、EXIF回転補正、白背景合成、全写真を90%の占有率で正方形にパディングし512×512へ縮小しました。公式デモの背景除去・前景切り出しとは条件が異なります。CPU 8スレッド、float32での結果です。

| 処理 | 時間 |
|---|---:|
| モデル構築・重み読み込み | 1.54秒 |
| 画像前処理 | 0.25秒 |
| 推論 | 49.59秒 |
| 出力保存を含む全体 | 53.65秒 |

Python起動・ライブラリimportは含みません。1回の実測で、ウォーム速度の統計ではありません。約10秒の目標は未達です。

生成数1,048,576 Gaussian、opacity > 0.005で306,374個をPLYに保存しました。全出力が有限値であることを確認済みです。保存場所はGit除外対象の `FreeSplatter-O/outputs/headphones/`（`--output`で変更可能）。

- `gaussians.ply`: 標準3DGS属性（SH degree 1、log scale、opacity logits、正規化したwxyz quaternion）。モデルの参照カメラ座標のまま保存。
- `gaussians_raw.npz`: フィルタ前の23次元の生出力。
- `input_00.png`〜`input_03.png`: 実際にモデルへ渡した画像。
- `report.json`: 入力パス・条件・処理時間。
- `point_preview.png`: opacity > 0.05の14,397点をXY/XZ/ZYに投影した診断画像。Gaussian描画ではありません。

投影図ではヘッドホンの輪郭を確認できますが、背景由来の点が多く残っています。opacity > 0.5は53個であり、単純な高しきい値による除去は点を大幅に失います。カメラ推定・Gaussian描画・メッシュ化・寸法精度の検証は未実施で、完成した3Dモデルとしての品質はまだ評価できていません。

### 背景除去して再推論

```bash
.venv/bin/python remove_background.py /path/to/headphone/photos --dark-object
.venv/bin/python infer_freesplatter.py FreeSplatter-O/inputs/headphones_rgba --crop-alpha --output FreeSplatter-O/outputs/headphones_nobg
.venv/bin/python preview_freesplatter.py --directory FreeSplatter-O/outputs/headphones_nobg
```

背景除去はrembg 2.0.85 / U2Net / ONNX Runtime CPUで行います。初回は約176MBの重みを取得し、Git除外済みの `.cache/rembg/` に保存します。元画像は変更せず、透明PNGを `FreeSplatter-O/inputs/headphones_rgba/` に保存します。

U2Netだけではヘッドバンド内側の机が残ったため、今回の黒いヘッドホンに対して `--dark-object` で明るさと茶色系の色による補正を追加しました。この補正は汎用ではなく、白い物体や茶色の物体には使用しないでください。反射部の欠落や影の残留があり、精密なマスクではありません。オプションを外すとU2Netのマスクだけを使います。

推論の `--crop-alpha` はalpha > 127の範囲で切り出し、白背景・90%占有率・512pxに揃えます。ケーブルもマスクに含まれるため、物体本体だけで切り出した比較とは異なります。元の背景あり結果は `outputs/headphones/` に保持します。

rembgのコードは[MIT](https://github.com/danielgatis/rembg)、U2Netの上流リポジトリは[Apache-2.0](https://github.com/xuebinqin/U-2-Net)を表示しています。使用するONNXファイルはrembgの配布物です。この記載はONNX変換重みに関する独立した許諾の確認を代替しません。

背景除去後の実測: 背景除去4枚1.33秒（モデルロード0.18秒を除く）、FreeSplatter推論51.06秒、推論側の読込・出力込み55.06秒。opacity > 0.005で55,420 Gaussianを保存しました。点数の減少だけでは品質改善を示しません。背景除去図は `FreeSplatter-O/inputs/background_removal_preview.jpg`、比較用PLYは `FreeSplatter-O/outputs/headphones_nobg/gaussians.ply` です。

## DA3-BASEの取得・CLI実行・試験記録

現在の採用モデルは **DA3-BASE**。DA3の[公式モデルカード](https://huggingface.co/depth-anything/DA3-BASE)で重みにApache-2.0が明示されており、複数画像の相対深度・カメラ姿勢推定が可能です。DA3-LARGE等は別ライセンスの場合があるため、DA3全体が同条件とは扱いません。

```bash
# 既存の共通環境でソースと重みを取得
.venv/bin/python download_da3.py
.venv/bin/python download_da3.py --local-files-only
# DA3用Python 3.10 / CPU環境を作成
bash setup_da3.sh
# 同じ写真4枚で推論
DA3/.venv/bin/python infer_da3.py /path/to/photos --limit 4
```

固定バージョン:

- [公式ソース](https://github.com/ByteDance-Seed/Depth-Anything-3): `3d835ec1a5802d64a8b8b15f817a1ab54809bfe4`
- [DA3-BASE重み](https://huggingface.co/depth-anything/DA3-BASE): `f4a6c9b3c95e41c82048423d3493a81ec3fa810e`
- 取得ファイル: `model.safetensors`（約542MB）、`config.json`、モデルカード `README.md`

```text
DA3/                                # フォルダ全体を.gitignoreで除外
├── source/                         # 公式ソース、設定、LICENSE
├── checkpoints/                    # 重み・設定・モデルカード・取得メタデータ
├── .venv/                          # Python 3.10のCPU環境
├── .venv-rocm/                     # ROCm用追加依存環境（既存ROCm環境を参照）
├── uploads/                        # GUIで保存した写真と生成結果
├── trash/                          # 一覧から取り除いたセットの退避先
└── outputs/                        # ヘッドホン・渋谷駅・性能試験等の結果
```

取得済みファイルを再利用し、ソースのrevision違いや追跡ファイルの変更がある場合は上書きせず停止します。コードと重みのライセンスはApache-2.0で、原文は `DA3/source/LICENSE`、モデルの指定は取得したモデルカードにあります。配布時のライセンス同梱・関連表示の保持・変更表示等の条件は上記Apache-2.0の説明に従います。

DA3の公式パッケージはPythonバージョンやNumPyの条件が既存環境と異なるため、`DA3/.venv`に分離しました。`requirements-da3.txt`は今回のCPU形状推論に必要な依存を定義し、`requirements-da3.lock`に実測環境の全バージョンを保存しています。公式パッケージ全体をインストールする代わりに、スクリプトから固定ソースを読み込みます。xformers / gsplat / Open3Dは導入していません。gsplatがない旨の起動メッセージは、今回使用しない3DGS描画の依存に関するものです。

### 出力形式と実行条件

DA3-BASEは3DGSを直接出力しません。今回は推定深度を内部パラメータで逆投影し、w2c外部パラメータから共通座標に変換した **RGB点群** を保存します。メッシュやGaussian PLYではないため、3DGS専用ビューアでは表示できない場合があります。

- `scene_points.ply` / `scene_points.glb`: 背景も含めた点群。
- `prediction.npz`: 深度・信頼度・内部/外部パラメータ・処理済みRGB。
- `points.npz`: 点座標・色・入力画像番号。
- `report.json`: 入力パス・時間・条件。
- `input_00.png`等: 処理後の入力画像。

CPUでは公式APIの自動fp16切り替えを使わず、サブクラスから公式ネットワークをfloat32で実行します。重みは共有パラメータに対応する `safetensors.load_model(..., strict=True)` で完全照合しています。画像処理は公式InputProcessorを順次実行し、長辺504・14の倍数にリサイズ、参照画像は先頭（`first`）です。ソースの変更はありません。

### ヘッドホン4枚の結果（2026-09-21）

前回と同じ元写真 `img_000.jpg`〜`img_003.jpg` を背景ありで入力しました。各504×378px、CPU 8スレッド、float32。背景除去画像は入力には使わず、前回のalphaマスクを**推論後の点の選別にだけ**使いました。全画素の信頼度の下位40%を除き、alpha > 127で物体点を選別します。しきい値は初期値で、点数や信頼度だけで品質を保証するものではありません。

| 処理・出力 | 実測 |
|---|---:|
| モデル構築・重み読込 | 0.35秒 |
| ネットワーク推論 | 1.92秒 |
| 前処理・推論・予測変換 | 1.97秒 |
| 読込・点群出力保存まで | 3.38秒 |
| 背景込み点群 | 457,229点 |
| マスクで選別した物体点群 | 75,923点 |

Python起動・ライブラリimport・モデル取得・背景除去・ビューア表示は含まない1回の実測です。「画像投入から初回3D表示まで10秒」の達成を示す計測ではありません。全予測の有限値とカメラ回転の行列式（約1）を確認しました。

```bash
DA3/.venv/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/4b8f82bc/input \
  --mask-dir FreeSplatter-O/inputs/headphones_rgba
DA3/.venv/bin/python preview_da3.py
```

マスクは `NN_<元画像stem>.png` のRGBAで、元写真と同じ画角・画像領域である必要があります。`--mask-dir`指定時は `object_points.ply` / `object_points.glb` も生成します。`preview_da3.py`はこれらから次を生成します。

- `point_preview.png`: 3方向の診断用投影図。
- `viewer.html`: ブラウザで開くオフライン点群ビューア。ドラッグで回転、ホイールで拡大縮小。表示だけ最大4万点に間引き、PLY/GLBには全点を保持。

投影図ではヘッドバンドとイヤーパッドの形を確認できますが、複数表面のずれ・厚み方向の広がりがあり、幾何精度の検証は未完了です。その後の点群・簡易3DGSのユーザー閲覧評価は良好で、現在の基本方式に採用しました。前回の不完全なマスクにも影響されます。未観測の裏面・寸法精度・メッシュ・新規視点の3DGS描画は評価していません。

### DA3点群から3DGS形式への簡易変換

```bash
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/headphones/object_points.ply \
  --output DA3/outputs/headphones/object_3dgs.ply
```

`points_to_3dgs.py`はRGB点群の各点を球状Gaussianに変換し、3DGSのPLY属性形式で保存します。元の点群は変更しません。

- 位置: 点群の座標を維持。完全一致する重複点がある場合のみ色を平均して統合。
- 色: RGBからSHのDC係数へ変換。互換性のためSH degree 3の属性を用意し、高次係数45個はゼロ。
- 大きさ: 近傍3点までの距離のRMSから推定し、既定 `--scale-factor 0.75` を掛ける。極端に大きい孤立Gaussianは上限で抑える。
- 不透明度: 既定 `--opacity 0.8`。PLYにはlogitで保存。
- 向き: 単位quaternion（wxyz）。等方的な球なので向きの影響はありません。

物体点群75,923点を75,923 Gaussianに変換しました。変換約0.16秒、PLY約18.8MB。ファイルを再読み込みし、位置・復元RGB・不透明度・正のスケール・単位quaternion・有限値を検証しました。生成条件は `object_3dgs.json` に保存します。

3DGS用の読み込み属性形式を確認済みで、簡易変換版はユーザーのSculptlyでの閲覧評価で良好でした。ファイル名は **`object_3dgs.ply`** です（元の `object_points.ply` は通常の点群）。この簡易変換版には学習・カメラに合わせた最適化を行っていないため、穴・にじみ・表面ずれが残る可能性があります。写真に合わせた最適化版は次節に記載しています。未撮影部分を埋めたり、形状を修正したりする処理ではありません。粒が大きすぎる場合はscale-factorを下げ、小さく隙間が目立つ場合は上げて別ファイルに出力してください。

### 元写真に合わせた3DGSの最適化

簡易変換の結果はユーザーのSculptlyでの確認で良好だったため、元の `object_3dgs.ply` を保存したまま、4枚の写真に合わせた最適化を追加しました。

**今回の出力: `DA3/outputs/headphones/optimized_conservative/object_3dgs_optimized.ply`**

`optimize_3dgs.py` は、DA3のカメラ内部・外部パラメータと `prediction.npz` 内の処理済み元写真を使います。既存の背景除去alphaで白背景に合成した写真を教師に、色（SHのDC）、不透明度、球状Gaussianの大きさをAdamで学習します。点の位置・カメラ・向き・高次SH係数は固定です。Gaussianは増減せず75,923個を保持します。

良かった形を維持するため、RGBの変化は各チャンネル±0.1（0〜1）、大きさは初期値の0.67〜1.5倍に制限します。損失はマスクで重み付けしたRGBのL1誤差、alphaの輪郭誤差、初期値からの変化に対する正則化です。初期試行では色むらが出たため、色の変化を制限した `optimized_conservative` を今回の確認対象としています。

描画はこのプロジェクトのPyTorch実装です。透視投影の共分散、0.3 pixel²の低域フィルタ、奥行き順のfront-to-back alpha合成を使います。学習時は8×8画素タイルを16個ずつサンプリングし、評価時は4枚の全画素を描画します。等方Gaussian・DC色専用で、異方Gaussianや高次SHの入力は受け付けません。gsplatのビルドや追加学習済み重みは不要で、DA3や背景除去モデルのライセンス条件は前述のとおりです。

今回使った既存ROCm環境での再実行（環境の中身は変更しません）:

```bash
/home/your-user/RealtimeDepth/.venv-rocm10/bin/python optimize_3dgs.py \
  --input DA3/outputs/headphones/object_3dgs.ply \
  --prediction DA3/outputs/headphones/prediction.npz \
  --mask-dir FreeSplatter-O/inputs/headphones_rgba \
  --output-dir DA3/outputs/headphones/optimized_conservative \
  --steps 4000
```

依存はPyTorch・NumPy・Pillowです。別環境では対応するPyTorchを用意し、Python実行パスを置き換えてください。`--device cpu` でも動作可能ですが、下記はRadeon 8060S / PyTorch 2.13.0+rocm10.0.0での実測です。`setup_da3.sh` のCPU環境にGPU版PyTorchをインストールする処理は追加していません。

マスクは `--mask-dir` 内のPNGをファイル名順に読み、予測画像と1対1に対応させます。元写真と同じ画像領域のRGBAが必要です。今回の4枚は504×378pxで学習・評価し、マスクは同解像度にリサイズしています。

| 指標（4枚の学習画像） | 最適化前 | 最適化後 |
|---|---:|---:|
| 物体領域のRGB平均絶対誤差（0〜1） | 0.09246 | 0.06422 |
| 物体領域のPSNR | 16.34 dB | 17.59 dB |
| 白背景を含む全画像のRGB平均絶対誤差 | 0.04979 | 0.02537 |
| 白背景を含む全画像のPSNR | 15.40 dB | 18.79 dB |

物体領域はalpha > 0.5で集計し、平均絶対誤差は約30.5%減りました。4,000反復の学習約34.1秒、準備・前後描画・保存まで約38.0秒です。Python起動・import・DA3推論・背景除去は含みません。今回は品質確認のための処理で、10秒以内の一連の処理は達成していません。

出力フォルダには次を保存します（`/DA3/` 全体が `.gitignore` 対象）。

- `object_3dgs_optimized.ply`: 最適化済み3DGS。Sculptlyで開くファイル。
- `comparison.jpg`: 左から教師写真（背景除去済み）、最適化前、最適化後。上から4視点。
- `target_00.png`〜 / `before_00.png`〜 / `after_00.png`〜: 各視点の個別画像。
- `report.json`: 条件、指標、実行時間、損失履歴、PLY書き戻し検証結果。

前後の比較画像を確認し、色むら・輪郭外のにじみが減る一方、細部の欠け・多重表面・カメラと形状のずれが残っています。上記は**同じ4枚の学習画像への適合度**で、未撮影視点の品質改善を保証する指標ではありません。Sculptlyとは描画条件が異なる可能性があり、最適化版のSculptlyでの外観はまだ確認していません。

検証では、合成の前後関係・カメラ背後の除外・透明度と大きさの勾配を解析値/数値差分と照合する3テストが通過しました。PLY再読込後の座標は元と完全一致し、再読込した属性による描画と学習直後の描画の最大差は1.8×10⁻⁷でした。

```bash
/home/your-user/RealtimeDepth/.venv-rocm10/bin/python -m unittest discover \
  -s tests -p test_3dgs_renderer.py -v
```

### 渋谷駅の簡易3DGS試験（2026-09-21）

既存セット `/home/your-user/room3dgs/data/sets/7c57ca12/input` の写真を使い、同じDA3-BASE → 点群 → 簡易3DGS変換を実行しました。4枚版はファイル名順の `img_000.jpg`〜`img_003.jpg`、8枚版は `img_000.jpg`〜`img_007.jpg` です。背景除去・写真への最適化は行っていません。

共通条件: CPU 8スレッド、float32、各504×378px、参照画像は先頭、全画素の信頼度下位40%を除外、Gaussian opacity=0.8、scale-factor=0.75。

| 実測項目 | 4枚 | 8枚 |
|---|---:|---:|
| DA3ネットワーク推論 | 1.95秒 | 4.40秒 |
| DA3読込・推論・点群保存（内部計測） | 3.21秒 | 6.59秒 |
| 点群から簡易3DGS変換（内部計測） | 0.66秒 | 1.46秒 |
| **起動・import・保存を含む2プロセスの一括経過時間** | **6.31秒** | **10.49秒** |
| Gaussian数 | 457,229 | 914,458 |
| 3DGS PLYサイズ（十進MB） | 113.4 MB | 226.8 MB |

一括経過時間は、親プロセスからDA3推論と変換を順次起動して測定しました。両方のPython起動・import、モデル読込、画像読込・前処理、点群と3DGSのファイル保存を含みます。モデル等のダウンロード、分類、プレビュー生成・ビューア表示は含みません。各条件1回の実測で、OSキャッシュ等によって変動します。前述のヘッドホン約3.54秒は内部時間の合計なので、一括経過時間とは計測範囲が異なります。

出力:

- `DA3/outputs/shibuya_4views/scene_3dgs.ply`: 4枚版の簡易3DGS。
- `DA3/outputs/shibuya_8views/scene_3dgs.ply`: 8枚版の簡易3DGS。
- 各フォルダの `scene_points.ply` / `.glb`: 通常のRGB点群。
- `point_preview.png` / `viewer.html`: 点群の診断用投影図とオフラインビューア。Gaussianの描画ではありません。
- `report.json` / `scene_3dgs.json` / `pipeline_timing.json`: 推論・変換条件と内訳・一括経過時間。

点群投影では壁画・柱・床・天井が確認できます。4枚版にも欠けや面のずれがあり、8枚版では異なる視点の面の重なり・ずれが目立ちます。8枚はより広い方向を撮影しているため、枚数と撮影範囲の両方が変わっています。8枚なら品質が上がるとは判断していません。PLY全属性の有限値、正のスケール、単位quaternion、カメラ回転の行列式（約1）を検証済みですが、これらは幾何精度の保証ではありません。この試験後、ユーザーから渋谷駅も「よくできている」との閲覧評価があり、ヘッドホンと併せて簡易方式を継続する判断になりました。4枚版と8枚版の個別の評価差は未確認です。

再実行例（8枚版はlimitと出力フォルダを変更）:

```bash
DA3/.venv/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/7c57ca12/input \
  --limit 4 --output DA3/outputs/shibuya_4views
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/shibuya_4views/scene_points.ply \
  --output DA3/outputs/shibuya_4views/scene_3dgs.ply
DA3/.venv/bin/python preview_da3.py --directory DA3/outputs/shibuya_4views \
  --cloud scene_points.ply --label '渋谷駅・4枚 DA3点群'
```

`preview_da3.py` は `--cloud` で点群を選べるようにしました。省略時は物体点群があればそれを使い、なければシーン点群を使います。`--label` はHTMLビューアの表示名です。全生成物は既存の `/DA3/` の `.gitignore` 設定で除外されます。

### ローカル3DGSビューア（room3dgsから移植）

`/home/your-user/room3dgs/static/` のWebGL2ビューアを `viewer/` にコピーしました。元プロジェクトは変更していません。CDNは使わず、ヘッドホン簡易版・最適化版と渋谷駅4枚・8枚のうち生成済みの結果を一覧表示します。

```bash
DA3/.venv/bin/python viewer_server.py --port 8080
```

上記は手動起動の例です。通常は `./start_all.sh` / `./stop_all.sh` を使用します。ブラウザで **http://127.0.0.1:8080/** を開き、結果を選択してください。手動起動の停止はそのターミナルでCtrl+C。別のポートは `--port` で指定できます。Python・NumPy・Pillowを使います。`viewer_server.py` の手動起動は既定でローカルホスト限定、`./start_all.sh` は既定で外部接続有効です。既存の生成物はそのまま配信します。写真GUIから新しく保存・生成する操作は「写真を選択するGUI」の節のとおりです。

- ドラッグ: モデル中心を軸に回転。右ドラッグ: 平行移動。
- Ctrl+ホイール: 前後移動。通常のホイール: 回転。
- WASD・矢印: 移動。Space/Shift: 上下。
- 数字0〜7: 対応する撮影視点へ移動（写真枚数の範囲内）。
- PLYダウンロードボタンで表示中の生成物を保存できます。

DA3のカメラ姿勢を読み、先頭写真の視点から表示します。標準3DGSのPLYをブラウザのworkerで変換・深度ソートしてGaussian描画します。点群ビューアの `viewer.html` とは別物です。高次SHによる視点依存色はこのレンダラでは使用しません（今回の簡易PLYは高次SHがゼロ）。WebGL2が必要で、8枚版は約227MBをブラウザへ読み込みます。

移植元・変更内容は `viewer/NOTICE.md` に記録しました。room3dgs由来部分のApache-2.0ライセンスと、レンダラ [antimatter15/splat](https://github.com/antimatter15/splat) のMITライセンス（Copyright © 2023 Kevin Kwok）を `viewer/licenses/` に同梱しています。

移植後、ヘッドレスChromiumで一覧表示・ヘッドホン簡易版・渋谷駅4枚版/8枚版のGaussian描画・数字キーによる視点切り替えを確認しました。ページのJavaScript例外は0件でした。描画スクリーンショットは `DA3/outputs/viewer_headphones.png`、`viewer_shibuya4.png`、`viewer_shibuya8.png` に保存しています。

ビューアの回転中心は、読み込んだGaussianのXYZ座標のバウンディングボックス中心です。ドラッグ・通常ホイール・1本指のタッチ回転で共通の中心を使います。パン・ズーム後もモデル中心を軸に回転します。回転行列の検証は `node tests/test_viewer_orbit.cjs` で実行できます。

### DA3のROCm推論（Radeon 8060S、2026-09-21検証）

`infer_da3.py` に `--device rocm` と `--dtype float32|float16` を追加しました。CPU版は `--device cpu --dtype float32` で、既定値もCPU/float32のままです。ROCmはPyTorch API上では `cuda` デバイスとして動作し、レポートには `backend: rocm` を記録します。重み・モデル・前処理・参照視点はCPU版と共通で、DA3公式ソースの変更はありません。

既存のROCm環境を読み取り専用で参照し、DA3用の追加依存だけをプロジェクト内に入れます。

```bash
bash setup_da3_rocm.sh
```

- 作成先: `DA3/.venv-rocm/`。CPU用 `DA3/.venv/` は保持。
- 参照元: 既定 `/home/your-user/RealtimeDepth/.venv-rocm10/bin/python`。`ROCM_PYTHON` 環境変数で変更可能。
- 検証環境: Python 3.14.3、PyTorch 2.13.0+rocm10.0.0、torchvision 0.28.0+rocm10.0.0、NumPy 2.5.2、AMD Radeon 8060S Graphics。`torch.version.hip` は7.15.26333。
- `rocm_base.pth` で既存環境のパッケージを参照します。参照元環境を削除・移動すると再設定が必要です。このスクリプト自体はROCm本体やドライバをインストールしません。
- `requirements-da3-rocm.txt` は追加パッケージの固定版一覧です。`--no-deps` で導入し、依存解決によるROCm版torchの置換を防ぎます。torch・torchvision・NumPy・OpenCVは既存環境から供給します。異なるPython/ROCm環境ではこの組合せの再検証が必要です。
- 環境・ダウンロード物・検証出力は既存の `/DA3/` と `/.cache/` の除外設定内です。DA3の重みを追加取得する必要はなく、ライセンス条件も変更ありません。

渋谷駅4枚の例:

```bash
DA3/.venv-rocm/bin/python infer_da3.py /home/your-user/room3dgs/data/sets/7c57ca12/input \
  --limit 4 --device rocm --dtype float32 --output DA3/outputs/shibuya_4views_rocm
DA3/.venv/bin/python points_to_3dgs.py DA3/outputs/shibuya_4views_rocm/scene_points.ply \
  --output DA3/outputs/shibuya_4views_rocm/scene_3dgs.ply
```

`--dtype float16` はGPUのautocastによる混合精度推論です。CPU版に近い精度を優先する場合はfloat32を使用してください。GPUが利用できない場合はエラーにし、CPUへの暗黙のフォールバックはしません。点群化・PLY出力・簡易3DGS変換は引き続きCPU処理です。

`--repeat 3` で同じモデルを保持して推論を3回実行し、最後の予測だけを保存できます。`report.json` の `inference_runs` に各回の時間を記録します。GPUの開始前・終了後に同期して計測するため、単なる非同期カーネル投入時間ではありません。`total_seconds` はimport後から保存までで、repeatを指定した場合は全反復を含みます。

#### 推論速度・精度

渋谷駅4枚、各504×378px、3回連続実行時のネットワーク推論時間:

| 実行環境 | 1回目 | 2回目 | 3回目 |
|---|---:|---:|---:|
| CPU float32・8スレッド | 1.86秒 | 1.71秒 | 1.77秒 |
| ROCm float32 | 6.87秒 | 0.41秒 | 0.35秒 |
| ROCm float16 | 1.17秒 | 0.25秒 | 0.17秒 |

GPU float32の最初の試験は初期化・初回カーネル準備の影響を含みます。float16はその後に実行したため、完全に同じコールド状態の比較ではありません。ウォーム時のfloat32推論はCPUに対して約4〜5倍高速でした。ヘッドホン4枚でもfloat32で1.02 / 0.40 / 0.36秒、75,923物体点を得ました。GPUの最大allocated memoryは約1.4〜1.7GBで、ドライバなどを含むGPU全体の消費量ではありません。

CPU float32との深度の平均相対差は、渋谷駅GPU float32で約0.000034%、ヘッドホンGPU float32で約0.000031%、渋谷駅GPU float16で約0.0100%でした。処理済み入力画像は一致し、深度・信頼度・内部/外部パラメータの有限値とカメラ回転を検証しました。CPU経路の回帰確認では、元の渋谷駅の予測配列と完全一致しています。これはCPU実装との差の検証で、実世界の正解に対する精度評価ではありません。

#### 起動から簡易3DGS保存まで

上記試験後に新しいPythonプロセスを起動し、DA3推論 → CPUでの簡易3DGS変換を順次測定しました。

| 渋谷駅4枚 | 推論プロセス全体 | 変換プロセス全体 | 合計 |
|---|---:|---:|---:|
| ROCm float32 | 5.96秒 | 0.85秒 | **6.82秒** |
| ROCm float16 | 5.52秒 | 0.83秒 | **6.34秒** |
| 以前のCPU float32 | 5.49秒 | 0.82秒 | **6.31秒** |

両Python起動・import、モデル読込・初期化、画像前処理、推論、点群・3DGS保存を含む各1回の実測です。分類・背景除去・ビューアは含みません。GPU測定時のディスク/カーネルキャッシュは既に使われた状態です。**現状の単発実行では全体の高速化は確認できていません。** 推論自体の短縮を全体に反映するにはモデルを常駐させる構成が有効ですが、この測定時点では常駐サービスを使っていません。後述の `start_all.sh` ではROCmモデル常駐に対応しました。

測定・比較結果は `reports/da3_rocm_comparison.json` に保存しています。検証用生成物は `DA3/outputs/rocm_test/` 内の `fp32_headphones/`、`pipeline_float32_shibuya4/`、`pipeline_float16_shibuya4/` に保存し、採用済みのCPU生成物とビューアの既定一覧は変更していません。


### 写真を選択するGUI（room3dgsから移植）

room3dgsの `index.html` / `app.js` をコピーし、トップページに写真セットの選択・ドラッグ＆ドロップ・保存・生成・表示を追加しました。元のWorldMirror再構成サーバーは使用せず、`photo_sets.py` が現在のDA3 → 点群 → 簡易3DGSを実行します。元のroom3dgsのファイルは変更していません。

通常の起動はROCmモデルを常駐させるスクリプトを使います。

```bash
./start_all.sh
```

1. http://127.0.0.1:8080/ を開く。
2. セット名を入力し、同じ対象の写真を2〜8枚選択する（推奨はまず4枚）。
3. 「このセットを保存」を押す。
4. 保存されたカードでCPUまたはGPU（ROCm）を選び、「3Dを作成」を押す。
5. 完了したら「3Dを見る」で開く。ビューアからPLYをダウンロードできる。

JPEG・PNG・WebP・HEIC/HEIF・MPO、合計64MB以内、1枚3000万画素以下に対応します。写真はブラウザで選択した順序で保存し、ファイル名をサーバー側で付け直します。現時点のGUI生成は**背景を含むシーン全体の簡易3DGS**です。SigLIP分類、背景除去、写真への追加最適化は自動実行しません。

`start_all.sh` で起動した場合、新規セットの既定はウォームアップ済みGPU（ROCm）です。従来どおり `viewer_server.py` を直接起動した場合はCPUが既定です。GPUは `setup_da3_rocm.sh` で用意した環境とGPUへのアクセスが必要で、FP32を使います。生成は同時に1件です。他の生成中はエラーを表示するので、完了後に再実行してください。進行状況・完了/失敗はカードに反映し、完了時は生成処理の経過時間とGaussian数も表示します。

- 新規セット: `DA3/uploads/<ID>/input/` に取り込んだ写真（HEIC/HEIF・MPOは変換後のJPEG。元のコンテナ形式は保持しません）、`thumb/` にサムネイル、`meta.json` に状態を保存。
- 生成結果: 同フォルダ内の `runs/<実行ID>/`。再生成時も以前の結果を残し、成功した結果に表示先を切り替えます。失敗した再生成で以前のPLYを失うことはありません。
- ログ: 各実行フォルダの `generation.log`。停止による中断は次回起動時にエラーとして表示し、手動で再生成できます。
- 「一覧から削除」は写真と結果を `DA3/trash/` に退避します。完全削除やGUIからの復元は実装していません。
- 新規セットの上限は20件。既存のヘッドホン・渋谷駅4結果は別枠の閲覧専用で、GUIから再生成・削除しません。
- すべての写真・生成物は `/DA3/` の既存 `.gitignore` 対象です。

ヘッドレスChromiumで写真4枚の選択・保存、CPU生成、ROCm再生成、3D表示、PLYダウンロード応答、一覧からの退避を確認しました。検証用セットの生成はCPU約6.4秒、ROCm約6.8秒でした。写真アップロード・ブラウザ読込を含まない生成処理だけの値です。JavaScript例外は0件で、アップロード検証・パス制限・退避時のファイル保持・実行中削除拒否・中断復帰を確認する5テストも通過しました。

```bash
DA3/.venv/bin/python -m unittest discover -s tests -p test_photo_sets.py -v
```


現在の写真セットテストは7件通過しています。HEIC画像4枚のJPEG変換、MPOの代表画像取り込みと向きの補正も含みます。画像の読み込みに失敗した場合は、画面に写真番号と判定形式を表示し、`run/server.log` に詳細な例外を記録します。今回のiPhoneアップロード失敗はMPO対応で解消しました。HEIC変換は生成したテスト画像で検証しています。

### サーバーの起動・停止とROCm初期化

```bash
./start_all.sh
# 起動完了後: http://127.0.0.1:8080/

./stop_all.sh
```

`start_all.sh` はバックグラウンドにサーバーを起動し、**ROCm初期化・DA3-BASE読込・ウォームアップ完了を待ってから成功を返します**。単に初期化用Pythonを起動して終了する方式ではなく、`da3_runtime.py` がサーバー内にGPUモデルを保持します。GUIからのROCm生成も同じ専用スレッド・モデルを再利用し、点群から簡易3DGSへの変換も同一プロセス内で行います。新規セットのGUIではGPUが既定になり、CPUも選択できます。既存セットで選択済みの実行環境は保持します。

ウォームアップは4枚・504×378・float32の合成入力を2回推論します。入力写真や生成物を作成・変更しません。異なる枚数や縦横比など、未実行の形状では追加の初回処理が発生する場合があります。新しい重みのダウンロードは行いません。事前に `download_da3.py` と `setup_da3_rocm.sh` を実行しておく必要があります。

- 起動先: 既定 `0.0.0.0:8080`（外部接続有効）。PCでは `http://127.0.0.1:8080/` でもアクセスできます。
- ログ: `run/server.log`（追記）。準備状況: `/api/health`。
- 管理ファイル: `run/server.json` / `run/server.pid`。ログとともに `.gitignore` 対象。
- 起動待ち: 既定180秒。失敗・タイムアウト時は開始したプロセスを片付け、終了コード1で返します。GPUなしの場合にCPUへ自動変更はしません。
- 二重起動: 同じ設定ですでに起動済みなら、そのURLを表示して終了します。設定を変える場合は先に停止してください。
- 停止: PID・プロセス開始時刻・起動識別子を照合し、このスクリプトが起動した専用プロセスグループを停止します。常駐モデルと実行中のCPU子プロセスも終了します。写真や完了済み結果は削除しません。実行中に止めたセットは次回起動時に中断エラーとして扱います。
- PIDが古い場合でも他のプロジェクトを名前検索して一括停止しません。手動で起動した旧サーバーは、そのターミナルで停止してから切り替えてください。

任意の指定:

```bash
./start_all.sh --host 127.0.0.1     # このPCからの接続に限定
./start_all.sh --port 8081          # ポート変更（HOST/PORT環境変数も使用可能）
./start_all.sh --cpu                # ROCm常駐・ウォームアップを省略
./start_all.sh --timeout 300        # 起動待ち時間を変更
```

`--cpu` 起動時のROCm選択は従来の都度起動経路になります。GPU常駐を使う場合は通常の `./start_all.sh` を使用してください。スクリプトは別ディレクトリから絶対パスで実行してもプロジェクトを基準に動作します。Linuxの `/proc`・プロセスグループとPython標準ライブラリで管理し、systemdやsudoは使いません。

#### 常駐後の実測

起動時のモデル読込・ウォームアップを済ませた後、GUIと同じAPI経由で渋谷駅4枚を2回生成しました。

| 常駐ROCm FP32 | 1回目 | 2回目 |
|---|---:|---:|
| DA3ネットワーク推論 | 0.356秒 | 0.356秒 |
| 写真読込 → 点群 → 簡易3DGS保存 | **1.914秒** | **1.923秒** |

両回でサーバーのPIDが同じ、`resident_model=true`、各生成のモデル読込時間0秒であることを確認しました。アップロード・HTTP待ち・ビューア読込・サーバー起動はこの時間に含みません。起動時のモデル初期化・ウォームアップは今回約4.0秒（その前のPython起動と一部importを除く）でした。

同じCPU基準結果との深度平均絶対差は3.2×10⁻⁷で、Gaussian数457,229も一致しました。CPU CLI経路も既存の予測配列と完全一致しています。実行結果は `reports/resident_rocm_test.json` に記録しました。起動・二重起動・停止・ポート競合時の失敗後処理を実行確認し、この測定時点では、管理対象でないPIDを停止しない4テストと写真セットの5テストが通過しました。

```bash
DA3/.venv/bin/python -m unittest discover -s tests -p test_server_control.py -v
```


写真選択画面の上部には、PCの現在のIPv4アドレスとサーバーのポートから作る接続URLを表示します。15秒ごとと画面にフォーカスが戻ったときに更新します。現在PC内限定で起動している場合は、その旨を併記します。iPhone等から接続する場合は `./stop_all.sh` の後に `./start_all.sh` で起動し、同じネットワークから表示されたURLを開いてください。IP表示機能だけでは待受設定を変更しません。
