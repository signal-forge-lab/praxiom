# Praxiom

[English](README.md) | [日本語](README.ja.md)

> **開発中スナップショット - 2026-09-12。** Praxiom は現在も開発中です。
> API、Evidence形式、運用手順は互換性保証なしで変更される可能性があります。
> この公開リポジトリは公開前監査済みのスナップショットから開始しており、
> 公開前のローカルGit履歴は意図的に含めていません。

**Praxiom = Praxis + Axiom**。実世界で操作し、その結果から学習し、経験を
再利用可能な原則へ整理し、次の操作を改善することを目的としています。

Praxiomは、独立実装したNative iOS Runtimeに、汎用Learning、Experience、
Shadow/Adaptive、Promotion、Telemetry、Recovery、Human Teachingの各レイヤーを
組み合わせた、汎用的なiOS実行・学習基盤です。Merge Bossはこの基盤を検証する
代表ドメインの1つであり、ゲーム固有概念を共通Learning/Runtime層へ持ち込まない
ことを設計上の不変条件としています。

## 現在の開発状況

R3からR10までのCritical Pathは完了しています。Post-R10のPhase A、Phase Bも
完了し、**Phase C0（Phase C Readiness）も100%完了**しています。

現在のPhase Cは、operation class単位の限定Canaryを段階的に進めるフェーズです。
Adaptive Live全体を一括で有効化しているわけではありません。

このスナップショットでACCEPTEDになっているPhase C Canaryは次の3つです。

- `system:return-home`
- `system:launch-application`
- `mergeboss:open-level-board`

generator生成、merge実行、order delivery、ゲーム全体の自律操作まで承認済みという
意味ではありません。Sequence Liveも引き続きOFFです。

現在状態と保持済みEvidence:

- `docs/STATUS.md`
- `docs/evidence/PHASE_C_PROGRESS.md`
- `docs/evidence/20260912_phasec-home-live-canary-acceptance.json`
- `docs/evidence/20260912_phasec-launch-application-live-canary-acceptance.json`
- `docs/evidence/20260912_phasec-mergeboss-open-board-canary-acceptance.json`

このスナップショットで保持している最新の決定論的テストは **600/600 PASS** です。
Runtime boundary guard、provenance guard、compile check、diff checkもPASSしています。

## 開発環境のセットアップ

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## 決定論的テスト

```powershell
python -m pytest -q
```

リポジトリルートでrepo用venvを有効にして実行します。決定論的テストスイート自体は
物理iPhoneへの接続を必要としません。

## Read-only Monitor

Praxiomにはport `17680` で動作するローカルread-only Monitorがあります。Monitorは
privacy-safeなRunJournalと、任意のlatest-frame projectionのみを読み取ります。
UI refreshからRuntimeの `observe`、`execute`、`recover`、`invalidate` を呼ばないため、
active revisionを変更しません。

```powershell
.venv\Scripts\python -m praxiom.monitor.server
```

起動後は `http://127.0.0.1:17680/` を開きます。非loopback bindは明示的に
`--allow-lan` を指定しない限り拒否されます。

現在画面の画像bytesは機微情報として扱い、**opt-in**です。長時間稼働するMCP Runtimeで
Monitor Frame Projectionを有効化する場合は、次のように再起動します。

```powershell
.\scripts\stop_praxiom_mcp.ps1
.\scripts\start_praxiom_mcp.ps1 -MonitorFrameProjection
```

projectionは `~/.praxiom/monitor/latest-frame.png` と制限されたmetadataのみを保持し、
observationごとに上書きします。画像履歴やVisual Flight Recorderそのものではありません。

## Provenance

- **Phone Harnessはhistorical/reference only**です。このリポジトリのproduction、
  build、runtime依存ではなく、そのproduction sourceをimport、copy、rename-port、
  callしません。
- `scripts/check_provenance.py` がproduction sourceとdependency declarationに対して
  この境界を検証します。
- **Active execution path:** `praxiom.ios_runtime` -> unmodified upstream
  `pymobiledevice3` -> WDA / CoreDevice / iPhone。
- `pymobiledevice3` は監査済みupstream commit
  `ec4ac06a850a6a884ca778350621f354faf347c6` に固定しています。
- 詳細は `docs/PROVENANCE.md` を参照してください。

## 公開スナップショット方針

この公開リポジトリは2026-09-12時点の開発状態をsanitizeしたsnapshotから開始します。
公開前のprivate Git historyにはworkstation-local path等の公開不要な環境情報が含まれていた
ため、公開履歴へは引き継いでいません。

また、特定のローカル開発環境でのみ使用していたSecure MCP Tunnel helper scriptsは、
Praxiom Runtime、決定論的テスト、ローカルread-only Monitorの必須要素ではないため、
公開snapshotから除外しています。

## Git運用

公開開発では、レビュー済みの安定した公開状態を`main`、公開されても問題ない
統合作業を`develop`、個別変更を短命な`feature/*`ブランチで管理します。
ブランチを機密性の境界には使用しません。SecretやPC固有設定はGitの外で管理し、
実装自体を非公開にする必要がある場合は別のPrivate Repositoryを使用します。

[Git運用 (English)](docs/GIT_WORKFLOW.md) / [Git運用 (日本語)](docs/GIT_WORKFLOW.ja.md)

## License

GPL-3.0-or-later。`LICENSE` を参照してください。
