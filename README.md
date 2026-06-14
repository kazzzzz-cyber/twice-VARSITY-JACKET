# TWICE VARSITY JACKET 在庫監視

S・M・Lのうち、どれか1サイズでも購入可能になった時点で、そのサイズを1着入れるShopifyカートリンクを作り、GmailとLINEへ通知します。複数サイズが同時に入荷した場合は、サイズごとに1着用リンクを送ります。GitHub Actionsで動くため、PCを閉じていても有効です。

## 重要

- カート投入だけでは在庫は確保されません。通知後に決済が必要です。
- ストアの仕様変更、Bot対策、商品URL変更などで動作しなくなる可能性があります。
- 過度なアクセスを避けるため、5分間隔に設定しています。
- 自動決済・支払情報の保存・CAPTCHA回避は実装していません。

## 1. GitHubへ登録

1. GitHubで新しいPrivate repositoryを作成します。
2. このフォルダ内のファイルを、フォルダ構成を保ったままアップロードします。
3. repositoryの `Settings` → `Actions` → `General` を開きます。
4. `Workflow permissions` で `Read and write permissions` を選び、保存します。

## 2. Gmail通知の準備

Googleアカウントで2段階認証を有効にし、アプリパスワードを発行します。通常のGoogleパスワードは登録しません。

GitHubの `Settings` → `Secrets and variables` → `Actions` → `New repository secret` から以下を登録します。

| Secret名 | 内容 |
|---|---|
| `SMTP_USERNAME` | 送信元Gmailアドレス |
| `SMTP_PASSWORD` | Googleの16桁アプリパスワード |
| `EMAIL_TO` | 通知を受け取るメールアドレス |

## 3. LINE通知の準備

LINE Notifyは使用せず、LINE Messaging APIを使います。

1. LINE Official Accountを作成します。
2. LINE Developers ConsoleでProviderとMessaging API channelを作成・連携します。
3. Messaging API設定で長期のChannel access tokenを発行します。
4. 作成した公式アカウントを自分のLINEで友だち追加します。
5. 自分のUser IDを確認します。最も確実なのは、一度Botへメッセージを送り、Webhookイベントの `source.userId` を取得する方法です。
6. GitHub Secretsに以下を追加します。

| Secret名 | 内容 |
|---|---|
| `LINE_CHANNEL_ACCESS_TOKEN` | Messaging APIのChannel access token |
| `LINE_USER_ID` | 自分のLINE User ID（通常はUから始まる文字列） |

## 4. 動作確認

1. GitHub repositoryの `Actions` タブを開きます。
2. `Watch TWICE varsity jacket stock` を選びます。
3. `Run workflow` を押します。
4. 実行ログに各サイズの `available` 状態が表示されます。

現在すべて売り切れなら通知されず、5分ごとの監視が継続します。S・M・Lのどれか1サイズでも入荷するとメールとLINEを送り、重複通知防止のためworkflowを自動停止します。リンクを開くと、選んだサイズ1着がカートに入ります。

## 現在の通知条件

- S・M・Lのどれか1サイズでも在庫が復活すれば通知します。
- 複数サイズが同時に在庫ありの場合は、各サイズの「1着だけ入れるカートリンク」をまとめて通知します。
- 最初の通知に成功するとworkflowを自動停止します。再度監視したい場合はGitHub Actions画面からworkflowを有効化してください。
