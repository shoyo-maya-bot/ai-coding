Feature: 受注ファイル取込

  Scenario: 結果ファイルに件数が出る
    Given 受注ファイル "orders.csv" に 3 行ある
    When 取込を実行する
    Then 結果ファイルの取込件数は 3
    And エラー件数は 0
