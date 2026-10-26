# モデル候補の調査

確認日: 2026-10-26。実在確認には配布元のモデルカードとHugging Face APIのファイル一覧を使用し、コミット・LFS SHA-256・サイズをカタログに記録しました。検索結果のサマリーだけで配布ファイルを決めていません。

| 項目 | Qwen候補 | JoyCaption候補 |
|---|---|---|
| 元モデル | huihui-ai/Huihui-Qwen3-VL-4B-Instruct-abliterated | fancyfeast/llama-joycaption-beta-one-hf-llava |
| 基盤 | Qwen3-VL-4B-Instruct | Llama-3.1-8B-Instruct＋SigLIP2 |
| 使用GGUF | noctrex/Huihui-Qwen3-VL-4B-Instruct-abliterated-GGUF | concedo/llama-joycaption-beta-one-hf-llava-mmproj-gguf |
| 固定コミット | `0e204140ef43727fb4ee4d4bbd88c948c64719df` | `acfe6bf78ae4e411cd5c7c8f4a71ba01f26a5b97` |
| 言語側 | Q4_K_M、2,497,282,240 bytes | Q4_K、4,920,735,936 bytes |
| 画像側 | mmproj-F16、836,180,576 bytes | mmproj-model-f16、877,771,808 bytes |
| 位置づけ | 軽量な比較候補、採用は暫定 | キャプション特化、現在の初期モデル |

## 実在と配布元

Qwen元モデルは [Huihuiのモデルカード](https://huggingface.co/huihui-ai/Huihui-Qwen3-VL-4B-Instruct-abliterated) でimage-to-text、abliterated、Apache-2.0の表記を確認しました。[noctrex量子化版](https://huggingface.co/noctrex/Huihui-Qwen3-VL-4B-Instruct-abliterated-GGUF) は元モデルへの参照と対応mmprojファイルを保持しています。モデルカードはF32画像側を推奨していますが、12GB環境の余裕を考えて現版はF16を選んでいます。この差の品質影響は未評価です。

JoyCaptionの [開発元モデルカード](https://huggingface.co/fancyfeast/llama-joycaption-beta-one-hf-llava) と [公式コード](https://github.com/fpgaminer/joycaption) は、拡散モデル学習用キャプション、SFW／NSFWの双方、写真・アニメ等の対象範囲を説明しています。開発元の主張であり、本アプリでの品質保証ではありません。[concedo配布](https://huggingface.co/concedo/llama-joycaption-beta-one-hf-llava-mmproj-gguf) には言語モデルと画像プロジェクターが揃っています。

調査したmradermacher量子化リポジトリには言語モデルのみがあり、対応画像側がありませんでした。そのため、自動導入には同一配布内で両ファイルを固定できるconcedo版を選んでいます。同版のカードはKoboldCpp向けと説明しているため、llama.cppでの動作は実機試験結果で別途確認します。

## ライセンス確認の範囲

- Qwen元モデルはApache-2.0表記です。量子化版のカードには別の明確なライセンスタグがないため、元モデルの表示・通知を確認した上で扱います。本アプリはモデルを再配布せず配布元から取得します。
- JoyCaptionの [コードのLICENSE](https://github.com/fpgaminer/joycaption/blob/main/LICENSE) はApache-2.0です。ただしコードのライセンスと重みの条件は別です。モデルカードはLlama 3.1とSigLIP2を基盤としており、JoyCaption／GGUFのメタデータには明確な重みライセンスタグがありません。
- JoyCaptionについて「無条件で商用利用・再配布可能」とは判定していません。重みの配布を製品に含める前に [Meta Llama 3.1のライセンス](https://github.com/meta-llama/llama-models/blob/main/models/llama3_1/LICENSE) と画像エンコーダーの条件、元作者の重みへのライセンス指定を確認する必要があります。
- エンジンは [llama.cpp](https://github.com/ggml-org/llama.cpp) のMITライセンスです。CUDAランタイム・PySide6等には個別の条件があり、配布用EXE化時に必要な文書を同梱する計画です。

## 推論互換性

[llama.cppの公式説明](https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md) に従い、言語GGUFと対応mmprojを同時に読み込みます。画像はOpenAI互換のローカルchat completionsへdata URIで渡します。テキスト専用Qwen3-4Bは代用しません。

Windows x64 / CUDA 12.4の [b11887リリース](https://github.com/ggml-org/llama.cpp/releases/tag/b11887) を固定しています。マルチモーダル機能は開発元も破壊的変更の可能性を明記しているため、単に常に最新版を取得する構成にはしていません。実測は `evaluations/*-evaluation.json` に保存します。

今回の実機試験では、両候補とも画像入力と必須フィールドを持つJSON出力に成功しました。合成画像での速度・品質の観測は [動作確認結果](VALIDATION.md) にまとめています。

## 品質と採用判断

実装開始時にはRTX 4070 12GBでの導入容量と余裕からQwen4Bを初期値にしていました。その後、ユーザー指定により初期値をJoyCaptionへ変更しました。保存済み設定がある場合はそのモデルを復元します。JoyCaptionは用途との一致が強い一方、8Bのメモリ負荷と量子化・テンプレート互換性を評価する必要があります。

実機の合成画像試験はモデル読込、画像入力、JSON成功、基本的な形・色の観測を確認するものです。成人向け画像の正確さ、キャラクター識別、画風の省略精度を評価するデータは提供されていません。両者の品質順位と最終採用モデルは、その評価が終わるまで確定しません。
