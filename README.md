# Test Gate MVP — Markdown表 + 決定的なAnalyzer/Gate

> **対象:** 新プロジェクトにコピー可能な最小構成。人間が編集するのはMarkdown表、判定するのはPython標準ライブラリ。AIは情報の探索とルール候補の作成を補助するが、毎回の合否を判断しない。

## なぜ作ったか

AIでテストを生成・実行できても、期待値が正しい仕様に基づくとは限らない。そこで「仕様とコードの食い違いを機械的に点検するAnalyzer」と「人間が承認した期待値の出典・未決事項を機械的に確認するGate」を、最小のファイル数で運用する。

**注意:** このMVPが判定するのは、仕様アンカーの存在、仕様ファイルの改訂、実装アンカーの存在、承認状態、未決事項である。コードの実行経路や仕様と期待値の意味的な同値性は証明できない。根拠の意味的な支持関係は人間が承認する。

## ファイル

```text
test-gate-mvp/
├── README.md               # 概要・実行手順
├── CLAUDE_PROMPTS.md       # 短い工程別プロンプト5つ
├── SPEC_INDEX.md           # 仕様の正本と実装/既存テストの対応
├── OPEN_QUESTIONS.md       # 人間が決定する未規定事項
├── TEST_RULES.md           # 承認した期待値・根拠（Markdown表）
├── ANALYZER_AND_GATE.md    # 判定モデル・制約
├── check.py                # Deterministic Analyzer + Gate
└── tests/test_check.py     # 自動回帰テスト
```

## 使い方

**新プロジェクトへコピーする場合:** `SPEC_INDEX.md`に正規仕様と対象機能を1〜3件だけ記載。 `OPEN_QUESTIONS.md`は未決事項を記録。 `TEST_RULES.md`にはルールを `pending` で追加。仕様の原文・期待値の導出を人間が確認し、承認状態を `approved` に変更する。

```bash
# pendingのルールに現在の仕様ファイルのSHA-256を固定（実ファイルがある場合）
python3 test-gate-mvp/check.py --stamp R-001

# 仕様出典・実装アンカー・承認・未決事項を確認
python3 test-gate-mvp/check.py

# HOLD、実装DRIFT、ルール未登録を非ゼロで通知（CIへの導入は任意）
python3 test-gate-mvp/check.py --strict

# スクリプト自体の回帰テスト
python3 -m unittest discover -s test-gate-mvp/tests -v
```

現時点ではTEST_RULES.mdの表は空。**新しいプロジェクトの正規仕様やルールを捏造して記入していない**ため、初回の通常実行はルール未登録を表示し、 `--strict` は失敗する。

### Analyzerの結果

| 値 | 意味 |
| --- | --- |
| `ANCHOR_FOUND` | 指定文字列がソースに1回存在（実装の動作・仕様適合の証明ではない） |
| `DRIFT` | 文字列が存在しない、または複数出現して一意に確認できない |
| `UNVERIFIED` | 出典・参照先が未登録、または読めない |

仕様ファイル全体のSHAも確認し、承認時から変わった場合はGateをHOLDする。

### Gateの結果

| 値 | 意味 |
| --- | --- |
| `ALLOW` | approved・仕様の原文アンカー一意・SHA一致・関連未決事項なし。**人間が期待値の意味を確認済みという前提** |
| `HOLD` | 未承認、仕様ドリフト、出典不足、未決事項など。仕様適合のassertionを確定しない |

実装アンカーがDRIFTでも、正しい仕様のオラクルを無効化しないためGateはALLOWになりうる。この場合は実装側の調査が必要で、 `--strict` では終了コード1となる。

終了コードは `0` = 正常終了（通常モードはHOLDでも0）、`1` = strictでHOLD/実装DRIFT/ルールなし、`2` = 不正な表・入出力エラー。

## 人間とAIの分担

| 主担当 | 判断・作業 |
| --- | --- |
| 人間 | 仕様の正本・適用範囲、OPEN_QUESTIONSの決定、TEST_RULESの期待値と原文の対応を承認 |
| AI | 仕様/コードの探索、SPEC_INDEXやTEST_RULESのpending追加案、調査結果の説明 |
| check.py | 参照・SHA・承認状態・未決事項の決定的な確認 |

**仕様決定はOPEN_QUESTIONS.mdにだけ閉じ込めず、承認済みIssue/仕様/ADRの正本へ反映する。** `--stamp` はSHAを記録するだけで承認しない。

## 導入方針

1機能・1PRから始める。CI/新しいテスト生成器/外部LLM APIは導入しない。今あるテストランナーと併用できるが、このMVPではテスト実行結果を自動評価しない。仕様の曖昧さに気付けるか、根拠が古いときに保留できるか、人間の保守負荷が小さいかを確認する。

## Claude Codeへの指示（短い工程に分割）

一括プロンプトは使用しない。**[CLAUDE_PROMPTS.md](CLAUDE_PROMPTS.md) の Prompt 1〜5 を必要な工程ごとに渡す**。

- Prompt 1：仕様・対象機能の参照先の確認
- Prompt 2：Markdown表へのルール候補追加と人間の承認
- Prompt 3：決定的Analyzerの確認
- Prompt 4：決定的Gateの確認
- Prompt 5：単体テスト・運用確認

既に実装済みならPrompt 3・4を再実装する必要はなく、Prompt 1→2→5で試す。各工程で成果物・未決事項・完了条件を確認してから次に進む。

詳細な上位設計は [../docs/evidence-based-test-generation/](../docs/evidence-based-test-generation/) にあるが、このMVPの利用には必須ではない。
