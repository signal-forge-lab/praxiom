# Git運用

[English](GIT_WORKFLOW.md) | [日本語](GIT_WORKFLOW.ja.md)

Praxiomでは、ブランチは開発工程の管理に使用し、機密性の境界には使用しません。

## ブランチ

- `main`: レビュー済みで安定した公開状態。
- `develop`: すでに公開可能な内容だけを扱う統合ブランチ。
- `feature/*`: `develop`から作成する短命な個別作業ブランチ。レビュー後に
  `develop`へ統合します。

これらすべてのブランチに、公開されても問題ない内容だけをコミットします。

## Public / Privateの分離

Public GitHub Repositoryには、公開可能なソース、テスト、ドキュメント、fixture、
設定例だけを置きます。次の内容はこのリポジトリの外で管理します。

- API Key、Token、秘密鍵、証明書、復号済みSecret。
- PC固有パスやローカル設定。
- 実行ログ、キャプチャ、ローカル生成物、実機固有データ。
- 意図的に内部専用とする実装。

PC固有設定は`.env`、`config.local.json`、`local/`などのignore対象を使用します。
`.env.example`や`config.example.json`を公開する場合は、Secretを含まないダミー値だけを
記載します。

実装自体を内部専用にする必要がある場合は、別のPrivate Repositoryを使用します。
Public Repositoryのprivate branchで分離しません。

## Secret

Secretの正本はこのリポジトリの外部に置きます。Runtimeは注入された環境変数や
設定値を参照できますが、実値をGitへコミットしません。一度でもSecretをコミットした
場合は漏えい済みとして扱い、履歴修正より先にローテーションします。

## 公開前確認

branchのpushまたは`main`への統合前に、次を確認します。

1. 完全なdiffとstage対象をレビューする。
2. ソース、テスト、設定、ドキュメント、必要なGit履歴を対象に、Secret、個人情報、
   PC固有パス、実機ID、ログ、生成物を検査する。
3. 決定論的テストとrepository boundary / provenance guardを実行する。
4. 公開ドキュメントに英語版と日本語版が揃っていることを確認する。
5. レビュー済みの`develop`を`main`へ統合し、private情報をbranchで隠さない。

Praxiomの公開前ローカル履歴はpublic remoteへ接続しません。公開開発は、sanitize済み
Public Repositoryから作成した独立cloneで行います。
