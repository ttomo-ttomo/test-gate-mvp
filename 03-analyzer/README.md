# Analyzer / Gate の使い方

> 全体像は [../README.md](../README.md)。仕組みは [ANALYZER_AND_GATE.md](ANALYZER_AND_GATE.md)。

## 人間が管理する3ファイル

日常の作業はこの3ファイルだけに集中する。

| ファイル | 人間がやること | 頻度 |
| --- | --- | --- |
| `01-human-review/TEST_RULES.md` | 期待値と仕様原文の対応を確認し、`pending` → `approved` にする | 機能ごと |
| `01-human-review/OPEN_QUESTIONS.md` | 仕様の未決事項に決定を下す | 未決が出るたび |
| `01-human-review/SPEC_INDEX.md` | 仕様の正本と対象機能（1〜3件）を登録する | 最初と仕様変更時 |

`check.py`、`tests/`、`ANALYZER_AND_GATE.md`（仕組みの説明）、`CLAUDE_PROMPTS.md`（AIへの指示）は、通常は編集しない。

## 手順（新プロジェクトに導入する場合）

**Step 0. 準備**
プロジェクトのルート直下に配置する。clone・改名・git管理の手順は [../README.md](../README.md) の「ファイル」章を参照。以降のコマンド例は、フォルダ名が既定の `test-gate-mvp` である前提。

**Step 1. 仕様の正本と対象機能を決める**（人間）
`01-human-review/SPEC_INDEX.md` に、正本となる仕様と、最初に試す機能を1〜3件だけ書く。サンプル行は実在のリンクに置き換える。仕様の正本が決まらない間は、次へ進まない。

**Step 2. ルール候補を作る**（AI → 人間）
[CLAUDE_PROMPTS.md](CLAUDE_PROMPTS.md) の Prompt 1→2 をAIに渡し、`01-human-review/TEST_RULES.md` に `pending` の行を追加させる。仕様に書かれていない点は、AIに決めさせず `01-human-review/OPEN_QUESTIONS.md` に記録する。

**Step 3. 根拠を固定する**（プログラム）
```bash
python3 test-gate-mvp/03-analyzer/check.py --stamp R-001
```
現在の仕様ファイルのSHA-256が表に記録される。承認状態は `pending` のまま変わらない。

**Step 4. 承認する**（人間）
仕様の原文と期待値を見比べ、導出が正しく、適用条件に合っていることを確認する。未決事項があれば `01-human-review/OPEN_QUESTIONS.md` で決定し、決定内容は仕様の正本（仕様書・採択Issue・ADR）に反映する。そのうえで `01-human-review/TEST_RULES.md` の承認を `approved` に変える。承認の議論は既存のPR/Issueに残す。

**Step 5. 点検する**（プログラム）
```bash
# 仕様出典・実装アンカー・承認・未決事項を確認
python3 test-gate-mvp/03-analyzer/check.py

# HOLD、実装DRIFT、ルール未登録を終了コード1で通知（CIへの導入は任意）
python3 test-gate-mvp/03-analyzer/check.py --strict
```
結果は次のように読む。

- `ALLOW`: 承認済みの期待値と根拠の対応が、今も有効である。この期待値で、仕様適合のテストを確定してよい。
- `HOLD`: 確定しない。理由の列に原因が出るので、末尾の「HOLDになったらどうするか」を見る。

**次の機能へ**
1機能で、仕様の曖昧さに気付けるか、根拠が古くなったときに保留できるか、保守の負担が小さいかを確かめてから、対象を増やす。

スクリプト自体の回帰テストは次で実行できる。

```bash
python3 -m unittest discover -s test-gate-mvp/03-analyzer/tests -v
```

現時点では01-human-review/TEST_RULES.mdの表は空。**新しいプロジェクトの正規仕様やルールを捏造して記入していない**ため、初回の通常実行はルール未登録を表示し、 `--strict` は失敗する。

## Analyzerの結果

