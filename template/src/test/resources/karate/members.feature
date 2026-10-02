Feature: 会員 API（API0001 照会 / API0002 登録）

  Background:
    * url baseUrl
    * def email = 'karate-' + java.util.UUID.randomUUID() + '@example.com'

  Scenario: 登録した会員を照会できる
    Given path '/api/v1/members'
    And request { name: '結合 テスト', email: '#(email)' }
    When method post
    Then status 201
    And match response == { id: '#number', name: '結合 テスト', email: '#(email)' }
    * def id = response.id

    Given path '/api/v1/members', id
    When method get
    Then status 200
    And match response.email == email

  Scenario: 同じメールアドレスは登録できない
    Given path '/api/v1/members'
    And request { name: 'A', email: '#(email)' }
    When method post
    Then status 201

    Given path '/api/v1/members'
    And request { name: 'B', email: '#(email)' }
    When method post
    Then status 409
    And match response.messageId == 'APPE0003'

  Scenario: 存在しない会員は 404
    Given path '/api/v1/members', 999999999
    When method get
    Then status 404
    And match response.messageId == 'APPE0002'
