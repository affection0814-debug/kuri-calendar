# カレンダー用DB同期
#
#   プロジェクトルートのバージョン付きDB（kuribayashi_minami_db_v17.db など）から
#   最新バージョンを見つけて、カレンダー側の固定名にコピーする。
#   GitHub Actions はリポジトリの中身しか見えないため、この同期はアップロード前に
#   手元で行う必要がある。
#
# 使い方（カレンダーフォルダの中で実行）:
#   powershell -File scripts/sync_db.ps1
#
# 入力: ..\kuribayashi_minami_db_v*.db   プロジェクトルートの正本DB（.bak は対象外）
# 出力: data\kuribayashi_minami.db       カレンダービルドが読む固定名

$ErrorActionPreference = 'Stop'

$candidates = Get-ChildItem -Path '..' -Filter 'kuribayashi_minami_db_v*.db' -File |
    Where-Object { $_.Name -match '^kuribayashi_minami_db_v(\d+)\.db$' } |
    ForEach-Object {
        [PSCustomObject]@{
            Version = [int]$Matches[1]
            File    = $_
        }
    }

if (-not $candidates) {
    Write-Error '見つかりません: プロジェクトルートに kuribayashi_minami_db_v*.db がありません'
}

$latest = $candidates | Sort-Object Version -Descending | Select-Object -First 1

New-Item -ItemType Directory -Force -Path 'data' | Out-Null
Copy-Item -Path $latest.File.FullName -Destination 'data\kuribayashi_minami.db' -Force

Write-Output "v$($latest.Version)（$($latest.File.Name)）→ data\kuribayashi_minami.db にコピーしました"
Write-Output 'この後 data\kuribayashi_minami.db を他の生成物と一緒にアップロードしてください'