| 値 | 意味 |
| --- | --- |
| `ANCHOR_FOUND` | 指定文字列がソースに1回存在（実装の動作・仕様適合の証明ではない） |
| `DRIFT` | 文字列が存在しない、または複数出現して一意に確認できない |
| `UNVERIFIED` | 出典・参照先が未登録、または読めない |

仕様ファイル全体のSHAも確認し、承認時から変わった場合はGateをHOLDする。

## Gateの結果

| 値 | 意味 |
| --- | --- |
| `ALLOW` | approved・仕様の原文アンカー一意・SHA一致・関連未決事項なし。**人間が期待値の意味を確認済みという前提** |
| `HOLD` | 未承認、仕様ドリフト、出典不足、未決事項など。仕様適合のassertionを確定しない |

実装アンカーがDRIFTでも、正しい仕様のオラクルを無効化しないためGateはALLOWになりうる。この場合は実装側の調査が必要で、 `--strict` では終了コード1となる。

終了コードは `0` = 正常終了（通常モードはHOLDでも0）、`1` = strictでHOLD/実装DRIFT/ルールなし、`2` = 不正な表・入出力エラー。

## Claude Codeへの指示（短い工程に分割）

一括プロンプトは使用しない。**[CLAUDE_PROMPTS.md](CLAUDE_PROMPTS.md) の Prompt 1〜5 を必要な工程ごとに渡す**。

- Prompt 1：仕様・対象機能の参照先の確認
- Prompt 2：Markdown表へのルール候補追加と人間の承認
- Prompt 3：決定的Analyzerの確認
- Prompt 4：決定的Gateの確認
- Prompt 5：単体テスト・運用確認

既に実装済みならPrompt 3・4を再実装する必要はなく、Prompt 1→2→5で試す。各工程で成果物・未決事項・完了条件を確認してから次に進む。

## HOLDになったらどうするか

`check.py` の表の「理由」列の文言で、次の対処を選ぶ。

| 理由（表示される文言） | 原因 | 対処 | 担当 |
| --- | --- | --- | --- |
| `未承認: pending` / `未承認: blocked` | 人間がまだ承認していない、または止めている | 原文と期待値を確認し、問題なければ `approved` にする。`blocked` は理由を解消してから戻す | 人間 |
| `仕様原文を一意に確認できない` | 仕様アンカーが仕様ファイルに0回または複数回出現する、またはパスが違う | アンカーを原文の連続した文字列（1回だけ出る箇所）に直す。パスも確認する | 人間／AI |
| `出典SHA256が未登録` | 根拠を固定していない | `--stamp <ID>` を実行する（pending行のみ可） | プログラム |
| `承認時から仕様ファイルが変更された` | 承認後に仕様が更新された | 変更内容を読み、期待値が影響を受けるか確認する。影響がなくても、承認を `pending` に戻して `--stamp` し、再承認する | 人間 |
| `未決事項が未解決: Q-xxx` | 関連する未決事項が `DECIDED` になっていない | `01-human-review/OPEN_QUESTIONS.md` で決定し、決定内容を仕様の正本に反映して `DECIDED` にする | 人間 |
| `未決IDの参照先がない` | 未決IDの誤記、または `01-human-review/OPEN_QUESTIONS.md` に行がない | IDを直す、または未決事項を追加する | 人間／AI |
| `ルールが未登録` | `01-human-review/TEST_RULES.md` の表が空 | Step 2 でルール候補を追加する | AI → 人間 |

Gateが `ALLOW` でも、`--strict` が1を返すことがある。実装アンカーの `DRIFT`（理由に `実装:` と出る）の場合で、仕様の期待値は有効なままである。実装側のコードが変わったのか、仕様に違反しているのかを調べる。アンカーの文字列が変わっただけなら、実装アンカーを更新する。

終了コード `2`（`INPUT_ERROR`）は、表の見出し・列数・区切り行が壊れているなどの入力不備である。HOLDとは別物で、メッセージのファイルと行を直す。
